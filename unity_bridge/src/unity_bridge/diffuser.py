"""Diffuser button presses from Unity."""

import os
import time
from collections.abc import Callable
from typing import Any

from diffuser.v1 import diffuser_pb2

# DiffuserChannel の値の順(ラムネ, 森)
DEFAULT_PINS = (8, 9)
MAX_PRESS_MS = 5000


class DiffuserController:
    """Map a DiffuserChannel to its pin and press it through send_pulse if given.

    The diffusers toggle on each press and cannot be read, so ON/OFF is
    estimated from the parity of the presses since the bridge started, like
    Unity's DiffuserMock.
    """

    def __init__(
        self,
        send_pulse: Callable[[int, int], None] | None = None,
        pins: tuple[int, ...] = DEFAULT_PINS,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._send_pulse = send_pulse
        self._pins = pins
        self._clock = clock
        # channel -> (押した回数, 最後に押した時刻)
        self._presses: dict[int, tuple[int, float]] = {}

    @property
    def wired(self) -> bool:
        """Whether presses reach the MCU (otherwise they are only recorded)."""
        return self._send_pulse is not None

    def channels(self) -> list[dict[str, Any]]:
        """Each channel's estimated state, in DiffuserChannel order."""
        result = []
        for channel in range(1, len(self._pins) + 1):
            count, at = self._presses.get(channel, (0, None))
            result.append(
                {
                    "channel": channel,
                    "pin": self._pins[channel - 1],
                    "on": count % 2 == 1,
                    "presses": count,
                    "last_press_at": at,
                }
            )
        return result

    def press(self, press: diffuser_pb2.DiffuserPress) -> None:
        if (
            not 1 <= press.channel <= len(self._pins)
            or not 0 < press.duration_ms <= MAX_PRESS_MS
        ):
            raise ValueError("Invalid diffuser press")
        count, _ = self._presses.get(press.channel, (0, None))
        self._presses[press.channel] = (count + 1, self._clock())
        if self._send_pulse is not None:
            self._send_pulse(self._pins[press.channel - 1], press.duration_ms)


def pins_from_env() -> tuple[int, ...]:
    """DIFFUSER_PINS(カンマ区切り、DiffuserChannel の値の順)。なければ DEFAULT_PINS。"""
    pins = os.getenv("DIFFUSER_PINS")
    return tuple(int(pin) for pin in pins.split(",")) if pins else DEFAULT_PINS
