"""Fan commands from Unity and the fan output that Unity reads back."""

import queue
import threading
import time
from collections.abc import Callable
from typing import Any, cast

from bridge.v1 import bridge_pb2
from fan.v1 import fan_pb2

from .settings import Settings

CHANNELS = tuple(range(1, 7))
MAX_VALUE = 255
GAMMA = 2.2  # firmware/cmd/pwm.go の fadeGamma と同じ
DEFAULT_SERIAL_PORT = "COM3"
DEFAULT_BAUDRATE = 115200


class FanController:
    """Track each fan's output; forward fades through send_fade if given.

    The firmware has no readback, so the "current" output is estimated from the
    last command the way the firmware fades: from 0 to value over duration, on
    a gamma 2.2 curve. ponytail: no tach; read the real value back if the
    firmware ever reports it.
    """

    def __init__(
        self,
        send_fade: Callable[[int, int, int], None] | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._send_fade = send_fade
        self._clock = clock
        # channel -> (target value, started at, duration seconds)
        self._fades: dict[int, tuple[int, float, float]] = {}

    def command(self, fan: fan_pb2.Fan) -> None:
        if fan.channel not in CHANNELS or fan.value > MAX_VALUE:
            raise ValueError("Invalid fan command")
        self._fades[fan.channel] = (fan.value, self._clock(), fan.duration_ms / 1000)
        if self._send_fade is not None:
            self._send_fade(fan.channel, fan.value, fan.duration_ms)

    @property
    def active(self) -> bool:
        return bool(self._fades)

    def _value(self, channel: int, now: float) -> int:
        fade = self._fades.get(channel)
        if fade is None:
            return 0
        target, started, duration = fade
        t = 1.0 if duration <= 0 else min(1.0, (now - started) / duration)
        return round(MAX_VALUE * (t * target / MAX_VALUE) ** GAMMA)

    def state(self) -> bytes:
        now = self._clock()
        state = bridge_pb2.FanState(
            readings=[
                bridge_pb2.FanReading(
                    channel=cast("fan_pb2.FanChannel", c),
                    value=self._value(c, now),
                )
                for c in CHANNELS
            ]
        )
        return bridge_pb2.BridgeEnvelope(fan_state=state).SerializeToString()


class McuFadeSender:
    """Send PwmFade to the firmware from a worker thread.

    The serial port and handshake block, so they stay off the event loop. A
    missing or reset MCU never raises: the failed command is dropped and the
    next command reconnects.
    """

    def __init__(
        self,
        port: str,
        pins: tuple[int, ...],
        baudrate: int = DEFAULT_BAUDRATE,
        client_factory: Callable[[str, int], Any] | None = None,
    ) -> None:
        if len(pins) != len(CHANNELS):
            raise ValueError(f"Expected {len(CHANNELS)} fan pins")
        if client_factory is None:
            from mcu import MCUClient

            client_factory = MCUClient
        self._pins = pins
        self._client_factory = lambda: client_factory(port, baudrate)
        self._client: Any | None = None
        self._commands: queue.Queue[Callable[[Any], None]] = queue.Queue()
        threading.Thread(target=self._run, name="fan-mcu", daemon=True).start()

    def __call__(self, channel: int, value: int, duration_ms: int) -> None:
        pin = self._pins[channel - 1]
        self._commands.put(lambda client: client.send_fade(pin, value, duration_ms))

    def pulse(self, pin: int, duration_ms: int) -> None:
        """Press a button wired to pin. Shares the fans' serial port and queue."""
        self._commands.put(lambda client: client.send_pulse(pin, duration_ms))

    def _run(self) -> None:
        while True:
            command = self._commands.get()
            try:
                client = self._client or self._connect()
                self._client = client
                command(client)
            except Exception as error:  # noqa: BLE001
                print(f"Fan MCU unavailable, dropped a command: {error}", flush=True)
                self._close()

    def _connect(self) -> Any:
        client = self._client_factory()
        client.connect()
        try:
            if not client.handshake().matched:
                raise RuntimeError("firmware schema mismatch; rebuild and reflash")
        except BaseException:
            client.close()
            raise
        return client

    def _close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None


def mcu_sender_from_env(settings: Settings) -> McuFadeSender | None:
    """fan_pwm_pins(6本)が空でなければマイコンへの送信役を作る。空なら None。"""
    if not settings.fan_pwm_pins:
        return None
    return McuFadeSender(
        settings.microcontroller_serial_port,
        tuple(settings.fan_pwm_pins),
        settings.microcontroller_baudrate,
    )
