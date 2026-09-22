#!/usr/bin/env python3
"""Compare gesture recognition in named action intervals with and without a curtain."""

from __future__ import annotations

import argparse
import json
import math
import platform
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import cv2
import mediapipe

from gesture_detection import pose_worker
from gesture_detection.app import FrameClock, GestureApplication

from .evaluate_curtain import PREPROCESSORS

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CLIP_PATTERN = re.compile(
    r"(?P<action>aogi|ramune|uchimizu|utimizu|yusuzumi)(?P<take>\d+)_"
    r"(?P<start>\d+(?:\.\d+)?)-(?P<end>\d+(?:\.\d+)?)\.mp4",
    re.IGNORECASE,
)
EXPECTED_ACTION = {
    "aogi": "FANNING",
    "ramune": "RAMUNE",
    "uchimizu": "SPRINKLING",
    "utimizu": "SPRINKLING",
    "yusuzumi": "RELAXING",
}


def parse_clip_name(path: Path) -> tuple[str, int, float, float]:
    match = CLIP_PATTERN.fullmatch(path.name)
    if match is None:
        raise ValueError(f"Clip name does not contain an action interval: {path.name}")
    action = match.group("action").lower()
    return (
        EXPECTED_ACTION[action],
        int(match.group("take")),
        float(match.group("start")),
        float(match.group("end")),
    )


def discover_clips(video_root: Path) -> list[tuple[str, Path]]:
    directories = {
        "behind": video_root / "bihind-the-screen_sabaku",
        "without": video_root / "without-the-screen_sabaku",
    }
    clips: list[tuple[str, Path]] = []
    for environment, directory in directories.items():
        if not directory.is_dir():
            raise FileNotFoundError(directory)
        for path in sorted(directory.glob("*.mp4")):
            parse_clip_name(path)
            clips.append((environment, path))
    if not clips:
        raise ValueError(f"No interval-labelled clips found in {video_root}")
    return clips


def evaluate_clip(
    source: Path,
    environment: str,
    model: Path,
    preprocess_name: str,
    detection_confidence: float,
    presence_confidence: float,
    sample_fps: float,
) -> dict[str, Any]:
    expected, take, interval_start, interval_end = parse_clip_name(source)
    pose_worker.POSE_MODEL_PATH = model
    analyzer = pose_worker.PoseAnalyzer(
        running_mode="VIDEO",
        detection_confidence=detection_confidence,
        presence_confidence=presence_confidence,
    )
    capture = cv2.VideoCapture(str(source))
    if not capture.isOpened():
        analyzer.close()
        raise RuntimeError(f"Unable to open {source}")
    preprocess = PREPROCESSORS[preprocess_name]
    clock = FrameClock(is_video=True)
    source_frames = evaluated_frames = interval_frames = pose_interval_frames = 0
    expected_frames = outside_frames = outside_action_frames = 0
    interval_actions: Counter[str] = Counter()
    outside_actions: Counter[str] = Counter()
    expected_detected = False
    expected_occurrence = False
    first_expected_at: float | None = None
    next_sample_at = 0.0
    try:
        while True:
            ok, frame = capture.read()
            if not ok:
                break
            timestamp = clock.timestamp(capture)
            source_frames += 1
            if timestamp + 1e-9 < next_sample_at:
                continue
            next_sample_at = timestamp + 1 / sample_fps
            result = analyzer.process(preprocess(frame), timestamp, evaluated_frames)
            evaluated_frames += 1
            action = GestureApplication._primary_action(result)
            in_interval = interval_start <= timestamp <= interval_end
            if in_interval:
                interval_frames += 1
                interval_actions[action] += 1
                current = result.get("current")
                pose_interval_frames += int(current is not None and current["tracking"])
                if action == expected:
                    expected_frames += 1
                    expected_detected = True
                    if first_expected_at is None:
                        first_expected_at = timestamp
                occurrences = {
                    "SPRINKLING" if item == "UCHIMIZU" else item
                    for item in result.get("occurrences", ())
                }
                expected_occurrence |= expected in occurrences
            else:
                outside_frames += 1
                outside_actions[action] += 1
                outside_action_frames += int(action != "NONE")
    finally:
        capture.release()
        analyzer.close()

    return {
        "environment": environment,
        "source": source.name,
        "take": take,
        "expected_action": expected,
        "expected_interval": [interval_start, interval_end],
        "source_frames": source_frames,
        "evaluated_frames": evaluated_frames,
        "sample_fps": sample_fps,
        "interval_frames": interval_frames,
        "pose_interval_frames": pose_interval_frames,
        "pose_interval_ratio": pose_interval_frames / interval_frames if interval_frames else None,
        "expected_action_frames": expected_frames,
        "expected_action_frame_ratio": expected_frames / interval_frames
        if interval_frames
        else None,
        "clip_detected": expected_detected,
        "occurrence_detected": expected_occurrence,
        "first_expected_latency": (
            first_expected_at - interval_start if first_expected_at is not None else None
        ),
        "outside_frames": outside_frames,
        "outside_action_ratio": outside_action_frames / outside_frames if outside_frames else None,
        "interval_actions": dict(sorted(interval_actions.items())),
        "outside_actions": dict(sorted(outside_actions.items())),
    }


