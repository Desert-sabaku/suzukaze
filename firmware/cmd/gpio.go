package main

import (
	"machine"
	"time"

	micon_v1 "firmware/gen/micon/v1"
)

// pulse は pin を DurationMs だけ HIGH にして LOW に戻す(単押しボタン用、PC817経由)。
// どのピンを使うかは呼び出し側(unity_bridge の DIFFUSER_PINS)が決める。
// 受信ループを止めないよう、呼び出し側は goroutine で呼ぶ。
func pulse(cmd *micon_v1.GpioPulse) {
	pin := machine.Pin(cmd.GetPin())
	pin.Configure(machine.PinConfig{Mode: machine.PinOutput})
	pin.High()
	time.Sleep(time.Duration(cmd.GetDurationMs()) * time.Millisecond)
	pin.Low()
}
