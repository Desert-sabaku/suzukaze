package main

import (
	"encoding/binary"
	"io"

	comms_v1 "firmware/gen/comms/v1"
)


var magicHeader = [4]byte{'S', 'Z', 0xAA, 0x55}

func sendPacket(w io.Writer, pkt *comms_v1.Packet) error {
	data, err := pkt.MarshalVT()
	if err != nil {
		return err
	}

  var header [6]byte
  header[0] = magicHeader[0]
  header[1] = magicHeader[1]
  header[2] = magicHeader[2]
  header[3] = magicHeader[3]
  binary.BigEndian.PutUint16(header[4:], uint16(len(data)))

  if _, err := w.Write(header[:]); err != nil {
    return err
  }
  _, err = w.Write(data)
  return err
}