def aggregate(clips: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for clip in clips:
        grouped[(clip["environment"], clip["expected_action"])].append(clip)
    rows: list[dict[str, Any]] = []
    for (environment, action), items in sorted(grouped.items()):
        interval_frames = sum(item["interval_frames"] for item in items)
        expected_frames = sum(item["expected_action_frames"] for item in items)
        outside_frames = sum(item["outside_frames"] for item in items)
        outside_action_frames = sum(
            sum(count for name, count in item["outside_actions"].items() if name != "NONE")
            for item in items
        )
        pose_frames = sum(item["pose_interval_frames"] for item in items)
        rows.append(
            {
                "environment": environment,
                "expected_action": action,
                "clips": len(items),
                "clip_recall": sum(item["clip_detected"] for item in items) / len(items),
                "occurrence_recall": sum(item["occurrence_detected"] for item in items)
                / len(items),
                "pose_interval_ratio": pose_frames / interval_frames if interval_frames else None,
                "expected_action_frame_ratio": (
                    expected_frames / interval_frames if interval_frames else None
                ),
                "outside_action_ratio": (
                    outside_action_frames / outside_frames if outside_frames else None
                ),
            }
        )
    return rows


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--video-root", type=Path, default=PROJECT_ROOT / "shared" / "videos")
    parser.add_argument("--model", type=Path, default=PROJECT_ROOT / "pose_landmarker_lite.task")
    parser.add_argument("--preprocess", choices=sorted(PREPROCESSORS), default="identity")
    parser.add_argument("--detection-confidence", type=float, default=0.5)
    parser.add_argument("--presence-confidence", type=float, default=0.5)
    parser.add_argument("--sample-fps", type=float, default=10.0)
    parser.add_argument("--environment", choices=("behind", "without"), action="append")
    parser.add_argument("--action", choices=sorted(set(EXPECTED_ACTION.values())), action="append")
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "shared" / "results" / "action-intervals.json",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not args.model.is_file():
        raise FileNotFoundError(args.model)
    if not math.isfinite(args.sample_fps) or args.sample_fps <= 0:
        raise ValueError("Sample FPS must be positive and finite")
    for value in (args.detection_confidence, args.presence_confidence):
        if not 0 <= value <= 1:
            raise ValueError("Confidence thresholds must be between 0 and 1")
    selected = []
    for environment, source in discover_clips(args.video_root):
        expected, _, _, _ = parse_clip_name(source)
        if args.environment and environment not in args.environment:
            continue
        if args.action and expected not in args.action:
            continue
        selected.append((environment, source))
    if not selected:
        raise ValueError("No clips match the requested filters")

    clips = []
    for environment, source in selected:
        print(f"[{environment}] {source.name}", flush=True)
        clips.append(
            evaluate_clip(
                source,
                environment,
                args.model,
                args.preprocess,
                args.detection_confidence,
                args.presence_confidence,
                args.sample_fps,
            )
        )
        report = {
            "environment": {
                "python": platform.python_version(),
                "mediapipe": mediapipe.__version__,
                "opencv": cv2.__version__,
            },
            "condition": {
                "model": args.model.name,
                "preprocess": args.preprocess,
                "detection_confidence": args.detection_confidence,
                "presence_confidence": args.presence_confidence,
                "sample_fps": args.sample_fps,
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
