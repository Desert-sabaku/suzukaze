package main

import (
	"machine"
	"slices"
	"time"

	micon_v1 "firmware/gen/micon/v1"
)

// ディフューザーのボタン用ピン(PC817経由)。起動時は LOW(ボタンを押していない状態)。
// 台数が決まったら足す。unity_bridge の DIFFUSER_PINS と揃える。
var diffuserPins = []uint32{8}

func initGpio() {
	for _, num := range diffuserPins {
		pin := machine.Pin(num)
		pin.Configure(machine.PinConfig{Mode: machine.PinOutput})
		pin.Low()
	}
}

// pulse は pin を DurationMs だけ HIGH にして LOW に戻す。
// 受信ループを止めないよう、呼び出し側は goroutine で呼ぶ。
// ponytail: 許可ピンは diffuserPins のみ。PWM のファンピンを誤って叩かないため。
func pulse(cmd *micon_v1.GpioPulse) {
	if !slices.Contains(diffuserPins, cmd.GetPin()) {
		Log.Error().Err(NewAppError("INVALID_GPIO_PIN", "pin is not pulsable").Uint("pin", uint(cmd.GetPin())))
		return
	}
	pin := machine.Pin(cmd.GetPin())
	pin.High()
	time.Sleep(time.Duration(cmd.GetDurationMs()) * time.Millisecond)
	pin.Low()
}
