package main

import (
	"machine"
	"time"
)

func heartbeat(led machine.Pin, period time.Duration) {
	for {
	  Log.Info().Bool("alive", true).Msg("Heartbeat signal sent")
		led.High()
		time.Sleep(period)
		led.Low()
		time.Sleep(period)
	}
}
