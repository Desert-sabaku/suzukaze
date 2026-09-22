import argparse
import asyncio
import os
import threading
from typing import Any

import websockets
from dotenv import load_dotenv

from .gesture_relay import GestureRelay

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
        gesture_port: int | None = None,
    ) -> None:
        self.host = host
        self.websocket_port = websocket_port
        self.serial_port = serial_port
        self.baudrate = baudrate
        if gesture_port is not None and serial_port is not None:
            raise ValueError("Gesture relay and serial relay are separate modes")
        self.gesture_relay = (
            GestureRelay(gesture_port) if gesture_port is not None else None
        )
        self._stop = threading.Event()
        self._serial: Any | None = None

    def run(self) -> None:
        """Open both connections and serve Unity until Ctrl+C."""
        asyncio.run(self._run())

    async def _run(self) -> None:
        if self.serial_port is not None:
            from serial import Serial

            self._serial = Serial(self.serial_port, self.baudrate, timeout=0.1)
        try:
            async with websockets.serve(
                self.gesture_relay.serve if self.gesture_relay else self._serve_client,
                self.host,
                self.websocket_port,
                max_size=MAX_MESSAGE_BYTES,
                close_timeout=0.5,
            ):
                print(f"Waiting for Unity on ws://{self.host}:{self.websocket_port}")
                if self.gesture_relay is not None:
                    print(f"Gesture source: 127.0.0.1:{self.gesture_relay.port}")
                elif self.serial_port is None:
                    print("Serial disabled")
                else:
                    print(
                        f"Serial connected: {self.serial_port} ({self.baudrate} baud)"
                    )
                await asyncio.Future()
        finally:
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


def _environment_defaults() -> dict[str, str | int]:
    load_dotenv()
    return {
        "host": os.getenv(
            "UNITY_WEBSOCKET_HOST", os.getenv("UNITY_TCP_HOST", DEFAULT_HOST)
        ),
        "websocket_port": int(
            os.getenv("UNITY_WEBSOCKET_PORT", str(DEFAULT_WEBSOCKET_PORT))
        ),
        "serial_port": os.getenv("MICROCONTROLLER_SERIAL_PORT", DEFAULT_SERIAL_PORT),
        "baudrate": int(os.getenv("MICROCONTROLLER_BAUDRATE", str(DEFAULT_BAUDRATE))),
    }


def test_websocket_connection() -> bool:
    host = os.getenv("UNITY_WEBSOCKET_TEST_HOST", "127.0.0.1")
    port = int(os.getenv("UNITY_WEBSOCKET_PORT", str(DEFAULT_WEBSOCKET_PORT)))

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
    defaults = _environment_defaults()
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
        "--gesture-port",
        type=int,
        help="Relay local gesture TCP to Unity instead of serial (typically 5001).",
    )
    args = parser.parse_args()
    if args.gesture_port is not None:
        if not 1 <= args.gesture_port <= 65535:
            parser.error("--gesture-port must be between 1 and 65535")
        # Gesture delivery is local-only; serial mode retains its existing default.
        if args.host == DEFAULT_HOST:
            args.host = "127.0.0.1"
        if args.host not in {"127.0.0.1", "localhost", "::1"}:
            parser.error("Gesture mode requires a loopback --host")
    return args


def main() -> None:
    args = _parse_args()
    serial_port = (
        None if args.no_serial or args.gesture_port is not None else args.serial_port
    )
    bridge = UnityBridge(
        args.host, args.websocket_port, serial_port, args.baudrate, args.gesture_port
    )
    try:
        bridge.run()
    except KeyboardInterrupt:
        bridge.stop()


if __name__ == "__main__":
    main()
