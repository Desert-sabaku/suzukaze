"""Run gesture_detection in a child process and deliver its samples to Unity.

The bridge owns delivery state (DeliveryOutbox): current state, expiring
events, retries and Unity's ACKs. Recognition only sends GestureSample values
over a multiprocessing queue and never sees the WebSocket.
"""

import asyncio
import multiprocessing as mp
import queue
import time
from collections import deque
from collections.abc import Callable
from typing import Any, Protocol

from bridge.v1 import bridge_pb2
from gesture_detection.app import main as run_detection
from gesture_detection.recognition_types import GestureSample
from websockets.exceptions import ConnectionClosed

from .diffuser import DiffuserController
from .error_log import ErrorLog
from .fan import FanController, McuFadeSender
from .gesture_codec import decode_bridge, decode_gesture, encode_message
from .gesture_delivery import DeliveryOutbox
from .runtime_settings import SettingsStore

TICK_SECONDS = 0.01
RECENT_OCCURRENCES = 20


class SampleSource(Protocol):
    def get(self, timeout: float) -> GestureSample | None: ...


class DetectionProcess:
    """gesture_detection running in a child process."""

    def __init__(self, target: Callable[..., None] = run_detection) -> None:
        self.samples: mp.Queue = mp.Queue()
        self.stop = mp.Event()
        self.process = mp.Process(
            target=target,
            kwargs={"samples": self.samples, "stop": self.stop},
            name="gesture-detection",
        )

    def start(self) -> None:
        self.process.start()

    def get(self, timeout: float) -> GestureSample | None:
        """Return None once recognition has exited normally (e.g. Esc).

        Raise queue.Empty on timeout and RuntimeError if recognition crashed.
        """
        try:
            sample = self.samples.get(timeout=timeout)
        except queue.Empty:
            if self.process.is_alive():
                raise
            if self.process.exitcode == 0:
                return None
            raise RuntimeError(
                f"gesture_detection exited with code {self.process.exitcode}"
            ) from None
        if not isinstance(sample, GestureSample):
            raise TypeError(f"Expected GestureSample, got {type(sample).__name__}")
        return sample

    def close(self) -> None:
        # Let recognition clean up its own workers; terminate() would orphan them.
        self.stop.set()
        if self.process.pid is not None:
            self.process.join(timeout=5)
            if self.process.is_alive():
                self.process.terminate()
                self.process.join()
        self.samples.close()
        self.samples.cancel_join_thread()


class BridgeRelay:
    def __init__(
        self,
        outbox: DeliveryOutbox,
        state_interval: float = 0.1,
        fan: FanController | None = None,
        diffuser: DiffuserController | None = None,
        settings: SettingsStore | None = None,
        errors: ErrorLog | None = None,
        mcu: McuFadeSender | None = None,
    ) -> None:
        self.outbox = outbox
        self.fan = fan or FanController()
        self.diffuser = diffuser or DiffuserController()
        self.settings = settings or SettingsStore()
        self.errors = errors or ErrorLog()
        # fan と diffuser が共有するマイコンへの送信役。設定画面で接続状態を出すだけに使う。
        self.mcu = mcu
        self.state_interval = state_interval
        # Called with each ACK before it settles the event; the debug GUI shows it.
        self.on_ack: Callable[[dict[str, Any]], None] | None = None
        # 設定画面に出す、最新の認識結果と、最近成立した所作(新しい順)。
        self.latest_sample: GestureSample | None = None
        self.recent_occurrences: deque[dict[str, Any]] = deque(
            maxlen=RECENT_OCCURRENCES
        )
        # Unity が最後に送った RuntimeStatus と、受け取った時刻(monotonic)。
        self.unity_status: bridge_pb2.RuntimeStatus | None = None
        self.unity_status_at: float | None = None
        self._connected = False

    @property
    def connected(self) -> bool:
        return self._connected

    async def pump(self, source: SampleSource) -> None:
        """Feed samples into the outbox until recognition exits."""
        while True:
            try:
                sample = await asyncio.to_thread(source.get, 0.5)
            except queue.Empty:
                continue
            if sample is None:
                return
            self._remember(sample)
            self.outbox.publish(sample, now=time.monotonic())

    def _remember(self, sample: GestureSample) -> None:
        self.latest_sample = sample
        for (gesture, _), accuracy in zip(
            sample.occurrences, sample.occurrence_accuracies, strict=True
        ):
            self.recent_occurrences.appendleft(
                {
                    "gesture": str(gesture),
                    "at": time.time(),
                    "action_accuracy": accuracy,
                }
            )

    async def serve(self, websocket: Any) -> None:
        if self._connected:
            await websocket.close(
                code=1013, reason="One Unity consumer is already connected"
            )
            return
        self._connected = True
        tasks = [
            asyncio.create_task(self._to_unity(websocket)),
            asyncio.create_task(self._from_unity(websocket)),
        ]
        try:
            done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                task.result()
        except ConnectionClosed:
            pass
        except (ValueError, TypeError, TimeoutError) as error:
            self.errors.record(
                "bridge",
                "error",
                f"Unity との接続を切りました: {type(error).__name__}: {error}",
            )
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            await websocket.close(code=1011, reason="Gesture connection closed")
            self._connected = False
            self.unity_status = None
            self.unity_status_at = None

    async def _to_unity(self, websocket: Any) -> None:
        next_state = 0.0
        reconnect = True
        settings_version = 0
        while True:
            now = time.monotonic()
            messages = []
            frames = []
            # 接続直後と、設定画面で変えたときに送る。
            if settings_version != self.settings.version:
                settings_version = self.settings.version
                frames.append(
                    bridge_pb2.BridgeEnvelope(
                        runtime_settings=self.settings.current.to_proto()
                    ).SerializeToString()
                )
            if now >= next_state:
                messages.append(self.outbox.state(now))
                # Unity がファンを使い始めるまでは、ファンの状態を送らない。
                if self.fan.active:
                    frames.append(self.fan.state())
                next_state = now + self.state_interval
            messages.extend(self.outbox.events(now, reconnect=reconnect))
            reconnect = False
            frames.extend(encode_message(message) for message in messages)
            for frame in frames:
                await asyncio.wait_for(websocket.send(frame), 0.5)
            await asyncio.sleep(TICK_SECONDS)

    async def _from_unity(self, websocket: Any) -> None:
        async for data in websocket:
            if not isinstance(data, bytes):
                raise TypeError("Expected a binary message")
            envelope = decode_bridge(data)
            kind = envelope.WhichOneof("payload")
            if kind == "fan_command":
                self.fan.command(envelope.fan_command)
            elif kind == "diffuser_press":
                self.diffuser.press(envelope.diffuser_press)
            elif kind == "runtime_status":
                self.unity_status = envelope.runtime_status
                self.unity_status_at = time.monotonic()
            elif kind == "unity_log":
                log = envelope.unity_log
                self.errors.record(
                    "unity",
                    "exception"
                    if log.level == bridge_pb2.UNITY_LOG_LEVEL_EXCEPTION
                    else "error",
                    log.message,
                    log.stack_trace,
                )
            elif kind == "gesture":
                ack = decode_gesture(envelope.gesture)
                if ack["type"] != "ack":
                    raise ValueError("Only ACKs are accepted in gesture mode")
                if self.on_ack is not None:
                    self.on_ack(ack)
                self.outbox.acknowledge(ack)
            else:
                raise ValueError("Unsupported message")
