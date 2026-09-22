"""One local TCP consumer; networking never runs in the inference loop."""

import json
import logging
import socket
import threading
import time

from .gesture_delivery import DeliveryOutbox

MAX_MESSAGE_BYTES = 8192
logger = logging.getLogger(__name__)


class GestureServer:
    def __init__(
        self,
        outbox: DeliveryOutbox,
        *,
        host: str = "127.0.0.1",
        port: int = 5001,
        state_interval: float = 0.1,
    ) -> None:
        self.outbox = outbox
        self.host = host
        self.port = port
        self.state_interval = state_interval
        self._stop = threading.Event()
        self._listener: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._error: BaseException | None = None

    def start(self) -> None:
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            listener.bind((self.host, self.port))
            listener.listen(1)
            listener.settimeout(0.05)
        except BaseException:
            listener.close()
            raise
        self._listener = listener
        self.port = listener.getsockname()[1]
        self._thread = threading.Thread(target=self._run, name="gesture-delivery", daemon=True)
        self._thread.start()

    def check(self) -> None:
        if self._error is not None:
            raise RuntimeError("Gesture delivery thread failed") from self._error

    def close(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2)
        if self._listener is not None:
            self._listener.close()
        if self._thread is not None and self._thread.is_alive():
            raise RuntimeError("Gesture delivery did not stop")
        self.check()

    def _run(self) -> None:
        try:
            assert self._listener is not None
            while not self._stop.is_set():
                try:
                    client, _ = self._listener.accept()
                except TimeoutError:
                    continue
                with client:
                    client.settimeout(0.05)
                    client.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                    try:
                        self._serve(client)
                    except (OSError, ValueError) as error:
                        logger.info("Gesture client disconnected: %s", error)
        except BaseException as error:
            self._error = error

    def _serve(self, client: socket.socket) -> None:
        buffer = b""
        next_state = 0.0
        reconnect = True
        while not self._stop.is_set():
            now = time.monotonic()
            messages = []
            if now >= next_state:
                messages.append(self.outbox.state(now))
                next_state = now + self.state_interval
            messages.extend(self.outbox.events(now, reconnect=reconnect))
            reconnect = False
            for message in messages:
                if self._stop.is_set():
                    return
                # The receiver also checks expiry after any socket buffering.
                client.sendall((json.dumps(message, allow_nan=False) + "\n").encode("utf-8"))
            try:
                chunk = client.recv(4096)
            except TimeoutError:
                continue
            if not chunk:
                return
            buffer += chunk
            while b"\n" in buffer:
                line, buffer = buffer.split(b"\n", 1)
                if len(line) > MAX_MESSAGE_BYTES:
                    raise ValueError("ACK too large")
                try:
                    ack = json.loads(line)
                except (ValueError, UnicodeDecodeError) as error:
                    raise ValueError("Invalid ACK JSON") from error
                self.outbox.acknowledge(ack)
            if len(buffer) > MAX_MESSAGE_BYTES:
                raise ValueError("ACK too large")
