package main

import (
	"machine"
	"math"
	"sync"
	"time"
)

const (
	pwmPeriod   = time.Second / (25 * 1000) // 25kHz
	maxValue    = 7999
	fadeSteps   = 100
	fadeGamma   = 2.2
	maxLineSize = 256 // guard against a runaway line if no '\n' ever arrives
)

// Message is a fade instruction received over USB serial as a JSON line.
type Message struct {
	Pin      int           `json:"pin"`
	Value    int           `json:"value"`
	Duration time.Duration `json:"duration"`
}

// pwmDevice is satisfied by *machine.PWM0..7 (unexported concrete type),
// enabling them to be stored in a slice and passed around by interface.
type pwmDevice interface {
	Configure(config machine.PWMConfig) error
	Channel(pin machine.Pin) (channel uint8, err error)
	Top() uint32
	Set(channel uint8, value uint32)
}

var (
	pwmPeripherals = [8]pwmDevice{
		machine.PWM0, machine.PWM1, machine.PWM2, machine.PWM3,
		machine.PWM4, machine.PWM5, machine.PWM6, machine.PWM7,
	}

	pinChans sync.Map // map[int]chan Message
)


// dispatch sends msg to the pin's fade worker, starting the worker on first
// use. If the worker is already fading, the in-flight fade is interrupted.
func dispatch(msg Message) {
	chAny, loaded := pinChans.LoadOrStore(msg.Pin, make(chan Message, 1))
	ch := chAny.(chan Message)

	if !loaded {
		go fadeWorker(msg.Pin, ch)
	}

	select {
	case ch <- msg:
	default:
		select {
		case <-ch:
		default:
		}
		ch <- msg
	}
}

// fadeWorker owns PWM output for a single pin and applies incoming Messages
// one at a time, interrupting any fade currently in progress.
func fadeWorker(pinNum int, ch chan Message) {
	pin := machine.Pin(pinNum)

	slice, err := machine.PWMPeripheral(pin)
	if err != nil {
		// log.Error().Err(err).Int("pin", pinNum).Msg("Invalid PWM pin")
		return
	}
	pwm := pwmPeripherals[slice]

	if err := pwm.Configure(machine.PWMConfig{Period: uint64(pwmPeriod)}); err != nil {
		// log.Error().Err(err).Int("pin", pinNum).Msg("Failed to configure PWM")
		return
	}

	channel, err := pwm.Channel(pin)
	if err != nil {
		// log.Error().Err(err).Int("pin", pinNum).Msg("Failed to get PWM channel")
		return
	}

	msg := <-ch
	for {
		if next := fade(pwm, channel, msg, ch); next != nil {
			msg = *next
			continue
		}
		msg = <-ch
	}
}

// fade ramps duty from 0 to msg.Value over msg.Duration, applying a gamma
// 2.2 curve. It returns early with the interrupting Message if a new
// Message arrives on ch before the fade completes.
func fade(pwm pwmDevice, channel uint8, msg Message, ch chan Message) *Message {
	top := float64(pwm.Top())
	interval := msg.Duration / fadeSteps
	if interval <= 0 {
		interval = time.Millisecond
	}

	for i := 0; i <= fadeSteps; i++ {
		select {
		case next := <-ch:
			return &next
		default:
		}

		t := float64(i) / fadeSteps
		duty := math.Pow(t*float64(msg.Value)/maxValue, fadeGamma) * top
		pwm.Set(channel, uint32(duty))
		time.Sleep(interval)
	}

	return nil
}
