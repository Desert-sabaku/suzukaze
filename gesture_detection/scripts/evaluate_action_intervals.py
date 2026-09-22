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
import numpy as np

from gesture_detection import pose_worker
from gesture_detection.app import FrameClock, GestureApplication
from gesture_detection.config import (
    RAMUNE_ALIGN_TOLERANCE,
    RAMUNE_MAX_READY_GAP,
    RAMUNE_MIN_READY_GAP,
)

from .evaluate_curtain import PREPROCESSORS
from .evaluate_landmark_annotations import (
    BACKGROUND_PREPROCESSORS,
    background_preprocess,
    build_session_backgrounds,
    load_frames,
)

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


def ramune_geometry(
    landmarks: list[tuple[float, float, float]],
    *,
    visibility_threshold: float = 0.5,
    alignment_tolerance: float = RAMUNE_ALIGN_TOLERANCE,
) -> dict[str, float] | None:
    if len(landmarks) < 25 or any(
        landmarks[index][2] <= visibility_threshold for index in (11, 12, 15, 16, 23, 24)
    ):
        return None
    scale = abs(landmarks[11][0] - landmarks[12][0])
    if scale < 1e-6:
        return None
    lower = max((15, 16), key=lambda index: landmarks[index][1])
    upper = 31 - lower
    gap = (landmarks[lower][1] - landmarks[upper][1]) / scale
    alignment = abs(landmarks[15][0] - landmarks[16][0]) / scale
    shoulder_y = (landmarks[11][1] + landmarks[12][1]) / 2
    hip_y = (landmarks[23][1] + landmarks[24][1]) / 2
    return {
        "gap": gap,
        "alignment": alignment,
        "in_torso": float(shoulder_y <= landmarks[lower][1] <= hip_y),
        "ready": float(
            alignment <= alignment_tolerance
            and shoulder_y <= landmarks[lower][1] <= hip_y
            and RAMUNE_MIN_READY_GAP <= gap <= RAMUNE_MAX_READY_GAP
        ),
    }


class RamunePoseCandidate:
    """Accept a sustained two-hand setup without requiring wrist contact."""

    def __init__(
        self, visibility_threshold: float, alignment_tolerance: float, dwell: float = 0.25
    ):
        self.visibility_threshold = visibility_threshold
        self.alignment_tolerance = alignment_tolerance
        self.dwell = dwell
        self.ready_since: float | None = None
        self.emitted = False

    def update(self, landmarks: list[tuple[float, float, float]], timestamp: float) -> bool:
        geometry = ramune_geometry(
            landmarks,
            visibility_threshold=self.visibility_threshold,
            alignment_tolerance=self.alignment_tolerance,
        )
        if geometry is None or not geometry["ready"]:
            self.ready_since = None
            self.emitted = False
            return False
        if self.ready_since is None:
            self.ready_since = timestamp
            return False
        if not self.emitted and timestamp - self.ready_since >= self.dwell:
            self.emitted = True
            return True
        return False


class RelaxingPoseCandidate:
    """Diagnostic stillness detector using only stable gesture-relevant joints."""

    LANDMARKS = (11, 12, 15, 16, 23, 24)

    def __init__(
        self,
        *,
        landmarks: tuple[int, ...] = LANDMARKS,
        ema_alpha: float,
        max_speed: float,
        max_drift: float,
        dwell: float = 1.0,
        max_gap: float = 0.25,
        preserve_missing: bool = False,
    ) -> None:
        self.landmarks = landmarks
        self.ema_alpha = ema_alpha
        self.max_speed = max_speed
        self.max_drift = max_drift
        self.dwell = dwell
        self.max_gap = max_gap
        self.preserve_missing = preserve_missing
        self.smoothed: np.ndarray[Any, Any] | None = None
        self.anchor: np.ndarray[Any, Any] | None = None
        self.last_time: float | None = None
        self.still_since = 0.0

    def update(
        self,
        landmarks: list[tuple[float, float, float]],
        timestamp: float,
        aspect_ratio: float,
    ) -> bool:
        if len(landmarks) <= max(self.landmarks) or any(
            landmarks[index][2] <= 0.5 for index in self.landmarks
        ):
            if (
                self.preserve_missing
                and self.last_time is not None
                and timestamp - self.last_time <= self.max_gap
            ):
                return False
            self.smoothed = self.anchor = self.last_time = None
            return False
        points = np.asarray(
            [(landmarks[index][0] * aspect_ratio, landmarks[index][1]) for index in self.landmarks]
        )
        shoulder_points = np.asarray(
            [(landmarks[index][0] * aspect_ratio, landmarks[index][1]) for index in (11, 12)]
        )
        hip_points = np.asarray(
            [(landmarks[index][0] * aspect_ratio, landmarks[index][1]) for index in (23, 24)]
        )
        shoulder_center = np.mean(shoulder_points, axis=0)
        hip_center = np.mean(hip_points, axis=0)
        scale = float(np.linalg.norm(shoulder_center - hip_center))
        if scale <= 1e-6:
            self.smoothed = self.anchor = self.last_time = None
            return False
        dt = timestamp - self.last_time if self.last_time is not None else 0.0
        if self.smoothed is None or self.anchor is None or dt <= 0 or dt > self.max_gap:
            self.smoothed = points
            self.anchor = points.copy()
            self.still_since = timestamp
            self.last_time = timestamp
            return False
        current = self.ema_alpha * points + (1 - self.ema_alpha) * self.smoothed
        speed = float(np.max(np.linalg.norm(current - self.smoothed, axis=1)) / scale / dt)
        drift = float(np.max(np.linalg.norm(current - self.anchor, axis=1)) / scale)
        if speed > self.max_speed or drift > self.max_drift:
            self.anchor = current.copy()
            self.still_since = timestamp
        self.smoothed = current
        self.last_time = timestamp
        return timestamp - self.still_since >= self.dwell


