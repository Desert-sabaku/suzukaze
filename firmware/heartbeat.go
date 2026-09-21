package main

import (
	"machine"
	"time"

	"github.com/rs/zerolog/log"
)

func heartbeat(led machine.Pin, period time.Duration) {
	for {
		log.Info().Bool("alive", true).Msg("Heartbeat signal sent")
		led.High()
		time.Sleep(period)
		led.Low()
		time.Sleep(period)
	}
}
