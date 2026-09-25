package main

import (
	"io"
	"os"

	comms_v1 "firmware/gen/comms/v1"
)

var Log = NewLogger(os.Stdout)

type Logger struct {
	writer io.Writer
}

func NewLogger(w io.Writer) *Logger {
	return &Logger{writer: w}
}

func (l *Logger) Debug() *LogEvent { return l.newEvent(comms_v1.LogLevel_LOG_LEVEL_DEBUG) }
func (l *Logger) Info() *LogEvent  { return l.newEvent(comms_v1.LogLevel_LOG_LEVEL_INFO) }
func (l *Logger) Warn() *LogEvent  { return l.newEvent(comms_v1.LogLevel_LOG_LEVEL_WARN) }
func (l *Logger) Error() *LogEvent { return l.newEvent(comms_v1.LogLevel_LOG_LEVEL_ERROR) }

func (l *Logger) newEvent(level comms_v1.LogLevel) *LogEvent {
	return &LogEvent{
		logger: l,
		entry: comms_v1.LogEntry{
			UptimeMs: UptimeMs(),
			Level:     level,
		},
	}
}

type LogEvent struct {
	logger *Logger
	entry  comms_v1.LogEntry
}

func (e *LogEvent) Str(key, val string) *LogEvent {
	e.entry.Fields = append(e.entry.Fields, &comms_v1.LogField{
		Key:   key,
		Value: &comms_v1.LogField_StringVal{StringVal: val},
	})
	return e
}

func (e *LogEvent) Int(key string, val int64) *LogEvent {
	e.entry.Fields = append(e.entry.Fields, &comms_v1.LogField{
		Key:   key,
		Value: &comms_v1.LogField_IntVal{IntVal: val},
	})
	return e
}

func (e *LogEvent) Float(key string, val float64) *LogEvent {
	e.entry.Fields = append(e.entry.Fields, &comms_v1.LogField{
		Key:   key,
		Value: &comms_v1.LogField_DoubleVal{DoubleVal: val},
	})
	return e
}

func (e *LogEvent) Bool(key string, val bool) *LogEvent {
	e.entry.Fields = append(e.entry.Fields, &comms_v1.LogField{
		Key:   key,
		Value: &comms_v1.LogField_BoolVal{BoolVal: val},
	})
	return e
}

// Msg でパケットを組み立ててシリアル送信
func (e *LogEvent) Msg(msg string) {
	e.entry.Message = msg

	pkt := &comms_v1.Packet{
		Payload: &comms_v1.Packet_LogEntry{
			LogEntry: &e.entry,
		},
	}

	_ = sendPacket(e.logger.writer, pkt)
}
