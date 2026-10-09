import argparse
import asyncio
import contextlib
import threading
from typing import Any

import websockets
from pydantic import ValidationError

from .bridge_relay import BridgeRelay, DetectionProcess, SampleSource
from .diffuser import DiffuserController
from .fan import FanController, mcu_sender_from_env
from .gesture_debug import ManualGestureSource, serve_debug_gui
from .gesture_delivery import DeliveryOutbox
from .settings import Settings, load_settings

DEFAULT_HOST = "0.0.0.0"
DEFAULT_WEBSOCKET_PORT = 5000
DEFAULT_SERIAL_PORT = "COM3"
DEFAULT_BAUDRATE = 115200
MAX_MESSAGE_BYTES = 64 * 1024


def iter_lines(buffer: bytes) -> tuple[list[bytes], bytes]:
    """Return complete newline-delimited messages and the incomplete remainder."""
    messages = buffer.split(b"\n")
    return messages[:-1], messages[-1]


class UnityBridge:
    """Relay WebSocket messages between one Unity client and a serial port."""

    def __init__(
        self,
        host: str = DEFAULT_HOST,
        websocket_port: int = DEFAULT_WEBSOCKET_PORT,
        serial_port: str | None = DEFAULT_SERIAL_PORT,
        baudrate: int = DEFAULT_BAUDRATE,
        bridge_relay: BridgeRelay | None = None,
        detect: bool = True,
        debug_port: int | None = None,
    ) -> None:
        self.host = host
        self.websocket_port = websocket_port
        self.serial_port = serial_port
        self.baudrate = baudrate
        if bridge_relay is not None and serial_port is not None:
            raise ValueError("Gesture relay and serial relay are separate modes")
        self.bridge_relay = bridge_relay
        self.detect = detect
        # With a port, the debug GUI replaces gesture_detection as the source.
        self.debug_port = debug_port
        self._stop = threading.Event()
        self._serial: Any | None = None

    def run(self) -> None:
        """Open both connections and serve Unity until Ctrl+C."""
        asyncio.run(self._run())

    async def _run(self) -> None:
        if self.serial_port is not None:
            from serial import Serial

            self._serial = Serial(self.serial_port, self.baudrate, timeout=0.1)
        relay = self.bridge_relay
        manual = (
            ManualGestureSource(relay.state_interval / 2)
            if relay is not None and self.debug_port is not None
            else None
        )
        detection = (
            DetectionProcess()
            if relay is not None and self.detect and manual is None
            else None
        )
        source: SampleSource | None = manual or detection
        try:
            if detection is not None:
                detection.start()
            async with contextlib.AsyncExitStack() as stack:
                await stack.enter_async_context(
                    websockets.serve(
                        relay.serve if relay else self._serve_client,
                        self.host,
                        self.websocket_port,
                        max_size=8192 if relay else MAX_MESSAGE_BYTES,
                        close_timeout=0.5,
                    )
                )
                print(f"Waiting for Unity on ws://{self.host}:{self.websocket_port}")
                if relay is not None and manual is not None:
                    assert self.debug_port is not None
                    await stack.enter_async_context(
                        serve_debug_gui(manual, relay, self.host, self.debug_port)
                    )
                    print(
                        "Gesture source: debug GUI at "
                        f"http://{self.host}:{self.debug_port}/"
                    )
                elif relay is not None:
                    print(
                        "Gesture source: gesture_detection child process"
                        if self.detect
                        else "Fan only: gesture_detection is not started"
                    )
                elif self.serial_port is None:
                    print("Serial disabled")
                else:
                    print(
                        f"Serial connected: {self.serial_port} ({self.baudrate} baud)"
                    )
                if relay is not None and source is not None:
                    await relay.pump(source)
                else:
                    await asyncio.Future()
        finally:
            if manual is not None:
                manual.close()
            if detection is not None:
                detection.close()
            self.stop()

    def stop(self) -> None:
        self._stop.set()
        if self._serial is not None:
            self._serial.close()
            self._serial = None

    async def _serve_client(self, websocket: Any) -> None:
        print(f"Unity connected: {websocket.remote_address}")
        serial_to_unity = (
            asyncio.create_task(self._forward_serial_to_unity(websocket))
            if self._serial is not None
            else None
        )
        try:
            async for message in websocket:
                if isinstance(message, str):
                    message = message.encode()
                print(
                    f"Received from Unity: {message.decode('utf-8', errors='replace')}",
                    flush=True,
                )
                if self._serial is None:
                    await websocket.send(message)
                    print("Echoed to Unity", flush=True)
                else:
                    self._write_serial(message)
                    print("Forwarded to serial", flush=True)
        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            if serial_to_unity is not None:
                serial_to_unity.cancel()
                await asyncio.gather(serial_to_unity, return_exceptions=True)
            print("Unity disconnected")

    async def _forward_serial_to_unity(self, websocket: Any) -> None:
        assert self._serial is not None
        while not self._stop.is_set():
            message = await asyncio.to_thread(self._serial.readline)
            if not message:
                continue
            try:
                await websocket.send(message)
            except websockets.exceptions.ConnectionClosed:
                return

    def _write_serial(self, message: bytes) -> None:
        if self._serial is None:
            return
        self._serial.write(message + b"\n")
        self._serial.flush()


