#!/usr/bin/env python3
"""Compare pose configurations on the behind-curtain ``*btn.mp4`` clips.

The clip name supplies only a clip-level expected action.  Consequently the
reported action-frame ratio is a comparison proxy, not frame-level accuracy.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import platform
import time
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
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
# The first three clips contain the target action throughout.  The Uchimizu
# clip has a pause and another person enters during the middle section.
EXPECTED_INTERVALS = {
    "ラムネbtn.mp4": ((0.0, math.inf),),
    "夕涼みbtn.mp4": ((0.0, math.inf),),
    "扇ぎbtn.mp4": ((0.0, math.inf),),
    "打ち水btn.mp4": ((0.0, 16.0), (23.0, math.inf)),
}


@dataclass(frozen=True)
class Condition:
    id: str
    description: str
    model_path: Path
    preprocess: Callable[[np.ndarray[Any, Any]], np.ndarray[Any, Any]]
    detection_confidence: float = 0.5
    presence_confidence: float = 0.5
    tracking_confidence: float = 0.5


def weak_blur(frame: np.ndarray[Any, Any]) -> np.ndarray[Any, Any]:
    """Reduce fine mesh texture while retaining the body outline."""
    return cv2.GaussianBlur(frame, (5, 5), 1.2)


def identity(frame: np.ndarray[Any, Any]) -> np.ndarray[Any, Any]:
    return frame


def half_resolution(frame: np.ndarray[Any, Any]) -> np.ndarray[Any, Any]:
    """Suppress fine mesh detail with antialiased spatial downsampling."""
    return cv2.resize(frame, None, fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA)


def clahe_luminance(frame: np.ndarray[Any, Any]) -> np.ndarray[Any, Any]:
    """Increase local subject contrast without changing chroma directly."""
    lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
    luminance, a_channel, b_channel = cv2.split(lab)
    enhanced = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(luminance)
    return cv2.cvtColor(cv2.merge((enhanced, a_channel, b_channel)), cv2.COLOR_LAB2BGR)


def half_resolution_clahe(frame: np.ndarray[Any, Any]) -> np.ndarray[Any, Any]:
    return clahe_luminance(half_resolution(frame))


def center_mask(frame: np.ndarray[Any, Any]) -> np.ndarray[Any, Any]:
    """Remove side-background people while preserving the original geometry."""
    width = frame.shape[1]
    left = round(width * 0.18)
    right = round(width * 0.82)
    masked = np.full_like(frame, np.median(frame, axis=(0, 1)).astype(frame.dtype))
    masked[:, left:right] = frame[:, left:right]
    return masked


def center_mask_half_resolution(frame: np.ndarray[Any, Any]) -> np.ndarray[Any, Any]:
    return half_resolution(center_mask(frame))


PREPROCESSORS = {
    "identity": identity,
    "weak_blur": weak_blur,
    "half_resolution": half_resolution,
    "clahe": clahe_luminance,
    "half_resolution_clahe": half_resolution_clahe,
    "center_mask": center_mask,
    "center_mask_half_resolution": center_mask_half_resolution,
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as model_file:
        for chunk in iter(lambda: model_file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def evaluate_clip(
    source: Path,
    expected_action: str,
    condition: Condition,
) -> dict[str, Any]:
    pose_worker.POSE_MODEL_PATH = condition.model_path
    analyzer = pose_worker.PoseAnalyzer(
        running_mode="VIDEO",
        detection_confidence=condition.detection_confidence,
        presence_confidence=condition.presence_confidence,
        tracking_confidence=condition.tracking_confidence,
    )
    capture = cv2.VideoCapture(str(source))
    if not capture.isOpened():
        analyzer.close()
        raise RuntimeError(f"Unable to open {source}")

    clock = FrameClock(is_video=True)
    actions: Counter[str] = Counter()
    transitions: list[list[Any]] = []
    visibility_sum = 0.0
    important_visible = 0
    important_jumps: list[float] = []
    previous_important: np.ndarray[Any, Any] | None = None
    pose_frames = 0
    frames = 0
    evaluated_frames = 0
    expected_action_evaluated_frames = 0
    other_action_evaluated_frames = 0
    first_expected_at: float | None = None
    inference_seconds = 0.0
    started = time.perf_counter()
    try:
        while True:
            success, frame = capture.read()
            if not success:
                break
            timestamp = clock.timestamp(capture)
            prepared = condition.preprocess(frame)
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

            in_expected_interval = any(
                start <= timestamp <= end for start, end in EXPECTED_INTERVALS[source.name]
            )
            if in_expected_interval:
                evaluated_frames += 1
                expected_action_evaluated_frames += int(action == expected_action)
                other_action_evaluated_frames += int(action not in {expected_action, "NONE"})

            landmarks = result["landmarks"]
            if landmarks:
                pose_frames += 1
                visibility_sum += sum(point[2] for point in landmarks) / len(landmarks)
                important_visible += int(
                    all(landmarks[index][2] > 0.5 for index in IMPORTANT_LANDMARKS)
                )
                current_important = np.asarray(
                    [(landmarks[index][0], landmarks[index][1]) for index in IMPORTANT_LANDMARKS]
                )
                if previous_important is not None:
                    important_jumps.extend(
                        np.linalg.norm(current_important - previous_important, axis=1).tolist()
                    )
                previous_important = current_important
            else:
                previous_important = None
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
        "evaluated_frames": evaluated_frames,
        "expected_action_evaluated_frames": expected_action_evaluated_frames,
        "expected_action_evaluated_ratio": (
            expected_action_evaluated_frames / evaluated_frames if evaluated_frames else 0.0
        ),
        "other_action_evaluated_frames": other_action_evaluated_frames,
        "mean_important_landmark_jump": (
            float(np.mean(important_jumps)) if important_jumps else None
        ),
        "p95_important_landmark_jump": (
            float(np.percentile(important_jumps, 95)) if important_jumps else None
        ),
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
    parser.add_argument(
        "--condition",
        action="append",
        help="Condition ID to run; repeat to select several. Defaults to all conditions.",
    )
    parser.add_argument(
        "--clip",
        action="append",
        help="Clip filename to run; repeat to select several. Defaults to all clips.",
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
        Condition("lite", "Lite / no preprocessing", args.lite_model, identity),
        Condition("full", "Full / no preprocessing", args.full_model, identity),
        Condition(
            "lite_blur",
            "Lite / Gaussian blur 5x5, sigma=1.2",
            args.lite_model,
            weak_blur,
        ),
        Condition(
            "full_conf035",
            "Full / detection and presence confidence 0.35",
            args.full_model,
            identity,
            detection_confidence=0.35,
            presence_confidence=0.35,
        ),
        Condition(
            "full_conf020",
            "Full / detection and presence confidence 0.20",
            args.full_model,
            identity,
            detection_confidence=0.2,
            presence_confidence=0.2,
        ),
        Condition(
            "full_half",
            "Full / area downsample to 50%",
            args.full_model,
            half_resolution,
        ),
        Condition("full_clahe", "Full / luminance CLAHE", args.full_model, clahe_luminance),
        Condition(
            "full_half_clahe",
            "Full / area downsample to 50% then luminance CLAHE",
            args.full_model,
            half_resolution_clahe,
        ),
        Condition(
            "full_center_mask",
            "Full / retain center 64% of frame",
            args.full_model,
            center_mask,
        ),
        Condition(
            "full_center_mask_half",
            "Full / retain center 64% then area downsample to 50%",
            args.full_model,
            center_mask_half_resolution,
        ),
    )
    available = {condition.id: condition for condition in conditions}
    selected_ids = args.condition or list(available)
    unknown = sorted(set(selected_ids) - available.keys())
    if unknown:
        raise ValueError(f"Unknown conditions: {', '.join(unknown)}")
    selected_clips = args.clip or list(EXPECTED_ACTIONS)
    unknown_clips = sorted(set(selected_clips) - EXPECTED_ACTIONS.keys())
    if unknown_clips:
        raise ValueError(f"Unknown clips: {', '.join(unknown_clips)}")
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
    for condition_id in selected_ids:
        specification = available[condition_id]
        condition = {
            "id": specification.id,
            "description": specification.description,
            "model": specification.model_path.name,
            "preprocess": next(
                name
                for name, operation in PREPROCESSORS.items()
                if operation is specification.preprocess
            ),
            "confidence": {
                "detection": specification.detection_confidence,
                "presence": specification.presence_confidence,
                "tracking": specification.tracking_confidence,
            },
            "clips": [],
        }
        for filename in selected_clips:
            expected = EXPECTED_ACTIONS[filename]
            print(f"[{condition_id}] {filename}", flush=True)
            condition["clips"].append(
                evaluate_clip(args.sample_dir / filename, expected, specification)
            )
        report["conditions"].append(condition)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )


if __name__ == "__main__":
    main()
