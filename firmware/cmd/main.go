package main

import (
	"machine"
	"time"

	micon_v1 "firmware/gen/micon/v1"
)

var Log *Logger
var transceiver *PacketTransceiver

type serialReader struct{}

// 1バイト読めたら即returnする(pを埋めきるまで待つと少量しか届かない時に詰まる)
func (serialReader) Read(p []byte) (n int, err error) {
	for {
		b, err := machine.Serial.ReadByte()
		if err == nil {
			p[0] = b
			return 1, nil
		}
		time.Sleep(time.Millisecond)
	}
}

func init() {
  transceiver = NewPacketTransceiver(serialReader{}, machine.Serial)
  Log = NewLogger(transceiver)
}

func main() {

	led := machine.LED
	led.Configure(machine.PinConfig{Mode: machine.PinOutput})

  Log.Info().Msg("System is starting up")

	// ファンはデフォルトで OFF。ホストの指示を待たずに、全ピンを最小にする。
	for _, pin := range fanPins {
		dispatch(&micon_v1.PwmFade{Pin: pin})
	}

  go heartbeat(led, time.Second)
  go receiveLoop(transceiver)

	select {}
}

// receiveLoop はホストから送られてくるパケットを読み続け、種別に応じて処理する。
func receiveLoop(pt *PacketTransceiver) {
	var pkt micon_v1.Packet
	for {
		if err := pt.ReadPacket(&pkt); err != nil {
			continue
		}
		if req := pkt.GetHandshakeReq(); req != nil {
			handleHandshake(pt, req)
		}
		if cmd := pkt.GetPwmFade(); cmd != nil {
			dispatch(cmd)
		}
	}
}

