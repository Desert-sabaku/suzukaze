"""Diffuser button presses from Unity."""

from collections.abc import Callable

from diffuser.v1 import diffuser_pb2

# DiffuserChannel の値の順(ラムネ, 森)
DEFAULT_PINS = (8, 9)
MAX_PRESS_MS = 5000


class DiffuserController:
    """Map a DiffuserChannel to its pin and press it through send_pulse if given."""

    def __init__(
        self,
        send_pulse: Callable[[int, int], None] | None = None,
        pins: tuple[int, ...] = DEFAULT_PINS,
    ) -> None:
        self._send_pulse = send_pulse
        self._pins = pins

    def press(self, press: diffuser_pb2.DiffuserPress) -> None:
        if (
            not 1 <= press.channel <= len(self._pins)
            or not 0 < press.duration_ms <= MAX_PRESS_MS
        ):
            raise ValueError("Invalid diffuser press")
        if self._send_pulse is not None:
            self._send_pulse(self._pins[press.channel - 1], press.duration_ms)
