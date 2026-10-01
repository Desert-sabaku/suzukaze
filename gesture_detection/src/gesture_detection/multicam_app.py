"""Opt-in dual-camera application and recorder-session replay."""

import json
import math
import time
from contextlib import ExitStack
from multiprocessing.queues import Queue
from multiprocessing.synchronize import Event
from typing import TextIO

import cv2
import numpy as np

from . import config
from .app import GestureApplication
from .multicam_fusion import MultiCameraFusion
from .multicam_input import Frame, LiveInputs, Preview, RecordedInput, load_session
from .pose_worker import PoseAnalyzer
from .recognition_types import GestureSample, PoseResult
from .rendering import draw_ramune_guide
from .video_output import AsyncVideoWriter

WINDOW = "Gesture Recognition - two cameras"
PANEL_WIDTH, PANEL_HEIGHT, HEADER_HEIGHT = 640, 360, 72


def compose_preview(previews: dict[int, Preview], fused: PoseResult) -> Frame:
    canvas = np.zeros((PANEL_HEIGHT + HEADER_HEIGHT, PANEL_WIDTH * 2, 3), dtype=np.uint8)
    for slot, camera in enumerate(config.MULTICAM_CAMERA_INDICES):
        value = previews.get(slot)
        if value is not None:
            frame, result = value
            image = GestureApplication._annotate_frame(frame, result)
            current = fused.get("current", {"gesture": "NONE", "tracking": False})["gesture"]
            if current == "RAMUNE":
                draw_ramune_guide(image, "OPENED")
            elif "RAMUNE" in fused.get("release_pending", ()):
                draw_ramune_guide(
                    image,
                    "WAIT_RELEASE",
                    release_message="Ramune: lower pressing hand or separate hands",
                )
            elif (
                "RAMUNE" in fused.get("locked_events", ())
                and result.get("ramune_state") == "WAIT_RELEASE"
            ):
                draw_ramune_guide(image, "IDLE")
            scale = min(PANEL_WIDTH / image.shape[1], PANEL_HEIGHT / image.shape[0])
            width, height = (
                max(1, round(image.shape[1] * scale)),
                max(1, round(image.shape[0] * scale)),
            )
            image = cv2.resize(image, (width, height))
            x = slot * PANEL_WIDTH + (PANEL_WIDTH - width) // 2
            y = HEADER_HEIGHT + (PANEL_HEIGHT - height) // 2
            canvas[y : y + height, x : x + width] = image
        timestamp = value[1].get("timestamp", -math.inf) if value else -math.inf
        stale = fused.get("timestamp", 0) - timestamp > config.MULTICAM_MAX_AGE_SECONDS
        text = f"Camera {camera} ({'subject' if config.MULTICAM_SELECT_SUBJECT[slot] else 'full'})"
        cv2.putText(
            canvas,
            text + (" - stale" if stale else ""),
            (slot * PANEL_WIDTH + 10, 58),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (0, 180, 255) if stale else (200, 200, 200),
            1,
        )
    gesture = fused.get("current", {"gesture": "NONE", "tracking": False})["gesture"]
    locked = ",".join(fused.get("locked_events", ())) or "none"
    cv2.putText(
        canvas,
        f"Combined: {gesture} | event locks: {locked}",
        (10, 27),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        (0, 255, 255),
        2,
    )
    return canvas


