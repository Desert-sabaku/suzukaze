package main

import (
	"machine"
)

func main() {
	led := machine.LED
	led.Configure(machine.PinConfig{Mode: machine.PinOutput})

  Log.Info().Msg("System is starting up")

	select {}
}

