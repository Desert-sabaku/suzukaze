package main

import (
	"bufio"
	"encoding/binary"
	"io"
	"sync"

	micon_v1 "firmware/gen/micon/v1"
)

const (
  HeaderSize = 6 // Magic(4) + Length(2)
  MaxPayloadSize = 512
  MaxPacketSize = HeaderSize + MaxPayloadSize
)

var MagicHeader = [4]byte{'S', 'Z', 0xAA, 0x55}

func NewErrPayloadTooLarge() *AppError {
  return NewAppError("PAYLOAD_TOO_LARGE", "payload exceeds limit").
    Int64("limit_bytes", MaxPayloadSize)
}

type PacketTransceiver struct {
  br *bufio.Reader
  w io.Writer
  rxBuf [MaxPayloadSize]byte
  txMu sync.Mutex // txBuf はheartbeatとreceiveLoopから同時に書かれうる共有バッファ
  txBuf [MaxPacketSize]byte
}

func NewPacketTransceiver(r io.Reader, w io.Writer) *PacketTransceiver {
  return &PacketTransceiver{
    br: bufio.NewReaderSize(r, MaxPayloadSize),
    w: w,
  }
}

func (pt *PacketTransceiver) syncHeader() error {
  var window [4]byte

  if _, err := io.ReadFull(pt.br, window[:]); err != nil {
    return err
  }

  for window != MagicHeader {
    b, err := pt.br.ReadByte()
    if err != nil {
      return err
    }

    window[0] = window[1]
    window[1] = window[2]
    window[2] = window[3]
    window[3] = b
  }

  return nil
}

func (pt *PacketTransceiver) ReadPacket(pkt *micon_v1.Packet) error {
  if err := pt.syncHeader(); err != nil {
    return err
  }

  var lenBuf [2]byte
  if _, err := io.ReadFull(pt.br, lenBuf[:]); err != nil {
    return err
  }
  length := binary.BigEndian.Uint16(lenBuf[:])

  if length > MaxPayloadSize {
    return NewErrPayloadTooLarge().Uint16("got_bytes", length)
  }

  payload := pt.rxBuf[:length]
  if _, err := io.ReadFull(pt.br, payload); err != nil {
    return err
  }

  pkt.Reset()
  return pkt.UnmarshalVT(payload)
}

func (pt *PacketTransceiver) SendPacket(pkt *micon_v1.Packet) error {
  pt.txMu.Lock()
  defer pt.txMu.Unlock()

  size := uint16(pkt.SizeVT())
  if size > MaxPayloadSize {
    return NewErrPayloadTooLarge().Uint16("payload_bytes", size)
  }

  copy(pt.txBuf[0:4], MagicHeader[:])
  binary.BigEndian.PutUint16(pt.txBuf[4:6], size)

  _, err := pkt.MarshalToSizedBufferVT(pt.txBuf[HeaderSize:HeaderSize + size])
  if err != nil {
    return err
  }

  _, err = pt.w.Write(pt.txBuf[:HeaderSize + size])
  return err
}
