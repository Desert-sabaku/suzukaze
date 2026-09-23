"""Diagnose whole control recordings; these are not labelled action intervals."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import cv2
import numpy as np

from .evaluate_action_intervals import EXPECTED_ACTION, evaluate_clip
from .evaluate_curtain import PREPROCESSORS


def control_roi(frame):
    """Diagnostic region for these recordings; not a deployment camera setting."""
    masked = np.full_like(frame, 127)
    width = frame.shape[1]
    masked[:, round(width * 0.36) : round(width * 0.82)] = frame[
        :, round(width * 0.36) : round(width * 0.82)
    ]
    return masked


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--videos", type=Path, required=True)
    parser.add_argument("--model", type=Path, default=Path("pose_landmarker_lite.task"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--preprocess", choices=["identity", "control_roi"], default="identity")
    args = parser.parse_args()
    PREPROCESSORS["control_roi"] = control_roi
    if not args.model.is_file():
        raise FileNotFoundError(args.model)
    clips = []
    for source in sorted(args.videos.glob("*.mp4")):
        expected = EXPECTED_ACTION[source.stem]
        capture = cv2.VideoCapture(str(source))
        if not capture.isOpened():
            raise ValueError(f"Cannot open {source}")
        fps = capture.get(cv2.CAP_PROP_FPS)
        frames = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        capture.release()
        if not math.isfinite(fps) or fps <= 0 or frames <= 0:
            raise ValueError(f"Invalid video metadata: {source}")
        print(source.name, flush=True)
        result = evaluate_clip(
            source,
            "bright_without",
            args.model,
            args.preprocess,
            0.5,
            0.5,
            30,
            labelled_interval=(expected, 1, 0.0, frames / fps),
        )
        clips.append(
            {
                "source": source.name,
                "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                "fps": fps,
                "duration_seconds": frames / fps,
                "source_frames": result["source_frames"],
                "evaluated_frames": result["evaluated_frames"],
                "expected_action": expected,
                "pose_ratio_whole_recording": result["pose_interval_ratio"],
                "expected_detected_anywhere": result["clip_detected"],
                "expected_occurrence_anywhere": result["occurrence_detected"],
                "first_expected_seconds": result["first_expected_latency"],
                "actions_whole_recording": result["interval_actions"],
                "diagnostics_whole_recording": result["diagnostics"],
            }
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(
                {
                    "scope": "Whole recordings including setup and exit; no ground-truth action intervals. Not recall or false-positive evaluation.",
                    "model": str(args.model),
                    "preprocess": args.preprocess,
                    "running_mode": "VIDEO",
                    "sample_fps": 30,
                    "detection_confidence": 0.5,
                    "presence_confidence": 0.5,
                    "clips": clips,
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n"
        )
    if not clips:
        raise ValueError("No control videos found")


if __name__ == "__main__":
    main()
