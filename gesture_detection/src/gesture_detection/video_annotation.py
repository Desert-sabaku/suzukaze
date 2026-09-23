"""Frame-accurate video, interval, event, and landmark annotation tool."""

from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import json
import math
import time
import uuid
from importlib.resources import files
from pathlib import Path
from typing import Any, cast

import cv2
import numpy as np

SCHEMA_VERSION = 1
WINDOW = "Video annotation"
PANEL_WIDTH = 470
TIMELINE_HEIGHT = 190
CONTROL_HEIGHT = 58
COLORS = (
    (70, 170, 255),
    (100, 220, 120),
    (220, 150, 80),
    (210, 100, 210),
    (80, 210, 220),
    (180, 180, 80),
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def default_output_path(video: Path, project_directory: Path | None = None) -> Path:
    root = Path.cwd() if project_directory is None else project_directory
    return root / "shared" / "annotations" / video.parent.name / video.stem / "timeline.json"


def load_label_config(path: Path | None = None) -> dict[str, Any]:
    if path is None:
        text = files("gesture_detection").joinpath("annotation_labels.json").read_text("utf-8")
    else:
        text = path.read_text(encoding="utf-8")
    config = cast(dict[str, Any], json.loads(text))
    if config.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("Unsupported label configuration version")
    tracks = config.get("tracks")
    if not isinstance(tracks, list) or not tracks:
        raise ValueError("Label configuration must contain tracks")
    track_ids: set[str] = set()
    for track in tracks:
        if not isinstance(track, dict) or not isinstance(track.get("id"), str):
            raise ValueError("Invalid track configuration")
        if track["id"] in track_ids or not track.get("labels"):
            raise ValueError("Track IDs must be unique and contain labels")
        track_ids.add(track["id"])
    if not isinstance(config.get("events"), list) or not isinstance(config.get("landmarks"), list):
        raise ValueError("Label configuration must contain events and landmarks")
    return config


def inspect_video(video: Path) -> dict[str, Any]:
    capture = cv2.VideoCapture(str(video))
    try:
        if not capture.isOpened():
            raise ValueError(f"Cannot open video: {video}")
        total = round(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = capture.get(cv2.CAP_PROP_FPS)
        width = round(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = round(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
        if total < 1 or width < 1 or height < 1 or not math.isfinite(fps) or fps <= 0:
            raise ValueError(f"Invalid video metadata: {video}")
    finally:
        capture.release()
    return {
        "path": str(video.resolve()),
        "sha256": sha256(video),
        "fps": fps,
        "total_frames": total,
        "width": width,
        "height": height,
    }


def frame_timestamp(source: dict[str, Any], frame_id: int) -> float:
    return frame_id / float(source["fps"])


def new_timeline(video: Path, labels: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "source": inspect_video(video),
        "label_config": copy.deepcopy(labels),
        "intervals": [],
        "events": [],
        "landmarks": [],
        "ui": {"last_frame": 0},
    }


def _track_map(data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {track["id"]: track for track in data["label_config"]["tracks"]}


def validate_timeline(data: dict[str, Any]) -> None:
    if data.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("Unsupported timeline schema version")
    source = data.get("source")
    if not isinstance(source, dict) or int(source.get("total_frames", 0)) < 1:
        raise ValueError("Invalid timeline source")
    total = int(source["total_frames"])
    tracks = _track_map(data)
    for interval in data.get("intervals", []):
        track = tracks.get(interval.get("track"))
        if track is None or interval.get("label") not in track["labels"]:
            raise ValueError("Unknown interval label")
        start, end = interval.get("start_frame"), interval.get("end_frame")
        if not isinstance(start, int) or not isinstance(end, int) or not 0 <= start <= end < total:
            raise ValueError("Invalid interval frames")
    event_labels = set(data["label_config"]["events"])
    for event in data.get("events", []):
        if event.get("label") not in event_labels or not 0 <= event.get("frame_id", -1) < total:
            raise ValueError("Invalid event")
    landmark_labels = set(data["label_config"]["landmarks"])
    for item in data.get("landmarks", []):
        if (
            not 0 <= item.get("frame_id", -1) < total
            or not set(item.get("points", {})) <= landmark_labels
        ):
            raise ValueError("Invalid landmark frame")
        for point in item["points"].values():
            if point.get("status") not in {"marked", "uncertain", "absent"}:
                raise ValueError("Invalid landmark status")
            if point["status"] == "marked" and not all(
                isinstance(point.get(key), (int, float)) and math.isfinite(point[key])
                for key in ("x_px", "y_px")
            ):
                raise ValueError("Invalid landmark coordinates")

    for track_id, track in tracks.items():
        if not track.get("exclusive", True):
            continue
        ordered = sorted(
            (item for item in data.get("intervals", []) if item["track"] == track_id),
            key=lambda item: item["start_frame"],
        )
        if any(
            left["end_frame"] >= right["start_frame"]
            for left, right in zip(ordered, ordered[1:], strict=False)
        ):
            raise ValueError(f"Overlapping intervals in exclusive track: {track_id}")


def save_timeline(path: Path, data: dict[str, Any]) -> None:
    validate_timeline(data)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def load_timeline(path: Path, video: Path | None = None) -> dict[str, Any]:
    data = cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))
    validate_timeline(data)
    if video is not None:
        actual = inspect_video(video)
        source = data["source"]
        compared = ("sha256", "total_frames", "width", "height")
        if any(actual[key] != source.get(key) for key in compared):
            raise ValueError("Timeline belongs to a different video")
        source["path"] = str(video.resolve())
    return data


def active_intervals(data: dict[str, Any], frame_id: int) -> list[dict[str, Any]]:
    return [
        interval
        for interval in data["intervals"]
        if interval["start_frame"] <= frame_id <= interval["end_frame"]
    ]


class TimelineEditor:
    """Validated, undoable mutations for one timeline."""

    def __init__(self, data: dict[str, Any], output: Path):
        validate_timeline(data)
        self.data = data
        self.output = output
        self.undo_stack: list[dict[str, Any]] = []
        self.redo_stack: list[dict[str, Any]] = []

    def _change(self, callback) -> None:
        before = copy.deepcopy(self.data)
        callback()
        try:
            validate_timeline(self.data)
        except Exception:
            self.data = before
            raise
        self.undo_stack.append(before)
        self.redo_stack.clear()
        save_timeline(self.output, self.data)

    def set_last_frame(self, frame_id: int) -> None:
        self.data["ui"]["last_frame"] = frame_id

    def add_interval(self, track: str, label: str, first: int, second: int) -> str:
        start, end = sorted((first, second))
        identifier = uuid.uuid4().hex

        def mutate() -> None:
            self.data["intervals"].append(
                {
                    "id": identifier,
                    "track": track,
                    "label": label,
                    "start_frame": start,
                    "end_frame": end,
                    "start_timestamp": frame_timestamp(self.data["source"], start),
                    "end_timestamp": frame_timestamp(self.data["source"], end),
                }
            )

        self._change(mutate)
        return identifier

    def update_interval_edge(self, identifier: str, edge: str, frame_id: int) -> None:
        if edge not in {"start", "end"}:
            raise ValueError("Interval edge must be start or end")

        def mutate() -> None:
            interval = next(item for item in self.data["intervals"] if item["id"] == identifier)
            interval[f"{edge}_frame"] = frame_id
            if interval["start_frame"] > interval["end_frame"]:
                interval["start_frame"], interval["end_frame"] = (
                    interval["end_frame"],
                    interval["start_frame"],
                )
            interval["start_timestamp"] = frame_timestamp(
                self.data["source"], interval["start_frame"]
            )
            interval["end_timestamp"] = frame_timestamp(self.data["source"], interval["end_frame"])

        self._change(mutate)

    def add_event(self, label: str, frame_id: int) -> str:
        identifier = uuid.uuid4().hex

        def mutate() -> None:
            self.data["events"].append(
                {
                    "id": identifier,
                    "label": label,
                    "frame_id": frame_id,
                    "timestamp": frame_timestamp(self.data["source"], frame_id),
                }
            )

        self._change(mutate)
        return identifier

    def set_landmark(
        self, frame_id: int, landmark: str, status: str, point: tuple[int, int] | None = None
    ) -> None:
        def mutate() -> None:
            frames = self.data["landmarks"]
            item = next((row for row in frames if row["frame_id"] == frame_id), None)
            if item is None:
                item = {
                    "frame_id": frame_id,
                    "timestamp": frame_timestamp(self.data["source"], frame_id),
                    "points": {},
                }
                frames.append(item)
                frames.sort(key=lambda row: row["frame_id"])
            value: dict[str, Any] = {"status": status}
            if point is not None:
                value.update(x_px=point[0], y_px=point[1])
            item["points"][landmark] = value

        self._change(mutate)

    def set_absent(self, frame_id: int) -> None:
        def mutate() -> None:
            frames = self.data["landmarks"]
            item = next((row for row in frames if row["frame_id"] == frame_id), None)
            if item is None:
                item = {
                    "frame_id": frame_id,
                    "timestamp": frame_timestamp(self.data["source"], frame_id),
                    "points": {},
                }
                frames.append(item)
                frames.sort(key=lambda row: row["frame_id"])
            item["points"] = {
                name: {"status": "absent"} for name in self.data["label_config"]["landmarks"]
            }

        self._change(mutate)

    def delete(self, identifier: str) -> None:
        def mutate() -> None:
            for collection in (self.data["intervals"], self.data["events"]):
                for index, item in enumerate(collection):
                    if item["id"] == identifier:
                        del collection[index]
                        return
            raise ValueError("Annotation not found")

        self._change(mutate)

    def undo(self) -> bool:
        if not self.undo_stack:
            return False
        self.redo_stack.append(copy.deepcopy(self.data))
        self.data = self.undo_stack.pop()
        save_timeline(self.output, self.data)
        return True

    def redo(self) -> bool:
        if not self.redo_stack:
            return False
        self.undo_stack.append(copy.deepcopy(self.data))
        self.data = self.redo_stack.pop()
        save_timeline(self.output, self.data)
        return True


def import_legacy_landmarks(editor: TimelineEditor, location: Path) -> int:
    csv_path = location if location.suffix.lower() == ".csv" else location / "annotations.csv"
    source_path = csv_path.parent / "source.json"
    if not csv_path.is_file() or not source_path.is_file():
        raise ValueError(f"Legacy annotation session not found: {location}")
    metadata = json.loads(source_path.read_text(encoding="utf-8"))
    if metadata.get("sha256") != editor.data["source"]["sha256"]:
        raise ValueError("Legacy landmarks belong to a different video")
    imported = 0
    with csv_path.open(encoding="utf-8", newline="") as source:
        for row in csv.DictReader(source):
            status = row["status"]
            if status == "pending":
                continue
            point = None
            if status == "marked":
                point = (round(float(row["x_px"])), round(float(row["y_px"])))
            editor.set_landmark(int(row["frame_id"]), row["landmark"], status, point)
            imported += 1
    return imported


class VideoReader:
    def __init__(self, path: Path, total_frames: int):
        self.capture = cv2.VideoCapture(str(path))
        if not self.capture.isOpened():
            raise ValueError(f"Cannot open video: {path}")
        self.total_frames = total_frames
        self.loaded = -1

    def read(self, frame_id: int) -> np.ndarray[Any, Any]:
        frame_id = max(0, min(self.total_frames - 1, frame_id))
        if frame_id != self.loaded + 1:
            self.capture.set(cv2.CAP_PROP_POS_FRAMES, frame_id)
        ok, frame = self.capture.read()
        if not ok:
            raise ValueError(f"Cannot decode frame {frame_id}")
        decoded = round(self.capture.get(cv2.CAP_PROP_POS_FRAMES)) - 1
        if decoded != frame_id:
            self.capture.set(cv2.CAP_PROP_POS_FRAMES, frame_id)
            ok, frame = self.capture.read()
            decoded = round(self.capture.get(cv2.CAP_PROP_POS_FRAMES)) - 1
            if not ok or decoded != frame_id:
                raise ValueError(f"Frame seek mismatch: requested {frame_id}, decoded {decoded}")
        self.loaded = frame_id
        return frame

    def close(self) -> None:
        self.capture.release()


class AnnotationApp:
    def __init__(
        self, video: Path, editor: TimelineEditor, max_width: int, max_height: int
    ) -> None:
        self.video = video
        self.editor = editor
        self.data = editor.data
        self.total = int(self.data["source"]["total_frames"])
        self.reader = VideoReader(video, self.total)
        self.frame_id = max(0, min(self.total - 1, int(self.data["ui"].get("last_frame", 0))))
        self.frame = self.reader.read(self.frame_id)
        scale = min(1.0, max_width / self.frame.shape[1], max_height / self.frame.shape[0])
        self.image_width = max(1, round(self.frame.shape[1] * scale))
        self.image_height = max(1, round(self.frame.shape[0] * scale))
        self.playing = False
        self.speed = 1.0
        self.selected_label: tuple[str, str] | None = None
        self.interval_start: int | None = None
        self.selected_landmark: str | None = None
        self.selected_annotation: str | None = None
        self.message = "Select a label, then set START and END"
        self.buttons: list[tuple[tuple[int, int, int, int], str, Any]] = []
        self._last_tick = time.monotonic()
        self._trackbar_ready = False

    def seek(self, frame_id: int) -> None:
        target = max(0, min(self.total - 1, frame_id))
        if target != self.frame_id:
            self.frame = self.reader.read(target)
            self.frame_id = target
        self.editor.set_last_frame(self.frame_id)
        if self._trackbar_ready and cv2.getTrackbarPos("Frame", WINDOW) != self.frame_id:
            cv2.setTrackbarPos("Frame", WINDOW, self.frame_id)

    def _mutate(self, callback) -> None:
        try:
            callback()
            self.message = "Saved"
        except (ValueError, StopIteration) as error:
            self.message = str(error)
        finally:
            self.data = self.editor.data

    def _button(
        self,
        canvas: np.ndarray[Any, Any],
        rect: tuple[int, int, int, int],
        text: str,
        action: str,
        payload=None,
        active: bool = False,
    ) -> None:
        x1, y1, x2, y2 = rect
        color = (70, 110, 70) if active else (55, 55, 55)
        cv2.rectangle(canvas, (x1, y1), (x2, y2), color, -1)
        cv2.rectangle(canvas, (x1, y1), (x2, y2), (120, 120, 120), 1)
        cv2.putText(
            canvas, text, (x1 + 6, y1 + 19), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (245, 245, 245), 1
        )
        self.buttons.append((rect, action, payload))

    def _point_data(self) -> dict[str, Any]:
        item = next(
            (row for row in self.data["landmarks"] if row["frame_id"] == self.frame_id), None
        )
        return {} if item is None else item["points"]

    def render(self) -> np.ndarray[Any, Any]:
        self.buttons.clear()
        display = cv2.resize(self.frame, (self.image_width, self.image_height))
        points = self._point_data()
        for index, name in enumerate(self.data["label_config"]["landmarks"]):
            point = points.get(name)
            if point and point["status"] == "marked":
                x = round(point["x_px"] * self.image_width / self.frame.shape[1])
                y = round(point["y_px"] * self.image_height / self.frame.shape[0])
                cv2.circle(display, (x, y), 7, COLORS[index % len(COLORS)], -1)
                cv2.putText(
                    display,
                    str(index + 1),
                    (x + 7, y - 7),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.7,
                    (0, 0, 255),
                    2,
                )
        width = self.image_width + PANEL_WIDTH
        height = max(self.image_height, 690) + TIMELINE_HEIGHT
        canvas = np.zeros((height, width, 3), dtype=np.uint8)
        canvas[: self.image_height, : self.image_width] = display
        panel_x = self.image_width + 10
        cv2.putText(
            canvas,
            f"FRAME {self.frame_id + 1}/{self.total}",
            (panel_x, 28),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.75,
            (255, 255, 255),
            2,
        )
        timestamp = frame_timestamp(self.data["source"], self.frame_id)
        cv2.putText(
            canvas,
            f"{timestamp:.3f}s  speed {self.speed:g}x",
            (panel_x, 52),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (220, 220, 220),
            1,
        )
        x = panel_x
        for text, action, payload in (
            ("-10", "step", -10),
            ("-1", "step", -1),
            ("PLAY" if not self.playing else "PAUSE", "play", None),
            ("+1", "step", 1),
            ("+10", "step", 10),
        ):
            self._button(canvas, (x, 66, x + 82, 94), text, action, payload)
            x += 88
        y = 108
        cv2.putText(
            canvas, "INTERVALS", (panel_x, y), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (180, 220, 255), 1
        )
        y += 10
        label_index = 0
        for track in self.data["label_config"]["tracks"]:
            for label in track["labels"]:
                column = label_index % 2
                row = label_index // 2
                x1 = panel_x + column * 225
                y1 = y + row * 29
                payload = (track["id"], label)
                self._button(
                    canvas,
                    (x1, y1, x1 + 217, y1 + 25),
                    f"{track['id']}: {label}",
                    "label",
                    payload,
                    self.selected_label == payload,
                )
                label_index += 1
        y += ((label_index + 1) // 2) * 29 + 5
        for text, action in (("SET START", "start"), ("SET END", "end"), ("DELETE", "delete")):
            self._button(canvas, (panel_x, y, panel_x + 140, y + 28), text, action)
            panel_x += 147
        panel_x = self.image_width + 10
        y += 32
        self._button(
            canvas, (panel_x, y, panel_x + 214, y + 25), "MOVE SELECTED START HERE", "edit_start"
        )
        self._button(
            canvas, (panel_x + 225, y, panel_x + 439, y + 25), "MOVE SELECTED END HERE", "edit_end"
        )
        y += 37
        cv2.putText(
            canvas,
            "EVENTS (click to add)",
            (panel_x, y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (180, 220, 255),
            1,
        )
        y += 9
        for index, label in enumerate(self.data["label_config"]["events"]):
            column = index % 2
            row = index // 2
            x1 = panel_x + column * 225
            y1 = y + row * 29
            self._button(canvas, (x1, y1, x1 + 217, y1 + 25), label, "event", label)
        y += ((len(self.data["label_config"]["events"]) + 1) // 2) * 29 + 8
        cv2.putText(
            canvas, "LANDMARKS", (panel_x, y), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (180, 220, 255), 1
        )
        y += 9
        for index, label in enumerate(self.data["label_config"]["landmarks"]):
            column = index % 2
            row = index // 2
            x1 = panel_x + column * 225
            y1 = y + row * 29
            self._button(
                canvas,
                (x1, y1, x1 + 217, y1 + 25),
                f"{index + 1}: {label}",
                "landmark",
                label,
                self.selected_landmark == label,
            )
        y += 3 * 29 + 5
        self._button(canvas, (panel_x, y, panel_x + 140, y + 28), "UNCERTAIN", "uncertain")
        self._button(canvas, (panel_x + 147, y, panel_x + 287, y + 28), "ABSENT", "absent")
        cv2.putText(
            canvas,
            self.message[:62],
            (self.image_width + 10, min(height - TIMELINE_HEIGHT - 12, y + 52)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.48,
            (100, 220, 255),
            1,
        )
        self._draw_timeline(canvas, height - TIMELINE_HEIGHT, width)
        return canvas

    def _draw_timeline(self, canvas: np.ndarray[Any, Any], top: int, width: int) -> None:
        cv2.rectangle(canvas, (0, top), (width - 1, canvas.shape[0] - 1), (25, 25, 25), -1)
        tracks = self.data["label_config"]["tracks"]
        lane_height = max(20, (TIMELINE_HEIGHT - 32) // max(1, len(tracks)))
        for lane, track in enumerate(tracks):
            y1 = top + 24 + lane * lane_height
            cv2.putText(
                canvas,
                track["id"],
                (5, y1 + 14),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.42,
                (210, 210, 210),
                1,
            )
            for interval in self.data["intervals"]:
                if interval["track"] != track["id"]:
                    continue
                x1 = round(interval["start_frame"] / max(1, self.total - 1) * (width - 1))
                x2 = round(interval["end_frame"] / max(1, self.total - 1) * (width - 1))
                color = COLORS[lane % len(COLORS)]
                cv2.rectangle(canvas, (x1, y1), (max(x1 + 2, x2), y1 + lane_height - 4), color, -1)
                if interval["id"] == self.selected_annotation:
                    cv2.rectangle(
                        canvas,
                        (x1, y1),
                        (max(x1 + 2, x2), y1 + lane_height - 4),
                        (255, 255, 255),
                        2,
                    )
        for event in self.data["events"]:
            x = round(event["frame_id"] / max(1, self.total - 1) * (width - 1))
            color = (255, 180, 80) if event["id"] != self.selected_annotation else (255, 255, 255)
            cv2.line(canvas, (x, top + 20), (x, top + 31), color, 2)
        cursor_x = round(self.frame_id / max(1, self.total - 1) * (width - 1))
        cv2.line(canvas, (cursor_x, top), (cursor_x, canvas.shape[0] - 1), (0, 0, 255), 2)
        cv2.putText(
            canvas,
            "Click timeline to seek/select | Space play | A/D 1f | J/L 10f | S/E interval | Z/Y undo/redo | Q quit",
            (8, top + 17),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.47,
            (230, 230, 230),
            1,
        )

    def handle(self, action: str, payload: Any = None) -> None:
        if action == "step":
            self.playing = False
            self.seek(self.frame_id + cast(int, payload))
        elif action == "play":
            self.playing = not self.playing
            self._last_tick = time.monotonic()
        elif action == "label":
            selected = cast(tuple[str, str], payload)
            self.selected_label = selected
            self.selected_landmark = None
            self.message = f"Selected {selected[0]}: {selected[1]}"
        elif action == "start":
            if self.selected_label is None:
                self.message = "Select an interval label first"
            else:
                self.interval_start = self.frame_id
                self.message = f"Start set at frame {self.frame_id}"
        elif action == "end":
            if self.selected_label is None or self.interval_start is None:
                self.message = "Select a label and set START first"
            else:
                track, label = self.selected_label
                start = self.interval_start
                self._mutate(
                    lambda: setattr(
                        self,
                        "selected_annotation",
                        self.editor.add_interval(track, label, start, self.frame_id),
                    )
                )
                if self.message == "Saved":
                    self.interval_start = None
        elif action == "event":
            self._mutate(
                lambda: setattr(
                    self, "selected_annotation", self.editor.add_event(str(payload), self.frame_id)
                )
            )
        elif action == "landmark":
            self.selected_landmark = str(payload)
            self.selected_label = None
            self.message = f"Click {payload} on the image"
        elif action == "uncertain":
            if self.selected_landmark is None:
                self.message = "Select a landmark first"
            else:
                self._mutate(
                    lambda: self.editor.set_landmark(
                        self.frame_id, self.selected_landmark or "", "uncertain"
                    )
                )
        elif action == "absent":
            self._mutate(lambda: self.editor.set_absent(self.frame_id))
        elif action == "delete" and self.selected_annotation:
            selected = self.selected_annotation
            self._mutate(lambda: self.editor.delete(selected))
            if self.message == "Saved":
                self.selected_annotation = None
        elif action in {"edit_start", "edit_end"}:
            if self.selected_annotation is None or not any(
                item["id"] == self.selected_annotation for item in self.data["intervals"]
            ):
                self.message = "Select an interval on the timeline first"
            else:
                edge = "start" if action == "edit_start" else "end"
                selected = self.selected_annotation
                self._mutate(
                    lambda: self.editor.update_interval_edge(selected, edge, self.frame_id)
                )

    def click(self, event, x, y, flags, userdata) -> None:
        if event != cv2.EVENT_LBUTTONDOWN:
            return
        for (x1, y1, x2, y2), action, payload in reversed(self.buttons):
            if x1 <= x <= x2 and y1 <= y <= y2:
                self.handle(action, payload)
                return
        if x < self.image_width and y < self.image_height and self.selected_landmark:
            point = (
                min(self.frame.shape[1] - 1, round(x * self.frame.shape[1] / self.image_width)),
                min(self.frame.shape[0] - 1, round(y * self.frame.shape[0] / self.image_height)),
            )
            self._mutate(
                lambda: self.editor.set_landmark(
                    self.frame_id, self.selected_landmark or "", "marked", point
                )
            )
            return
        timeline_top = max(self.image_height, 690)
        if y >= timeline_top:
            self.playing = False
            self.seek(round(x / max(1, self.image_width + PANEL_WIDTH - 1) * (self.total - 1)))
            events = [item for item in self.data["events"] if item["frame_id"] == self.frame_id]
            if events:
                self.selected_annotation = events[-1]["id"]
            tracks = self.data["label_config"]["tracks"]
            lane_height = max(20, (TIMELINE_HEIGHT - 32) // max(1, len(tracks)))
            lane = (y - timeline_top - 24) // lane_height
            if 0 <= lane < len(tracks):
                matching = [
                    item
                    for item in active_intervals(self.data, self.frame_id)
                    if item["track"] == tracks[lane]["id"]
                ]
                if matching:
                    self.selected_annotation = matching[-1]["id"]

    def key(self, key: int) -> bool:
        if key in (27, ord("q")):
            return False
        mapping = {ord("a"): -1, ord("d"): 1, ord("j"): -10, ord("l"): 10}
        if key in mapping:
            self.handle("step", mapping[key])
        elif key == ord(" "):
            self.handle("play")
        elif key == ord("s"):
            self.handle("start")
        elif key == ord("e"):
            self.handle("end")
        elif key == ord("u"):
            self.handle("uncertain")
        elif key == ord("x"):
            self.handle("absent")
        elif key == ord("z"):
            if self.editor.undo():
                self.data = self.editor.data
                self.message = "Undo saved"
        elif key == ord("y"):
            if self.editor.redo():
                self.data = self.editor.data
                self.message = "Redo saved"
        elif key in (8, 127):
            self.handle("delete")
        elif key == ord("["):
            self.speed = max(0.25, self.speed / 2)
        elif key == ord("]"):
            self.speed = min(4.0, self.speed * 2)
        return True

    def run(self) -> None:
        cv2.namedWindow(WINDOW, cv2.WINDOW_NORMAL)
        cv2.setMouseCallback(WINDOW, self.click)
        cv2.createTrackbar("Frame", WINDOW, self.frame_id, self.total - 1, self.seek)
        self._trackbar_ready = True
        try:
            while True:
                if self.playing:
                    interval = 1.0 / (float(self.data["source"]["fps"]) * self.speed)
                    now = time.monotonic()
                    if now - self._last_tick >= interval:
                        if self.frame_id >= self.total - 1:
                            self.playing = False
                        else:
                            self.seek(self.frame_id + 1)
                        self._last_tick = now
                cv2.imshow(WINDOW, self.render())
                key = cv2.waitKey(10) & 0xFF
                if not self.key(key) or cv2.getWindowProperty(WINDOW, cv2.WND_PROP_VISIBLE) < 1:
                    break
        finally:
            self.editor.set_last_frame(self.frame_id)
            save_timeline(self.editor.output, self.editor.data)
            self.reader.close()
            cv2.destroyAllWindows()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--labels", type=Path)
    parser.add_argument("--import-landmarks", type=Path)
    parser.add_argument("--max-width", type=int, default=1280)
    parser.add_argument("--max-height", type=int, default=720)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if min(args.max_width, args.max_height) < 1:
        raise SystemExit("Display dimensions must be positive")
    if not args.video.is_file():
        raise SystemExit(f"Video not found: {args.video}")
    output = args.output or default_output_path(args.video)
    labels = load_label_config(args.labels)
    created = not output.exists()
    data = new_timeline(args.video, labels) if created else load_timeline(output, args.video)
    editor = TimelineEditor(data, output)
    if created:
        save_timeline(output, data)
        legacy = args.import_landmarks
        if legacy is None and (output.parent / "annotations.csv").is_file():
            legacy = output.parent
        if legacy is not None:
            imported = import_legacy_landmarks(editor, legacy)
            print(f"Imported {imported} landmark records")
    elif args.import_landmarks is not None:
        raise SystemExit("--import-landmarks is only valid when creating a timeline")
    AnnotationApp(args.video, editor, args.max_width, args.max_height).run()
    print(f"Annotations: {output}")


if __name__ == "__main__":
    main()
