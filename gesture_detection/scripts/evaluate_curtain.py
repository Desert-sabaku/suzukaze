#!/usr/bin/env python3
"""Compare pose configurations on the behind-curtain ``*btn.mp4`` clips.

The clip name supplies only a clip-level expected action.  Consequently the
reported action-frame ratio is a comparison proxy, not frame-level accuracy.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import time
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

import cv2
import mediapipe
import numpy as np
from modules import pose_worker
from modules.app import FrameClock, GestureApplication, PoseResult

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXPECTED_ACTIONS = {
    "ラムネbtn.mp4": "RAMUNE",
    "夕涼みbtn.mp4": "RELAXING",
    "扇ぎbtn.mp4": "FANNING",
    # GestureApplication._primary_action exposes UCHIMIZU as SPRINKLING.
    "打ち水btn.mp4": "SPRINKLING",
}
IMPORTANT_LANDMARKS = (0, 11, 12, 15, 16, 23, 24)


def weak_blur(frame: np.ndarray[Any, Any]) -> np.ndarray[Any, Any]:
    """Reduce fine mesh texture while retaining the body outline."""
    return cv2.GaussianBlur(frame, (5, 5), 1.2)


def identity(frame: np.ndarray[Any, Any]) -> np.ndarray[Any, Any]:
    return frame


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as model_file:
        for chunk in iter(lambda: model_file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def evaluate_clip(
    source: Path,
    expected_action: str,
    model_path: Path,
    preprocess: Callable[[np.ndarray[Any, Any]], np.ndarray[Any, Any]],
) -> dict[str, Any]:
    pose_worker.POSE_MODEL_PATH = model_path
    analyzer = pose_worker.PoseAnalyzer(running_mode="VIDEO")
    capture = cv2.VideoCapture(str(source))
    if not capture.isOpened():
        analyzer.close()
        raise RuntimeError(f"Unable to open {source}")

    clock = FrameClock(is_video=True)
    actions: Counter[str] = Counter()
    transitions: list[list[Any]] = []
    visibility_sum = 0.0
    important_visible = 0
    pose_frames = 0
    frames = 0
    first_expected_at: float | None = None
    inference_seconds = 0.0
    started = time.perf_counter()
    try:
        while True:
            success, frame = capture.read()
            if not success:
                break
            timestamp = clock.timestamp(capture)
            prepared = preprocess(frame)
            inference_started = time.perf_counter()
            result = cast(PoseResult, analyzer.process(prepared, timestamp, frames))
            inference_seconds += time.perf_counter() - inference_started
            if result.get("frame_id") != frames or result.get("timestamp") != timestamp:
                raise RuntimeError("Pose result metadata does not match its input frame")

            action = GestureApplication._primary_action(result)
            actions[action] += 1
            if not transitions or transitions[-1][1] != action:
                transitions.append([round(timestamp, 3), action])
            if action == expected_action and first_expected_at is None:
                first_expected_at = timestamp

            landmarks = result["landmarks"]
            if landmarks:
                pose_frames += 1
                visibility_sum += sum(point[2] for point in landmarks) / len(landmarks)
                important_visible += int(
                    all(landmarks[index][2] > 0.5 for index in IMPORTANT_LANDMARKS)
                )
            frames += 1
    finally:
        capture.release()
        analyzer.close()

    return {
        "source": source.name,
        "expected_action": expected_action,
        "frames": frames,
        "pose_frames": pose_frames,
        "pose_frame_ratio": pose_frames / frames if frames else 0.0,
        "mean_landmark_visibility": visibility_sum / pose_frames if pose_frames else 0.0,
        "important_landmarks_visible_frames": important_visible,
        "important_landmarks_visible_ratio": important_visible / frames if frames else 0.0,
        "expected_action_frames": actions[expected_action],
        "expected_action_ratio": actions[expected_action] / frames if frames else 0.0,
        "first_expected_action_seconds": first_expected_at,
        "actions": dict(sorted(actions.items())),
        "transitions": transitions,
        "inference_seconds": inference_seconds,
        "elapsed_seconds": time.perf_counter() - started,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample-dir", type=Path, default=PROJECT_ROOT / "sample_movies")
    parser.add_argument(
        "--lite-model", type=Path, default=PROJECT_ROOT / "pose_landmarker_lite.task"
    )
    parser.add_argument(
        "--full-model", type=Path, default=PROJECT_ROOT / "pose_landmarker_full.task"
    )
    parser.add_argument(
        "--output", type=Path, default=PROJECT_ROOT / "docs" / "curtain-comparison.json"
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    for path in (args.lite_model, args.full_model):
        if not path.is_file():
            raise FileNotFoundError(path)
    missing = [name for name in EXPECTED_ACTIONS if not (args.sample_dir / name).is_file()]
    if missing:
        raise FileNotFoundError(f"Missing sample clips: {', '.join(missing)}")

    conditions = (
        ("lite", args.lite_model, identity, "Lite / no preprocessing"),
        ("full", args.full_model, identity, "Full / no preprocessing"),
        ("lite_blur", args.lite_model, weak_blur, "Lite / Gaussian blur 5x5, sigma=1.2"),
    )
    report: dict[str, Any] = {
        "environment": {
            "python": platform.python_version(),
            "mediapipe": mediapipe.__version__,
            "opencv": cv2.__version__,
            "running_mode": "VIDEO",
            "important_landmark_indices": list(IMPORTANT_LANDMARKS),
        },
        "models": {
            "lite": {"file": args.lite_model.name, "sha256": sha256(args.lite_model)},
            "full": {"file": args.full_model.name, "sha256": sha256(args.full_model)},
        },
        "conditions": [],
    }
    for condition_id, model, preprocess, description in conditions:
        condition = {"id": condition_id, "description": description, "clips": []}
        for filename, expected in EXPECTED_ACTIONS.items():
            print(f"[{condition_id}] {filename}", flush=True)
            condition["clips"].append(
                evaluate_clip(args.sample_dir / filename, expected, model, preprocess)
            )
        report["conditions"].append(condition)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )


if __name__ == "__main__":
    main()
