#!/usr/bin/env python3
"""Evaluate YOLO Pose candidates against manually annotated curtain frames."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import platform
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import torch
import ultralytics
from ultralytics import YOLO

from .evaluate_landmark_annotations import (
    AnnotatedFrame,
    load_frames,
    reference_scale,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
YOLO_LANDMARK_INDICES = {
    "left_shoulder": 5,
    "right_shoulder": 6,
    "left_wrist": 9,
    "right_wrist": 10,
    "left_hip": 11,
    "right_hip": 12,
}
SELECTION_STRATEGIES = ("largest", "center", "oracle")


def sha256(path: Path) -> str:
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def foreground_candidates(result: Any, min_area_ratio: float) -> np.ndarray[Any, Any]:
    if result.boxes is None or len(result.boxes.xyxy) == 0:
        return np.asarray([], dtype=int)
    boxes = result.boxes.xyxy.detach().cpu().numpy()
    areas = (boxes[:, 2] - boxes[:, 0]) * (boxes[:, 3] - boxes[:, 1])
    image_area = result.orig_shape[0] * result.orig_shape[1]
    return np.flatnonzero(areas >= image_area * min_area_ratio)


def select_candidate(
    result: Any,
    candidates: np.ndarray[Any, Any],
    strategy: str,
    annotated: AnnotatedFrame,
    keypoint_confidence: float,
) -> int | None:
    if not len(candidates):
        return None
    boxes = result.boxes.xyxy.detach().cpu().numpy()
    if strategy == "largest":
        areas = (boxes[:, 2] - boxes[:, 0]) * (boxes[:, 3] - boxes[:, 1])
        return int(candidates[np.argmax(areas[candidates])])
    if strategy == "center":
        centers = (boxes[candidates, :2] + boxes[candidates, 2:]) / 2
        image_center = np.asarray((result.orig_shape[1] / 2, result.orig_shape[0] / 2))
        return int(candidates[np.argmin(np.linalg.norm(centers - image_center, axis=1))])
    if strategy != "oracle":
        raise ValueError(f"Unknown selection strategy: {strategy}")

    coordinates = result.keypoints.xy.detach().cpu().numpy()
    confidences = result.keypoints.conf.detach().cpu().numpy()
    height, width = result.orig_shape
    scale = reference_scale(annotated.annotations, width, height)
    scores = []
    for candidate in candidates:
        penalties = []
        for item in annotated.annotations:
            if item.status != "marked":
                continue
            index = YOLO_LANDMARK_INDICES[item.landmark]
            if confidences[candidate, index] < keypoint_confidence:
                penalties.append(2.0)
            else:
                penalties.append(
                    math.hypot(
                        coordinates[candidate, index, 0] - item.x_px,
                        coordinates[candidate, index, 1] - item.y_px,
                    )
                    / scale
                )
        scores.append(float(np.mean(penalties)) if penalties else math.inf)
    return int(candidates[np.argmin(scores)])


def evaluate_strategy(
    frames: list[AnnotatedFrame],
    results: list[Any],
    strategy: str,
    min_area_ratio: float,
    keypoint_confidence: float,
) -> dict[str, Any]:
    presence_frames = detected_presence_frames = absent_frames = false_positive_frames = 0
    marked_points = detected_points = 0
    normalized_errors: list[float] = []
    marked_by_landmark: Counter[str] = Counter()
    errors_by_landmark: dict[str, list[float]] = defaultdict(list)
    for annotated, result in zip(frames, results, strict=True):
        candidates = foreground_candidates(result, min_area_ratio)
        present = any(item.status in {"marked", "uncertain"} for item in annotated.annotations)
        if present:
            presence_frames += 1
            detected_presence_frames += int(bool(len(candidates)))
        else:
            absent_frames += 1
            false_positive_frames += int(bool(len(candidates)))
        selected = select_candidate(result, candidates, strategy, annotated, keypoint_confidence)
        coordinates = (
            result.keypoints.xy.detach().cpu().numpy() if result.keypoints is not None else None
        )
        confidences = (
            result.keypoints.conf.detach().cpu().numpy()
            if result.keypoints is not None and result.keypoints.conf is not None
            else None
        )
        height, width = result.orig_shape
        scale = reference_scale(annotated.annotations, width, height)
        for item in annotated.annotations:
            if item.status != "marked":
                continue
            marked_points += 1
            marked_by_landmark[item.landmark] += 1
            if selected is None or coordinates is None or confidences is None:
                continue
            index = YOLO_LANDMARK_INDICES[item.landmark]
            if confidences[selected, index] < keypoint_confidence:
                continue
            detected_points += 1
            error = (
                math.hypot(
                    coordinates[selected, index, 0] - item.x_px,
                    coordinates[selected, index, 1] - item.y_px,
                )
                / scale
            )
            normalized_errors.append(error)
            errors_by_landmark[item.landmark].append(error)

    return {
        "selection": strategy,
        "frames": len(frames),
        "presence_frames": presence_frames,
        "pose_recall": detected_presence_frames / presence_frames if presence_frames else None,
        "absent_frames": absent_frames,
        "false_positive_rate": false_positive_frames / absent_frames if absent_frames else None,
        "marked_points": marked_points,
        "point_detection_rate": detected_points / marked_points if marked_points else None,
        "median_normalized_error_on_detected": (
            float(np.median(normalized_errors)) if normalized_errors else None
        ),
        "pck_at_0_2": (
            sum(error <= 0.2 for error in normalized_errors) / marked_points
            if marked_points
            else None
        ),
        "per_landmark": {
            name: {
                "marked_points": marked_by_landmark[name],
                "detected_points": len(errors_by_landmark[name]),
                "median_normalized_error_on_detected": (
                    float(np.median(errors_by_landmark[name])) if errors_by_landmark[name] else None
                ),
                "pck_at_0_2": (
                    sum(error <= 0.2 for error in errors_by_landmark[name])
                    / marked_by_landmark[name]
                ),
            }
            for name in sorted(marked_by_landmark)
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--annotations", type=Path, default=PROJECT_ROOT / "shared" / "annotations")
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--confidence", type=float, default=0.05)
    parser.add_argument("--keypoint-confidence", type=float, default=0.5)
    parser.add_argument("--image-size", type=int, default=640)
    parser.add_argument("--min-area-ratio", type=float, default=0.08)
    parser.add_argument("--device", default="cpu")
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "shared" / "results" / "yolo-landmark-annotations.json",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not args.model.is_file():
        raise FileNotFoundError(args.model)
    for value in (args.confidence, args.keypoint_confidence, args.min_area_ratio):
        if not 0 <= value <= 1:
            raise ValueError("Confidence and area thresholds must be between 0 and 1")
    if args.image_size <= 0:
        raise ValueError("Image size must be positive")
    frames = load_frames(args.annotations)
    model = YOLO(str(args.model))
    results = list(
        model.predict(
            source=[str(frame.image) for frame in frames],
            stream=True,
            conf=args.confidence,
            imgsz=args.image_size,
            device=args.device,
            verbose=False,
        )
    )
    if len(results) != len(frames):
        raise RuntimeError("YOLO result count does not match the annotated frames")
    report = {
        "environment": {
            "python": platform.python_version(),
            "ultralytics": ultralytics.__version__,
            "torch": torch.__version__,
            "opencv": cv2.__version__,
            "device": args.device,
        },
        "condition": {
            "model": args.model.name,
            "model_sha256": sha256(args.model),
            "confidence": args.confidence,
            "keypoint_confidence": args.keypoint_confidence,
            "image_size": args.image_size,
            "min_area_ratio": args.min_area_ratio,
        },
        "annotations": {
            "sessions": len({frame.session for frame in frames}),
            "frames": len(frames),
        },
        "strategies": [
            evaluate_strategy(
                frames,
                results,
                strategy,
                args.min_area_ratio,
                args.keypoint_confidence,
            )
            for strategy in SELECTION_STRATEGIES
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Report: {args.output}")


if __name__ == "__main__":
    main()
