package main

import (
	"machine"
	"math"
	"sync"
	"time"

	micon_v1 "firmware/gen/micon/v1"
)

const (
	// 実験中: 1kHz。4ピンファンの規格(21-28kHz)に戻すなら time.Second / (25 * 1000)。
	pwmPeriod = time.Second / 1000 // 1kHz
	fadeSteps = 100
	fadeGamma = 2.2

	// PC817 のフォトカプラでファンの PWM 線を GND に落とす配線のとき、出力が反転する。
	// true なら、デューティを top から引いて出力し、PwmFade.value は大きいほど速いままにする。
	// GPIO をファンの PWM 線に直接つなぐのは禁止(マイコンが壊れた)。必ずフォトカプラ経由にする。
	pwmInverted = true
)

// ファンの PWM ピン(GP2-GP7)。ファンはデフォルトで OFF にするため、起動時にこの全ピンを
// 最小で出力する。指示が来るまでピンが Low のままだと、反転配線ではファンが全開になる。
var fanPins = []uint32{2, 3, 4, 5, 6, 7}

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
	// DurationMs が 0 のときは、フェードせず cmd.Value に即座に切り替える。
	if cmd.GetDurationMs() == 0 {
		setDuty(pwm, channel, top, cmd.GetValue(), 1)
		return nil
	}
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

		setDuty(pwm, channel, top, cmd.GetValue(), float64(i)/fadeSteps)
		time.Sleep(interval)
	}

	return nil
}

// setDuty は、フェードの進み具合 t (0-1) でのデューティを出力する(ガンマ2.2、pwmInverted なら反転)。
func setDuty(pwm pwmDevice, channel uint8, top float64, value uint32, t float64) {
	duty := math.Pow(t*float64(value)/255, fadeGamma) * top
	if pwmInverted {
		duty = top - duty
	}
	pwm.Set(channel, uint32(duty))
}
