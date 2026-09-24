#!/usr/bin/env python3
"""Measure YOLO Pose landmark availability on the behind-screen clips."""

from __future__ import annotations

import argparse
import json
import platform
import time
from pathlib import Path
from typing import Any

import numpy as np
import torch
import ultralytics
from ultralytics import YOLO

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CLIPS = (
    "ラムネbtn.mp4",
    "夕涼みbtn.mp4",
    "扇ぎbtn.mp4",
    "打ち水btn.mp4",
)
# COCO keypoints corresponding to the seven MediaPipe points used by the
# curtain evaluator: nose, shoulders, wrists, and hips.
IMPORTANT_KEYPOINTS = (0, 5, 6, 9, 10, 11, 12)


def select_primary_person(result: Any, min_area_ratio: float = 0.08) -> int | None:
    """Choose the largest detected person, which is the foreground performer."""
    if result.boxes is None or len(result.boxes.xyxy) == 0:
        return None
    boxes = result.boxes.xyxy.detach().cpu().numpy()
    areas = (boxes[:, 2] - boxes[:, 0]) * (boxes[:, 3] - boxes[:, 1])
    image_area = result.orig_shape[0] * result.orig_shape[1]
    foreground = np.flatnonzero(areas >= image_area * min_area_ratio)
    if not len(foreground):
        return None
    return int(foreground[np.argmax(areas[foreground])])


def evaluate_clip(
    model: YOLO,
    source: Path,
    confidence: float,
    image_size: int,
    device: str,
    min_area_ratio: float,
) -> dict[str, Any]:
    frames = 0
    pose_frames = 0
    important_visible = 0
    confidence_sum = 0.0
    jumps: list[float] = []
    previous: np.ndarray[Any, Any] | None = None
    started = time.perf_counter()

    predictions = model.predict(
        source=str(source),
        stream=True,
        conf=confidence,
        imgsz=image_size,
        device=device,
        verbose=False,
    )
    for prediction in predictions:
        result: Any = prediction
        frames += 1
        person = select_primary_person(result, min_area_ratio)
        if person is None or result.keypoints is None or result.keypoints.conf is None:
            previous = None
            continue
        coordinates = result.keypoints.xyn[person].detach().cpu().numpy()
        confidences = result.keypoints.conf[person].detach().cpu().numpy()
        pose_frames += 1
        selected_confidences = confidences[list(IMPORTANT_KEYPOINTS)]
        confidence_sum += float(np.mean(selected_confidences))
        important_visible += int(np.all(selected_confidences > 0.5))
        current = coordinates[list(IMPORTANT_KEYPOINTS)]
        if previous is not None:
            jumps.extend(np.linalg.norm(current - previous, axis=1).tolist())
        previous = current

    return {
        "source": source.name,
        "frames": frames,
        "pose_frames": pose_frames,
        "pose_frame_ratio": pose_frames / frames if frames else 0.0,
        "important_keypoints_visible_frames": important_visible,
        "important_keypoints_visible_ratio": important_visible / frames if frames else 0.0,
        "mean_important_keypoint_confidence": (
            confidence_sum / pose_frames if pose_frames else 0.0
        ),
        "mean_important_keypoint_jump": float(np.mean(jumps)) if jumps else None,
        "p95_important_keypoint_jump": float(np.percentile(jumps, 95)) if jumps else None,
        "elapsed_seconds": time.perf_counter() - started,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample-dir", type=Path, default=PROJECT_ROOT / "sample_movies")
    parser.add_argument("--model", type=Path, default=PROJECT_ROOT / "yolov8n-pose.pt")
    parser.add_argument("--output", type=Path, default=PROJECT_ROOT / "docs/yolo-pose-curtain.json")
    parser.add_argument("--confidence", type=float, default=0.25)
    parser.add_argument("--image-size", type=int, default=640)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--min-area-ratio", type=float, default=0.08)
    parser.add_argument("--clip", action="append")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    clips = args.clip or list(DEFAULT_CLIPS)
    missing = [filename for filename in clips if not (args.sample_dir / filename).is_file()]
    if missing:
        raise FileNotFoundError(f"Missing clips: {', '.join(missing)}")
    if not args.model.is_file():
        raise FileNotFoundError(args.model)
    if not 0.0 <= args.confidence <= 1.0:
        raise ValueError("confidence must be between 0 and 1")
    if args.image_size <= 0:
        raise ValueError("image size must be positive")
    if not 0.0 <= args.min_area_ratio <= 1.0:
        raise ValueError("minimum area ratio must be between 0 and 1")

    model = YOLO(str(args.model))
    report = {
        "environment": {
            "python": platform.python_version(),
            "ultralytics": ultralytics.__version__,
            "torch": torch.__version__,
            "device": args.device,
        },
        "model": args.model.name,
        "confidence": args.confidence,
        "image_size": args.image_size,
        "min_area_ratio": args.min_area_ratio,
        "important_keypoint_indices": list(IMPORTANT_KEYPOINTS),
        "clips": [],
    }
    for filename in clips:
        print(f"[yolo-pose] {filename}", flush=True)
        report["clips"].append(
            evaluate_clip(
                model,
                args.sample_dir / filename,
                args.confidence,
                args.image_size,
                args.device,
                args.min_area_ratio,
            )
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )


if __name__ == "__main__":
    main()
