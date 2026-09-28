package main

import (
	"machine"
	"time"
)

var Log *Logger

type serialReader struct{}

func (serialReader) Read(p []byte) (n int, err error) {
	for i := range p {
		b, err := machine.Serial.ReadByte()
		if err != nil {
			return i, err
		}
		p[i] = b
	}
	return len(p), nil
}

func init() {
  time.Sleep(2 * time.Second)

  tranceiver := NewPacketTransceiver(serialReader{}, machine.Serial)
  Log = NewLogger(tranceiver)
}

func main() {

	led := machine.LED
	led.Configure(machine.PinConfig{Mode: machine.PinOutput})

  Log.Info().Msg("System is starting up")

  go heartbeat(led, time.Second)

	select {}
}