def distribution(values: list[float]) -> dict[str, float | None]:
    return {
        "count": float(len(values)),
        "median": float(np.median(values)) if values else None,
        "p95": float(np.percentile(values, 95)) if values else None,
        "max": max(values) if values else None,
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
    background: Any | None = None,
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
    preprocess = PREPROCESSORS.get(preprocess_name)
    clock = FrameClock(is_video=True)
    source_frames = evaluated_frames = interval_frames = pose_interval_frames = 0
    expected_frames = outside_frames = outside_action_frames = 0
    interval_actions: Counter[str] = Counter()
    outside_actions: Counter[str] = Counter()
    expected_detected = False
    expected_occurrence = False
    first_expected_at: float | None = None
    next_sample_at = 0.0
    ramune_states: Counter[str] = Counter()
    ramune_gaps: list[float] = []
    ramune_alignments: list[float] = []
    ramune_ready_geometry_frames = 0
    ramune_required_visible_frames = 0
    ramune_presses: list[float] = []
    ramune_closings: list[float] = []
    ramune_remaining_gaps: list[float] = []
    relaxing_speeds: list[float] = []
    relaxing_still_seconds: list[float] = []
    ramune_pose_candidates = {
        "align_100_dwell_025_visible_050": RamunePoseCandidate(0.5, 1.0, 0.25),
        "align_100_dwell_050_visible_050": RamunePoseCandidate(0.5, 1.0, 0.5),
        "align_080_dwell_025_visible_050": RamunePoseCandidate(0.5, 0.8, 0.25),
        "align_100_dwell_025_visible_020": RamunePoseCandidate(0.2, 1.0, 0.25),
    }
    ramune_pose_candidate_interval_events: Counter[str] = Counter()
    ramune_pose_candidate_outside_events: Counter[str] = Counter()
    relaxing_pose_candidates = {
        "speed_030_drift_008": RelaxingPoseCandidate(
            ema_alpha=0.35, max_speed=0.30, max_drift=0.08
        ),
        "speed_050_drift_010": RelaxingPoseCandidate(
            ema_alpha=0.35, max_speed=0.50, max_drift=0.10
        ),
        "torso_speed_030_drift_008": RelaxingPoseCandidate(
            landmarks=(11, 12, 23, 24),
            ema_alpha=0.35,
            max_speed=0.30,
            max_drift=0.08,
        ),
        "torso_speed_050_drift_010": RelaxingPoseCandidate(
            landmarks=(11, 12, 23, 24),
            ema_alpha=0.35,
            max_speed=0.50,
            max_drift=0.10,
        ),
        "torso_grace_080_speed_050_drift_010": RelaxingPoseCandidate(
            landmarks=(11, 12, 23, 24),
            ema_alpha=0.35,
            max_speed=0.50,
            max_drift=0.10,
            max_gap=0.8,
            preserve_missing=True,
        ),
    }
    relaxing_pose_candidate_interval_frames: Counter[str] = Counter()
    relaxing_pose_candidate_outside_frames: Counter[str] = Counter()
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
            if preprocess is not None:
                prepared = preprocess(frame)
            else:
                if background is None:
                    raise ValueError("Background preprocessing requires a reference image")
                prepared = background_preprocess(frame, background, preprocess_name)
            result = analyzer.process(prepared, timestamp, evaluated_frames)
            evaluated_frames += 1
            action = GestureApplication._primary_action(result)
            in_interval = interval_start <= timestamp <= interval_end
            candidate_events = {
                name: candidate.update(result["landmarks"], timestamp)
                for name, candidate in ramune_pose_candidates.items()
            }
            relaxing_candidates = {
                name: candidate.update(
                    result["landmarks"], timestamp, prepared.shape[1] / prepared.shape[0]
                )
                for name, candidate in relaxing_pose_candidates.items()
            }
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
                ramune_states[result.get("ramune_state", "UNKNOWN")] += 1
                geometry = ramune_geometry(result["landmarks"])
                if geometry is not None:
                    ramune_required_visible_frames += 1
                    ramune_gaps.append(geometry["gap"])
                    ramune_alignments.append(geometry["alignment"])
                    ramune_ready_geometry_frames += int(geometry["ready"])
                ramune = analyzer.recognition.ramune
                if ramune.state == "READY" and ramune.base_index is not None:
                    landmarks = result["landmarks"]
                    base = landmarks[ramune.base_index]
                    pressing = landmarks[31 - ramune.base_index]
                    press = (pressing[1] - ramune.upper_y) / ramune.scale
                    remaining = (base[1] - pressing[1]) / ramune.scale
                    ramune_presses.append(press)
                    ramune_remaining_gaps.append(remaining)
                    ramune_closings.append(ramune.ready_gap - remaining)
                speed = result.get("motion_speed")
                if speed is not None and math.isfinite(speed):
                    relaxing_speeds.append(speed)
                still_seconds = result.get("still_seconds")
                if still_seconds is not None and math.isfinite(still_seconds):
                    relaxing_still_seconds.append(still_seconds)
                for name, detected in candidate_events.items():
                    ramune_pose_candidate_interval_events[name] += int(detected)
                for name, active in relaxing_candidates.items():
                    relaxing_pose_candidate_interval_frames[name] += int(active)
            else:
                outside_frames += 1
                outside_actions[action] += 1
                outside_action_frames += int(action != "NONE")
                for name, detected in candidate_events.items():
                    ramune_pose_candidate_outside_events[name] += int(detected)
                for name, active in relaxing_candidates.items():
                    relaxing_pose_candidate_outside_frames[name] += int(active)
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
        "diagnostics": {
            "ramune_states": dict(sorted(ramune_states.items())),
            "ramune_required_visible_frames": ramune_required_visible_frames,
            "ramune_ready_geometry_frames": ramune_ready_geometry_frames,
            "ramune_gap": distribution(ramune_gaps),
            "ramune_alignment": distribution(ramune_alignments),
            "ramune_press": distribution(ramune_presses),
            "ramune_closing": distribution(ramune_closings),
            "ramune_remaining_gap": distribution(ramune_remaining_gaps),
            "relaxing_motion_speed": distribution(relaxing_speeds),
            "relaxing_still_seconds": distribution(relaxing_still_seconds),
            "ramune_pose_candidate_interval_events": dict(
                sorted(ramune_pose_candidate_interval_events.items())
            ),
            "ramune_pose_candidate_outside_events": dict(
                sorted(ramune_pose_candidate_outside_events.items())
            ),
            "relaxing_pose_candidate_interval_frames": dict(
                sorted(relaxing_pose_candidate_interval_frames.items())
            ),
            "relaxing_pose_candidate_outside_frames": dict(
                sorted(relaxing_pose_candidate_outside_frames.items())
            ),
        },
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
    parser.add_argument("--annotations", type=Path, default=PROJECT_ROOT / "shared" / "annotations")
    parser.add_argument("--model", type=Path, default=PROJECT_ROOT / "pose_landmarker_lite.task")
    parser.add_argument(
        "--preprocess",
        choices=sorted((*PREPROCESSORS, *BACKGROUND_PREPROCESSORS)),
        default="identity",
    )
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
    backgrounds = None
    if args.preprocess in BACKGROUND_PREPROCESSORS:
        if {environment for environment, _ in selected} != {"behind"}:
            raise ValueError("Background preprocessing is available only with --environment behind")
        backgrounds = build_session_backgrounds(load_frames(args.annotations))

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
                backgrounds[source.stem] if backgrounds is not None else None,
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
