#!/usr/bin/env python3
"""Evaluate pose conditions against manually annotated curtain frames."""

from __future__ import annotations

import argparse
import csv
import json
import math
import platform
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import mediapipe
import numpy as np

from gesture_detection import pose_worker

from .evaluate_curtain import PREPROCESSORS

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SESSION_PATTERN = re.compile(r"(aogi|ramune|uchimizu|yusuzumi)(\d+)_(\d+)-(\d+)")
LANDMARK_INDICES = {
    "left_shoulder": 11,
    "right_shoulder": 12,
    "left_wrist": 15,
    "right_wrist": 16,
    "left_hip": 23,
    "right_hip": 24,
}
# These sessions predate the ``absent`` annotation command. Their comments
# document which placeholder status was used for an absent subject.
LEGACY_ABSENT_STATUSES = {
    "aogi1_2-6": frozenset({"uncertain", "pending"}),
    "aogi2_2-5": frozenset({"pending"}),
}


@dataclass(frozen=True)
class Annotation:
    landmark: str
    status: str
    x_px: float | None
    y_px: float | None


@dataclass(frozen=True)
class AnnotatedFrame:
    session: str
    frame_id: int
    timestamp: float
    image: Path
    annotations: tuple[Annotation, ...]


def normalized_status(session: str, status: str) -> str:
    if status in LEGACY_ABSENT_STATUSES.get(session, ()):
        return "absent"
    return status


def load_frames(annotation_root: Path) -> list[AnnotatedFrame]:
    frames: list[AnnotatedFrame] = []
    for session_dir in sorted(annotation_root.iterdir()):
        if not session_dir.is_dir() or not SESSION_PATTERN.fullmatch(session_dir.name):
            continue
        grouped: dict[tuple[int, float], list[Annotation]] = defaultdict(list)
        with (session_dir / "annotations.csv").open(encoding="utf-8-sig", newline="") as source:
            for row in csv.DictReader(source):
                status = normalized_status(session_dir.name, row["status"])
                grouped[(int(row["frame_id"]), float(row["timestamp"]))].append(
                    Annotation(
                        landmark=row["landmark"],
                        status=status,
                        x_px=float(row["x_px"]) if status == "marked" else None,
                        y_px=float(row["y_px"]) if status == "marked" else None,
                    )
                )
        for (frame_id, timestamp), frame_annotations in sorted(grouped.items()):
            image = session_dir / f"frame_{frame_id:06d}.png"
            if not image.is_file():
                raise FileNotFoundError(image)
            frames.append(
                AnnotatedFrame(
                    session=session_dir.name,
                    frame_id=frame_id,
                    timestamp=timestamp,
                    image=image,
                    annotations=tuple(frame_annotations),
                )
            )
    if not frames:
        raise ValueError(f"No annotated curtain sessions found in {annotation_root}")
    return frames


def reference_scale(annotations: tuple[Annotation, ...], width: int, height: int) -> float:
    points = {
        item.landmark: np.asarray((item.x_px, item.y_px), dtype=float)
        for item in annotations
        if item.status == "marked"
    }
    for left, right in (
        ("left_shoulder", "right_shoulder"),
        ("left_hip", "right_hip"),
    ):
        if left in points and right in points:
            scale = float(np.linalg.norm(points[left] - points[right]))
            if scale > 0:
                return scale
    return math.hypot(width, height)


