#!/usr/bin/env python3
"""Measure Hand Landmarker availability in the labelled Ramune intervals."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import platform
from collections import Counter
from pathlib import Path
from typing import Any

import cv2
import mediapipe as mp
import numpy as np
from mediapipe.tasks import python
from mediapipe.tasks.python import vision

from gesture_detection.app import FrameClock

from .evaluate_action_intervals import discover_clips, parse_clip_name
from .evaluate_curtain import PREPROCESSORS
from .evaluate_landmark_annotations import (
    BACKGROUND_PREPROCESSORS,
    background_preprocess,
    build_session_backgrounds,
    load_frames,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PALM_INDICES = (0, 5, 9, 13, 17)


def palm_center(hand: Any, aspect_ratio: float) -> np.ndarray[Any, Any]:
    return np.mean(
        np.asarray([(hand[index].x * aspect_ratio, hand[index].y) for index in PALM_INDICES]),
        axis=0,
    )


def sha256(path: Path) -> str:
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def evaluate_clip(
    source: Path,
    environment: str,
    landmarker: Any,
    preprocess_name: str,
    sample_fps: float,
    background: np.ndarray[Any, Any] | None,
) -> dict[str, Any]:
    expected, take, interval_start, interval_end = parse_clip_name(source)
    if expected != "RAMUNE":
        raise ValueError(f"Expected a Ramune clip, got {source.name}")
    capture = cv2.VideoCapture(str(source))
    if not capture.isOpened():
        raise RuntimeError(f"Unable to open {source}")
    clock = FrameClock(is_video=True)
    preprocess = PREPROCESSORS.get(preprocess_name)
    interval_frames = any_hand_frames = two_hand_frames = opposite_handed_frames = 0
    hand_counts: Counter[int] = Counter()
    palm_distances: list[float] = []
    next_sample_at = 0.0
    try:
        while True:
            ok, frame = capture.read()
            if not ok:
                break
            timestamp = clock.timestamp(capture)
            if timestamp + 1e-9 < next_sample_at:
                continue
            next_sample_at = timestamp + 1 / sample_fps
            if preprocess is not None:
                prepared = preprocess(frame)
            else:
                if background is None:
                    raise ValueError("Background preprocessing requires a reference image")
                prepared = background_preprocess(frame, background, preprocess_name)
            if not interval_start <= timestamp <= interval_end:
                continue
            rgb = cv2.cvtColor(prepared, cv2.COLOR_BGR2RGB)
            image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
            result = landmarker.detect_for_video(image, int(timestamp * 1000))
            count = len(result.hand_landmarks)
            interval_frames += 1
            hand_counts[count] += 1
            any_hand_frames += int(count >= 1)
            two_hand_frames += int(count >= 2)
            if count >= 2:
                labels = {
                    category.category_name
                    for handedness in result.handedness[:2]
                    for category in handedness[:1]
                }
                opposite_handed_frames += int(labels == {"Left", "Right"})
                aspect_ratio = prepared.shape[1] / prepared.shape[0]
                centers = [palm_center(hand, aspect_ratio) for hand in result.hand_landmarks[:2]]
                palm_distances.append(float(np.linalg.norm(centers[0] - centers[1])))
    finally:
        capture.release()
    return {
        "environment": environment,
        "source": source.name,
        "take": take,
        "expected_interval": [interval_start, interval_end],
        "interval_frames": interval_frames,
        "hand_counts": {str(key): value for key, value in sorted(hand_counts.items())},
        "any_hand_ratio": any_hand_frames / interval_frames if interval_frames else None,
        "two_hand_ratio": two_hand_frames / interval_frames if interval_frames else None,
        "opposite_handed_ratio": (
            opposite_handed_frames / interval_frames if interval_frames else None
        ),
        "palm_distance": {
            "count": len(palm_distances),
            "median": float(np.median(palm_distances)) if palm_distances else None,
            "minimum": min(palm_distances) if palm_distances else None,
        },
    }


def aggregate(clips: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for environment in sorted({clip["environment"] for clip in clips}):
        selected = [clip for clip in clips if clip["environment"] == environment]
        frames = sum(clip["interval_frames"] for clip in selected)
        any_frames = sum(
            sum(count for hands, count in clip["hand_counts"].items() if int(hands) >= 1)
            for clip in selected
        )
        two_frames = sum(
            sum(count for hands, count in clip["hand_counts"].items() if int(hands) >= 2)
            for clip in selected
        )
        rows.append(
            {
                "environment": environment,
                "clips": len(selected),
                "interval_frames": frames,
                "any_hand_ratio": any_frames / frames if frames else None,
                "two_hand_ratio": two_frames / frames if frames else None,
                "clips_with_two_hands": sum(clip["two_hand_ratio"] > 0 for clip in selected),
            }
        )
    return rows


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--video-root", type=Path, default=PROJECT_ROOT / "shared" / "videos")
    parser.add_argument("--annotations", type=Path, default=PROJECT_ROOT / "shared" / "annotations")
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument(
        "--preprocess",
        choices=sorted((*PREPROCESSORS, *BACKGROUND_PREPROCESSORS)),
        default="identity",
    )
    parser.add_argument("--sample-fps", type=float, default=10.0)
    parser.add_argument("--detection-confidence", type=float, default=0.5)
    parser.add_argument("--presence-confidence", type=float, default=0.5)
    parser.add_argument("--tracking-confidence", type=float, default=0.5)
    parser.add_argument("--environment", choices=("behind", "without"), action="append")
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "shared" / "results" / "hand-landmarker.json",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not args.model.is_file():
        raise FileNotFoundError(args.model)
    if not math.isfinite(args.sample_fps) or args.sample_fps <= 0:
        raise ValueError("Sample FPS must be positive and finite")
    confidences = (
        args.detection_confidence,
        args.presence_confidence,
        args.tracking_confidence,
    )
    if any(not 0 <= value <= 1 for value in confidences):
        raise ValueError("Confidence thresholds must be between 0 and 1")
    selected = [
        (environment, source)
        for environment, source in discover_clips(args.video_root)
        if parse_clip_name(source)[0] == "RAMUNE"
        and (not args.environment or environment in args.environment)
    ]
    if not selected:
        raise ValueError("No Ramune clips match the requested filters")
    backgrounds = None
    if args.preprocess in BACKGROUND_PREPROCESSORS:
        if {environment for environment, _ in selected} != {"behind"}:
            raise ValueError("Background preprocessing is available only with --environment behind")
        backgrounds = build_session_backgrounds(load_frames(args.annotations))

    options = vision.HandLandmarkerOptions(
        base_options=python.BaseOptions(model_asset_path=str(args.model)),
        running_mode=vision.RunningMode.VIDEO,
        num_hands=2,
        min_hand_detection_confidence=args.detection_confidence,
        min_hand_presence_confidence=args.presence_confidence,
        min_tracking_confidence=args.tracking_confidence,
    )
    clips = []
    for environment, source in selected:
        print(f"[{environment}] {source.name}", flush=True)
        with vision.HandLandmarker.create_from_options(options) as landmarker:
            clips.append(
                evaluate_clip(
                    source,
                    environment,
                    landmarker,
                    args.preprocess,
                    args.sample_fps,
                    backgrounds[source.stem] if backgrounds is not None else None,
                )
            )
    report = {
        "environment": {
            "python": platform.python_version(),
            "mediapipe": mp.__version__,
            "opencv": cv2.__version__,
        },
        "condition": {
            "model": args.model.name,
            "model_sha256": sha256(args.model),
            "preprocess": args.preprocess,
            "sample_fps": args.sample_fps,
            "detection_confidence": args.detection_confidence,
            "presence_confidence": args.presence_confidence,
            "tracking_confidence": args.tracking_confidence,
        },
        "clips": clips,
        "aggregates": aggregate(clips),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Report: {args.output}")


if __name__ == "__main__":
    main()
