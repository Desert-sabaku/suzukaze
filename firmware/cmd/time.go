package main

import "time"

var bootTime = time.Now()

func UptimeMs() uint64 {
  return uint64(time.Since(bootTime).Milliseconds())
}
