package main

import (
	"machine"
	"time"
)

func main() {
	led := machine.LED
	led.Configure(machine.PinConfig{Mode: machine.PinOutput})

  Log.Info().Msg("System is starting up")

  go heartbeat(led, time.Second)

	select {}
}

