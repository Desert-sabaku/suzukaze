package main

import (
	"machine"
	"math"
	"sync"
	"time"

	micon_v1 "firmware/gen/micon/v1"
)

const (
	pwmPeriod = time.Second / (25 * 1000) // 25kHz
	fadeSteps = 100
	fadeGamma = 2.2
)

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

	pinChans sync.Map // map[uint32]chan *micon_v1.PwmFade
)

// dispatch sends cmd to the pin's fade worker, starting the worker on first
// use. If the worker is already fading, the in-flight fade is interrupted.
func dispatch(cmd *micon_v1.PwmFade) {
	chAny, loaded := pinChans.LoadOrStore(cmd.GetPin(), make(chan *micon_v1.PwmFade, 1))
	ch := chAny.(chan *micon_v1.PwmFade)

	if !loaded {
		go fadeWorker(cmd.GetPin(), ch)
	}

	select {
	case ch <- cmd:
	default:
		select {
		case <-ch:
		default:
		}
		ch <- cmd
	}
}

// fadeWorker owns PWM output for a single pin and applies incoming commands
// one at a time, interrupting any fade currently in progress.
func fadeWorker(pinNum uint32, ch chan *micon_v1.PwmFade) {
	pin := machine.Pin(pinNum)

	slice, err := machine.PWMPeripheral(pin)
	if err != nil {
		Log.Error().Err(NewAppError("INVALID_PWM_PIN", "invalid PWM pin").Wrap(err).Uint("pin", uint(pinNum)))
		return
	}
	pwm := pwmPeripherals[slice]

	if err := pwm.Configure(machine.PWMConfig{Period: uint64(pwmPeriod)}); err != nil {
		Log.Error().Err(NewAppError("PWM_CONFIGURE_FAILED", "failed to configure PWM").Wrap(err).Uint("pin", uint(pinNum)))
		return
	}

	channel, err := pwm.Channel(pin)
	if err != nil {
		Log.Error().Err(NewAppError("PWM_CHANNEL_FAILED", "failed to get PWM channel").Wrap(err).Uint("pin", uint(pinNum)))
		return
	}

	cmd := <-ch
	for {
		if next := fade(pwm, channel, cmd, ch); next != nil {
			cmd = next
			continue
		}
		cmd = <-ch
	}
}

// fade ramps duty from 0 to cmd.Value (0-255) over cmd.DurationMs, applying a
// gamma 2.2 curve. It returns early with the interrupting command if a new
// one arrives on ch before the fade completes.
func fade(pwm pwmDevice, channel uint8, cmd *micon_v1.PwmFade, ch chan *micon_v1.PwmFade) *micon_v1.PwmFade {
	top := float64(pwm.Top())
	// TODO: when DurationMs is 0, jump to cmd.Value at once. Now the interval is
	// clamped to 1ms below, so the fade takes about fadeSteps ms. Unity's
	// FanDeviceMock already jumps instantly.
	interval := time.Duration(cmd.GetDurationMs()) * time.Millisecond / fadeSteps
	if interval <= 0 {
		interval = time.Millisecond
	}

	for i := 0; i <= fadeSteps; i++ {
		select {
		case next := <-ch:
			return next
		default:
		}

		t := float64(i) / fadeSteps
		duty := math.Pow(t*float64(cmd.GetValue())/255, fadeGamma) * top
		pwm.Set(channel, uint32(duty))
		time.Sleep(interval)
	}

	return nil
}
