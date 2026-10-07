package main

import (
	micon_v1 "firmware/gen/micon/v1"
)

type FieldHolder[T any] struct {
  self   T
  Fields []*micon_v1.LogField
}

func NewFieldHolder[T any](self T) *FieldHolder[T] {
  return &FieldHolder[T]{
    self: self,
  }
}

func (h *FieldHolder[T]) Bytes(key string, val []byte) T {
  h.Fields = append(h.Fields, &micon_v1.LogField{
    Key:   key,
    Value: &micon_v1.LogField_BytesVal{BytesVal: val},
  })
  return h.self
}

func (h *FieldHolder[T]) Str(key string, val string) T {
   h.Fields = append(h.Fields, &micon_v1.LogField{
    Key:   key,
    Value: &micon_v1.LogField_StringVal{StringVal: val},
  })
  return h.self
}

func (h *FieldHolder[T]) Int64(key string, val int64) T {
	h.Fields = append(h.Fields, &micon_v1.LogField{
		Key:   key,
		Value: &micon_v1.LogField_IntVal{IntVal: val},
	})
  return h.self
}

func (h *FieldHolder[T]) Int(key string, val int) T {
  return h.Int64(key, int64(val))
}

func (h *FieldHolder[T]) Uint64(key string, val uint64) T {
	h.Fields = append(h.Fields, &micon_v1.LogField{
		Key:   key,
		Value: &micon_v1.LogField_UintVal{UintVal: val},
	})
  return h.self
}


func (h *FieldHolder[T]) Uint(key string, val uint) T {
  return h.Uint64(key, uint64(val))
}

func (h *FieldHolder[T]) Uint16(key string, val uint16) T {
  return h.Uint64(key, uint64(val))
}

func (h *FieldHolder[T]) Float64(key string, val float64) T {
	h.Fields = append(h.Fields, &micon_v1.LogField{
		Key:   key,
		Value: &micon_v1.LogField_DoubleVal{DoubleVal: val},
	})
  return h.self
}

func (h *FieldHolder[T]) Bool(key string, val bool) T {
	h.Fields = append(h.Fields, &micon_v1.LogField{
		Key:   key,
		Value: &micon_v1.LogField_BoolVal{BoolVal: val},
	})
  return h.self
}

type AppError struct {
  Code string
  Message string
  Err error
  *FieldHolder[*AppError]
}

func NewAppError(code string, message string) *AppError {
  e := &AppError{
    Code: code,
    Message: message,
  }
  e.FieldHolder = NewFieldHolder(e)
  return e
}

func (e *AppError) Wrap(err error) *AppError {
  e.Err = err
  return e
}

// error インターフェースを満たしておく
func (e *AppError) Error() string {
	return e.Message
}

type Logger struct {
	transceiver *PacketTransceiver
}

func NewLogger(pt *PacketTransceiver) *Logger {
	return &Logger{transceiver: pt}
}

func (l *Logger) Debug() *LogEvent { return l.newEvent(micon_v1.LogLevel_LOG_LEVEL_DEBUG) }
func (l *Logger) Info() *LogEvent  { return l.newEvent(micon_v1.LogLevel_LOG_LEVEL_INFO) }
func (l *Logger) Warn() *LogEvent  { return l.newEvent(micon_v1.LogLevel_LOG_LEVEL_WARN) }
func (l *Logger) Error() *LogEvent { return l.newEvent(micon_v1.LogLevel_LOG_LEVEL_ERROR) }

func (l *Logger) newEvent(level micon_v1.LogLevel) *LogEvent {
  e := &LogEvent{
		logger: l,
		entry: micon_v1.LogEntry{
			UptimeMs: UptimeMs(),
			Level:     level,
		},
	}
  e.FieldHolder = NewFieldHolder(e)
  return e
}

type LogEvent struct {
	logger *Logger
	entry  micon_v1.LogEntry
  *FieldHolder[*LogEvent]
}

func (e *LogEvent) send() {
	e.entry.Fields = e.Fields

	pkt := &micon_v1.Packet{
		Payload: &micon_v1.Packet_LogEntry{
			LogEntry: &e.entry,
		},
	}

	_ = e.logger.transceiver.SendPacket(pkt)
}

// Msg でパケットを組み立ててシリアル送信
func (e *LogEvent) Msg(msg string) {
	e.entry.Message = msg
  e.send()
}

func (e *LogEvent) Err(err *AppError) {
  if err == nil {
		e.send()
		return
	}

	e.entry.Message = err.Message
  if err.Code != "" {
    e.Str("error_code", err.Code)
  }

  if err.Err != nil {
		e.Str("error_cause", err.Err.Error())
	}

  if err.FieldHolder != nil {
    e.Fields = append(e.Fields, err.Fields...)
  }

  e.send()
}