class MultiCameraApplication:
    def __init__(
        self, samples: Queue[GestureSample] | None = None, stop: Event | None = None
    ) -> None:
        self.samples = samples
        self.stop = stop
        self._window_created = False

    def _exit_requested(self) -> bool:
        if self.stop is not None and self.stop.is_set():
            return True
        if config.MULTICAM_HEADLESS:
            return False
        if cv2.waitKey(1) & 0xFF == 27:
            return True
        if not self._window_created:
            return False
        try:
            return cv2.getWindowProperty(WINDOW, cv2.WND_PROP_VISIBLE) < 1
        except cv2.error:
            return True

    def _show(self, image: Frame) -> None:
        if not config.MULTICAM_HEADLESS:
            cv2.imshow(WINDOW, image)
            self._window_created = True

    @staticmethod
    def _trace(stack: ExitStack) -> TextIO | None:
        path = config.MULTICAM_TRACE_PATH
        if path is None:
            return None
        path.parent.mkdir(parents=True, exist_ok=True)
        return stack.enter_context(path.open("w", encoding="utf-8"))

    @staticmethod
    def _write_trace(
        trace: TextIO | None, fused: PoseResult, latest: dict[int, PoseResult]
    ) -> None:
        if trace is not None:
            trace.write(json.dumps({"fused": fused, "views": latest}, allow_nan=False) + "\n")

    def run(self) -> None:
        try:
            if config.MULTICAM_VIDEO_SESSION is not None:
                self._replay()
            else:
                self._live()
        finally:
            if not config.MULTICAM_HEADLESS:
                cv2.destroyAllWindows()

    def _replay(self) -> None:
        assert config.MULTICAM_VIDEO_SESSION is not None
        views = load_session(config.MULTICAM_VIDEO_SESSION, config.MULTICAM_CAMERA_INDICES)
        protected = {
            config.MULTICAM_VIDEO_SESSION.resolve(),
            *(view.path.resolve() for view in views),
        }
        output_path = config.VIDEO_OUTPUT_PATH.resolve()
        trace_path = config.MULTICAM_TRACE_PATH.resolve() if config.MULTICAM_TRACE_PATH else None
        if output_path in protected or trace_path in protected or trace_path == output_path:
            raise ValueError(
                "Replay output and trace must be distinct from the session inputs and each other"
            )
        fusion = MultiCameraFusion()
        previews: dict[int, Preview] = {}
        with ExitStack() as stack:
            inputs, analyzers = [], []
            for slot, view in enumerate(views):
                source = RecordedInput(view)
                stack.callback(source.close)
                inputs.append(source)
                analyzer = PoseAnalyzer(
                    running_mode="VIDEO",
                    select_subject=config.MULTICAM_SELECT_SUBJECT[slot],
                    ramune_detector="rules",
                    source_fps=view.fps,
                    recognition_profile="multicam",
                )
                stack.callback(analyzer.close)
                analyzers.append(analyzer)
            pending = [source.read() for source in inputs]
            trace = self._trace(stack)
            config.VIDEO_OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
            writer = cv2.VideoWriter(
                str(config.VIDEO_OUTPUT_PATH),
                cv2.VideoWriter.fourcc(*"mp4v"),
                config.MULTICAM_FUSION_FPS,
                (PANEL_WIDTH * 2, PANEL_HEIGHT + HEADER_HEIGHT),
            )
            if not writer.isOpened():
                writer.release()
                raise RuntimeError(f"Unable to open output {config.VIDEO_OUTPUT_PATH}")
            try:
                output = AsyncVideoWriter(writer, config.VIDEO_OUTPUT_BUFFER_FRAMES)
            except BaseException:
                writer.release()
                raise
            stack.callback(output.release)
            # Include an EOF tick so inputs faster than the output grid are
            # drained too; no trailing native frame/event is silently skipped.
            for tick in range(math.ceil(views[0].duration * config.MULTICAM_FUSION_FPS) + 1):
                now = min(tick / config.MULTICAM_FUSION_FPS, views[0].duration)
                for slot in (0, 1):
                    sample = pending[slot]
                    while sample is not None and sample[1] <= now + 1e-9:
                        frame, timestamp, frame_id = sample
                        result = analyzers[slot].process(frame, timestamp, frame_id)
                        fusion.submit(slot, result)
                        previews[slot] = frame, result
                        sample = inputs[slot].read()
                        pending[slot] = sample
                fused = fusion.advance(now)
                self._write_trace(trace, fused, fusion.latest)
                image = compose_preview(previews, fused)
                output.write(image)
                self._show(image)
                if self._exit_requested():
                    break

    def _live(self) -> None:
        fusion = MultiCameraFusion()
        previews: dict[int, Preview] = {}
        with ExitStack() as stack:
            inputs = LiveInputs(config.MULTICAM_CAMERA_INDICES, config.MULTICAM_SELECT_SUBJECT)
            inputs.start()
            stack.callback(inputs.close)
            trace = self._trace(stack)
            next_tick = time.monotonic()
            while True:
                now = time.monotonic()
                if now >= next_tick:
                    for slot, result in inputs.poll():
                        fusion.submit(slot, result)
                    fused = fusion.advance(now)
                    if self.samples is not None and fusion.latest:
                        self.samples.put(
                            GestureSample.from_result(fused, fused.get("observed_at", now))
                        )
                    self._write_trace(trace, fused, fusion.latest)
                    previews = inputs.latest_previews(previews)
                    if not config.MULTICAM_HEADLESS:
                        self._show(compose_preview(previews, fused))
                    next_tick = now + 1 / config.MULTICAM_FUSION_FPS
                if self._exit_requested():
                    break
                time.sleep(0.001)