def _environment_defaults(settings: Settings) -> dict[str, str | int]:
    return {
        "host": settings.unity_websocket_host,
        "websocket_port": settings.unity_websocket_port,
        "serial_port": settings.microcontroller_serial_port,
        "baudrate": settings.microcontroller_baudrate,
    }


def bridge_relay_from_env() -> BridgeRelay:
    """Delivery timing; times are seconds on the host monotonic clock."""
    settings = load_settings()
    state_interval = settings.gesture_state_interval
    stale_timeout = settings.gesture_stale_timeout
    if not 0 < state_interval < stale_timeout:
        raise ValueError("Gesture state interval must be shorter than stale timeout")
    outbox = DeliveryOutbox(
        event_ttl=settings.gesture_event_ttl,
        stale_timeout=stale_timeout,
        retry_interval=settings.gesture_retry_interval,
        max_pending=settings.gesture_max_pending,
    )
    sender = mcu_sender_from_env(settings)
    return BridgeRelay(
        outbox,
        state_interval,
        FanController(send_fade=sender),
        DiffuserController(sender.pulse, settings.diffuser_pins.ordered()),
    )


def test_websocket_connection() -> bool:
    settings = load_settings()
    host = settings.unity_websocket_test_host
    port = settings.unity_websocket_port

    async def connect() -> None:
        async with websockets.connect(f"ws://{host}:{port}"):
            return

    try:
        asyncio.run(connect())
        print(f"WebSocket connection succeeded: ws://{host}:{port}")
        return True
    except OSError as error:
        print(f"WebSocket connection failed: ws://{host}:{port} ({error})")
        return False


def _parse_args() -> argparse.Namespace:
    settings = load_settings()
    defaults = _environment_defaults(settings)
    parser = argparse.ArgumentParser(
        description="Bridge Unity WebSocket and microcontroller serial I/O."
    )
    parser.add_argument("--host", default=defaults["host"])
    parser.add_argument(
        "--websocket-port", type=int, default=defaults["websocket_port"]
    )
    parser.add_argument("--serial-port", default=defaults["serial_port"])
    parser.add_argument(
        "--no-serial",
        action="store_true",
        help="Start the WebSocket server without opening a serial port.",
    )
    parser.add_argument("--baudrate", type=int, default=defaults["baudrate"])
    parser.add_argument(
        "--gesture",
        action="store_true",
        help="Run gesture_detection and deliver gestures to Unity instead of serial.",
    )
    parser.add_argument(
        "--fan",
        action="store_true",
        help="Serve fan control to Unity only; do not start gesture_detection.",
    )
    parser.add_argument(
        "--debug-gui",
        action="store_true",
        help="Send gestures from a browser GUI instead of gesture_detection.",
    )
    parser.add_argument(
        "--debug-port",
        type=int,
        default=settings.gesture_debug_port,
    )
    args = parser.parse_args()
    # --fan は、ジェスチャー用の WebSocket 中継から、認識の子プロセスだけを除いたもの。
    # --debug-gui は、認識の子プロセスの代わりにブラウザから所作を送るもの。
    if args.fan and args.debug_gui:
        parser.error("--fan and --debug-gui cannot be combined")
    args.gesture = args.gesture or args.fan or args.debug_gui
    if args.gesture:
        # Gesture delivery is local-only; serial mode retains its existing default.
        if args.host == DEFAULT_HOST:
            args.host = "127.0.0.1"
        if args.host not in {"127.0.0.1", "localhost", "::1"}:
            parser.error("Gesture mode requires a loopback --host")
    return args


def main() -> None:
    try:
        args = _parse_args()
        serial_port = None if args.no_serial or args.gesture else args.serial_port
        bridge = UnityBridge(
            args.host,
            args.websocket_port,
            serial_port,
            args.baudrate,
            bridge_relay_from_env() if args.gesture else None,
            detect=not args.fan,
            debug_port=args.debug_port if args.debug_gui else None,
        )
    except ValidationError as error:
        raise SystemExit(f"設定エラー:\n{error}") from error
    try:
        bridge.run()
    except KeyboardInterrupt:
        bridge.stop()


if __name__ == "__main__":
    main()