def evaluate(
    frames: list[AnnotatedFrame],
    model: Path,
    preprocess_name: str,
    detection_confidence: float,
    presence_confidence: float,
) -> dict[str, Any]:
    pose_worker.POSE_MODEL_PATH = model
    analyzer = pose_worker.PoseAnalyzer(
        running_mode="IMAGE",
        detection_confidence=detection_confidence,
        presence_confidence=presence_confidence,
    )
    preprocess = PREPROCESSORS[preprocess_name]
    presence_frames = absent_frames = detected_presence_frames = false_positive_frames = 0
    marked_points = detected_points = 0
    errors: list[float] = []
    normalized_errors: list[float] = []
    by_landmark: dict[str, list[float]] = defaultdict(list)
    marked_by_landmark: Counter[str] = Counter()
    by_session: dict[str, dict[str, int]] = defaultdict(
        lambda: {
            "presence_frames": 0,
            "detected_presence_frames": 0,
            "absent_frames": 0,
            "false_positive_frames": 0,
        }
    )
    try:
        for frame_number, annotated in enumerate(frames):
            image = cv2.imread(str(annotated.image))
            if image is None:
                raise ValueError(f"Cannot read {annotated.image}")
            height, width = image.shape[:2]
            result = analyzer.process(preprocess(image), annotated.timestamp, frame_number)
            landmarks = result["landmarks"]
            present = any(item.status in {"marked", "uncertain"} for item in annotated.annotations)
            session_counts = by_session[annotated.session]
            if present:
                presence_frames += 1
                session_counts["presence_frames"] += 1
                if landmarks:
                    detected_presence_frames += 1
                    session_counts["detected_presence_frames"] += 1
            else:
                absent_frames += 1
                session_counts["absent_frames"] += 1
                if landmarks:
                    false_positive_frames += 1
                    session_counts["false_positive_frames"] += 1

            scale = reference_scale(annotated.annotations, width, height)
            for item in annotated.annotations:
                if item.status != "marked":
                    continue
                marked_points += 1
                marked_by_landmark[item.landmark] += 1
                if not landmarks:
                    continue
                detected_points += 1
                predicted = landmarks[LANDMARK_INDICES[item.landmark]]
                error = math.hypot(
                    predicted[0] * width - item.x_px, predicted[1] * height - item.y_px
                )
                errors.append(error)
                normalized = error / scale
                normalized_errors.append(normalized)
                by_landmark[item.landmark].append(normalized)
    finally:
        analyzer.close()

    return {
        "model": model.name,
        "preprocess": preprocess_name,
        "confidence": {"detection": detection_confidence, "presence": presence_confidence},
        "frames": len(frames),
        "presence_frames": presence_frames,
        "pose_recall": detected_presence_frames / presence_frames if presence_frames else None,
        "absent_frames": absent_frames,
        "false_positive_rate": false_positive_frames / absent_frames if absent_frames else None,
        "marked_points": marked_points,
        "point_detection_rate": detected_points / marked_points if marked_points else None,
        "mean_error_px_on_detected": float(np.mean(errors)) if errors else None,
        "median_normalized_error_on_detected": (
            float(np.median(normalized_errors)) if errors else None
        ),
        "pck_at_0_2": (
            sum(error <= 0.2 for error in normalized_errors) / marked_points
            if marked_points
            else None
        ),
        "per_landmark": {
            name: {
                "marked_points": marked_by_landmark[name],
                "detected_points": len(values),
                "median_normalized_error_on_detected": (
                    float(np.median(values)) if values else None
                ),
                "pck_at_0_2": (
                    sum(error <= 0.2 for error in values) / marked_by_landmark[name]
                    if marked_by_landmark[name]
                    else None
                ),
            }
            for name in sorted(marked_by_landmark)
            for values in (by_landmark[name],)
        },
        "per_session": dict(sorted(by_session.items())),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--annotations", type=Path, default=PROJECT_ROOT / "shared" / "annotations")
    parser.add_argument("--model", type=Path, default=PROJECT_ROOT / "pose_landmarker_lite.task")
    parser.add_argument(
        "--preprocess",
        action="append",
        choices=sorted(PREPROCESSORS),
        help="Repeat to compare conditions; defaults to identity.",
    )
    parser.add_argument("--detection-confidence", type=float, default=0.5)
    parser.add_argument("--presence-confidence", type=float, default=0.5)
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "shared" / "results" / "landmark-annotations.json",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not args.model.is_file():
        raise FileNotFoundError(args.model)
    for value in (args.detection_confidence, args.presence_confidence):
        if not 0 <= value <= 1:
            raise ValueError("Confidence thresholds must be between 0 and 1")
    frames = load_frames(args.annotations)
    report = {
        "environment": {
            "python": platform.python_version(),
            "mediapipe": mediapipe.__version__,
            "opencv": cv2.__version__,
        },
        "annotations": {
            "root": str(args.annotations),
            "sessions": len({frame.session for frame in frames}),
            "frames": len(frames),
            "legacy_absent_statuses": {
                session: sorted(statuses) for session, statuses in LEGACY_ABSENT_STATUSES.items()
            },
        },
        "conditions": [
            evaluate(
                frames,
                args.model,
                preprocess,
                args.detection_confidence,
                args.presence_confidence,
            )
            for preprocess in (args.preprocess or ["identity"])
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Report: {args.output}")


if __name__ == "__main__":
    main()
