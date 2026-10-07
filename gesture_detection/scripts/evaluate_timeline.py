"""Replay every frame against timeline annotations using the live PoseAnalyzer."""

from __future__ import annotations

import argparse
import json
import math
import subprocess
import time
from collections import Counter, defaultdict
from importlib.metadata import version
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from gesture_detection import config
from gesture_detection import pose_worker as pose_module
from gesture_detection.pose_worker import PoseAnalyzer

from .video_annotation import load_label_config, load_timeline, sha256

LANDMARK_NAMES = tuple(load_label_config()["landmarks"])
EVENT_GESTURES = {"RAMUNE_OPEN": "RAMUNE", "UCHIMIZU_RELEASE": "UCHIMIZU"}


def match_events(expected: list[int], predicted: list[int], tolerance: int) -> dict[str, Any]:
    """Ordered one-to-one matching; duplicates remain false positives."""
    expected, predicted = sorted(expected), sorted(predicted)
    i = j = 0
    errors = []
    while i < len(expected) and j < len(predicted):
        delta = predicted[j] - expected[i]
        if delta < -tolerance:
            j += 1
        elif delta > tolerance:
            i += 1
        else:
            errors.append(delta)
            i += 1
            j += 1
    return {
        "tp": len(errors),
        "fp": len(predicted) - len(errors),
        "fn": len(expected) - len(errors),
        "signed_error_frames": errors,
    }


def landmark_errors(
    annotation: dict[str, Any], points: list, width: int, height: int
) -> list[dict[str, Any]]:
    rows = []
    for name, point in annotation.items():
        if point["status"] != "marked":
            continue
        if name not in LANDMARK_NAMES:
            raise ValueError(f"Unsupported landmark: {name}")
        index = LANDMARK_NAMES.index(name)
        estimate = points[index] if len(points) > index else None
        valid = estimate is not None and all(math.isfinite(v) for v in estimate)
        error = (
            math.hypot(estimate[0] * width - point["x_px"], estimate[1] * height - point["y_px"])
            if valid
            else None
        )
        rows.append({"name": name, "error_px": error, "visibility": estimate[2] if valid else None})
    return rows


def summarize_landmarks(rows: list[dict[str, Any]]) -> dict[str, Any]:
    errors = [row["error_px"] for row in rows if row["error_px"] is not None]
    return {
        "marked_points": len(rows),
        "estimated_points": len(errors),
        "missing_points": len(rows) - len(errors),
        "mean_error_px": float(np.mean(errors)) if errors else None,
        "median_error_px": float(np.median(errors)) if errors else None,
        "p95_error_px": float(np.percentile(errors, 95)) if errors else None,
        # Missing estimates count as failures; low visibility never hides errors.
        "pck_20px": sum(error <= 20 for error in errors) / len(rows) if rows else None,
    }


def summarize(data: dict[str, Any], rows: list[dict[str, Any]], tolerance: float) -> dict[str, Any]:
    actions = [item for item in data["intervals"] if item["track"] == "action"]
    segments = []
    for action in actions:
        subset = rows[action["start_frame"] : action["end_frame"] + 1]
        hits = [row for row in subset if row["current"]["gesture"] == action["label"]]
        segments.append(
            {
                "label": action["label"],
                "start_frame": action["start_frame"],
                "end_frame": action["end_frame"],
                "frames": len(subset),
                "detected_frames": len(hits),
                "tracking_frames": sum(row["current"]["tracking"] for row in subset),
                "predictions": dict(Counter(row["current"]["gesture"] for row in subset)),
                "occurrences": dict(
                    Counter(event for row in subset for event in row["occurrences"])
                ),
            }
        )
    phases = []
    for phase in data["intervals"]:
        if phase["track"] == "action":
            continue
        subset = rows[phase["start_frame"] : phase["end_frame"] + 1]
        phases.append(
            {
                "track": phase["track"],
                "label": phase["label"],
                "frames": len(subset),
                "predictions": dict(Counter(row["current"]["gesture"] for row in subset)),
            }
        )
    event_metrics = {}
    for label, gesture in EVENT_GESTURES.items():
        expected = [event["frame_id"] for event in data["events"] if event["label"] == label]
        # No annotation is unknown, not evidence that no event happened.
        if not expected:
            continue
        predicted = [row["frame_id"] for row in rows if gesture in row["occurrences"]]
        event_metrics[label] = match_events(
            expected, predicted, round(tolerance * data["source"]["fps"])
        )
    point_rows = [point for row in rows for point in row["landmark_errors"]]
    return {
        "frames": len(rows),
        "actions": segments,
        "phases": phases,
        "events": event_metrics,
        "tracking_frames": sum(row["current"]["tracking"] for row in rows),
        "subject_states": dict(Counter(row.get("subject_state", "DISABLED") for row in rows)),
        "outside_action_predictions": dict(
            Counter(
                row["current"]["gesture"]
                for row in rows
                if not any(a["start_frame"] <= row["frame_id"] <= a["end_frame"] for a in actions)
            )
        ),
        "landmarks": summarize_landmarks(point_rows),
    }


def evaluate(
    timeline: Path,
    video: Path,
    output: Path,
    *,
    select_subject: bool,
    profile: str,
    tolerance: float,
) -> dict[str, Any]:
    data = load_timeline(timeline, video)
    source = data["source"]
    fps = float(source["fps"])
    if not math.isfinite(fps) or fps <= 0:
        raise ValueError(f"Invalid annotation FPS: {timeline}")
    capture = cv2.VideoCapture(str(video))
    analyzer = None
    rows = []
    annotations = {item["frame_id"]: item["points"] for item in data["landmarks"]}
    elapsed = 0.0
    try:
        actual_fps = capture.get(cv2.CAP_PROP_FPS)
        if not math.isclose(fps, actual_fps, rel_tol=1e-4):
            raise ValueError(f"Annotation/video FPS mismatch: {fps} vs {actual_fps}")
        analyzer = PoseAnalyzer(
            running_mode="VIDEO",
            select_subject=select_subject,
            ramune_detector="rules",
            source_fps=fps,
            recognition_profile=profile,
        )
        for frame_id in range(source["total_frames"]):
            ok, frame = capture.read()
            if not ok or frame.shape[:2] != (source["height"], source["width"]):
                raise ValueError(f"Invalid frame {frame_id}: {video}")
            started = time.perf_counter()
            result = dict(analyzer.process(frame, frame_id / fps, frame_id))
            elapsed += time.perf_counter() - started
            result.pop("display_landmarks", None)
            result["landmark_errors"] = landmark_errors(
                annotations.get(frame_id, {}),
                result["landmarks"],
                source["width"],
                source["height"],
            )
            rows.append(result)
        if capture.read()[0]:
            raise ValueError(f"Unannotated trailing frames: {video}")
    finally:
        capture.release()
        if analyzer is not None:
            analyzer.close()
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row, allow_nan=False) + "\n")
    return {
        "source": source,
        "annotation_sha256": sha256(timeline),
        "inference_seconds": elapsed,
        "inference_fps": len(rows) / elapsed,
        **summarize(data, rows, tolerance),
    }


def aggregate(clips: dict[str, Any]) -> dict[str, Any]:
    actions: dict[str, Any] = defaultdict(
        lambda: {
            "segments": 0,
            "detected_segments": 0,
            "frames": 0,
            "detected_frames": 0,
            "tracking_frames": 0,
            "predictions": Counter(),
            "occurrences": Counter(),
        }
    )
    for clip in clips.values():
        for segment in clip["actions"]:
            total = actions[segment["label"]]
            total["segments"] += 1
            total["detected_segments"] += int(segment["detected_frames"] > 0)
            for key in ("frames", "detected_frames", "tracking_frames"):
                total[key] += segment[key]
            for key in ("predictions", "occurrences"):
                total[key].update(segment[key])
    return dict(actions)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("annotations", type=Path)
    parser.add_argument(
        "--videos", type=Path, required=True, help="Matching relative take/camera tree"
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--pose-model", choices=("configured", "lite", "full", "heavy"), default="configured"
    )
    parser.add_argument("--subject-selection", choices=("on", "off"), default="on")
    parser.add_argument("--profile", choices=("default", "multicam"), default="default")
    parser.add_argument("--event-tolerance", type=float, default=0.5)
    parser.add_argument("--landmark-clips-only", action="store_true")
    parser.add_argument(
        "--resume", action="store_true", help="Resume using the saved annotation snapshot"
    )
    args = parser.parse_args()
    if not math.isfinite(args.event_tolerance) or args.event_tolerance < 0:
        parser.error("Event tolerance must be finite and non-negative")
    annotation_root = args.output / "annotations" if args.resume else args.annotations
    timelines = sorted(annotation_root.rglob("timeline.json"))
    if args.landmark_clips_only:
        timelines = [
            p
            for p in timelines
            if any(
                point["status"] == "marked"
                for row in load_timeline(p)["landmarks"]
                for point in row["points"].values()
            )
        ]
    if not timelines:
        parser.error("No matching timelines")
    if args.output.exists() and not args.resume:
        parser.error("Output already exists; use a new directory to preserve comparison results")
    if args.pose_model != "configured":
        name = f"pose_landmarker_{args.pose_model}"
        pose_module.POSE_MODEL_PATH = config.PROJECT_ROOT / f"{name}.task"
        pose_module.POSE_MODEL_URL = f"https://storage.googleapis.com/mediapipe-models/pose_landmarker/{name}/float16/1/{name}.task"
    PoseAnalyzer.ensure_model()
    if not args.resume:
        snapshots = []
        for timeline in timelines:
            snapshot = args.output / "annotations" / timeline.relative_to(annotation_root)
            snapshot.parent.mkdir(parents=True, exist_ok=True)
            snapshot.write_bytes(timeline.read_bytes())
            snapshots.append(snapshot)
        timelines = snapshots
    annotation_root = args.output / "annotations"
    report: dict[str, Any] = {
        "revision": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "dirty": bool(subprocess.check_output(["git", "status", "--porcelain"], text=True).strip()),
        "protocol": "Sequential VIDEO inference, all frames, frame_id / annotated FPS, fresh analyzer per clip. Views scored independently; no assumed hardware synchronization. Unlabelled frames/phases/events are unknown, not negatives. Action coverage includes preparation, not classification accuracy. PCK uses all marked points including missing/low-confidence predictions.",
        "settings": {
            "evaluator_sha256": sha256(Path(__file__)),
            "packages": {name: version(name) for name in ("mediapipe", "numpy", "opencv-python")},
            "model": str(pose_module.POSE_MODEL_PATH),
            "model_sha256": sha256(pose_module.POSE_MODEL_PATH),
            "subject_selection": args.subject_selection,
            "profile": args.profile,
            "event_tolerance_seconds": args.event_tolerance,
            "config": {
                name: str(value) if isinstance(value, Path) else value
                for name, value in vars(config).items()
                if name.isupper() and name != "VIDEO_OUTPUT_PATH"
            },
            "code_sha256": {
                p.name: sha256(p) for p in sorted(Path(pose_module.__file__).parent.glob("*.py"))
            },
        },
        "clips": {},
    }
    summary_path = args.output / "summary.json"
    if args.resume and summary_path.exists():
        previous = json.loads(summary_path.read_text(encoding="utf-8"))
        if previous["settings"] != json.loads(json.dumps(report["settings"])):
            parser.error("Cannot resume with changed settings or inference code")
        report["clips"] = previous["clips"]
    report["actions"] = aggregate(report["clips"])
    for timeline in timelines:
        relative = timeline.relative_to(annotation_root).parent
        video = args.videos / relative.with_suffix(".mp4")
        if str(relative) in report["clips"]:
            saved = report["clips"][str(relative)]
            if (
                sha256(timeline) != saved["annotation_sha256"]
                or sha256(video) != saved["source"]["sha256"]
            ):
                parser.error(f"Cannot resume changed inputs: {relative}")
            continue
        print(f"Evaluating {relative}", flush=True)
        clip = evaluate(
            timeline,
            video,
            args.output / relative / "frames.jsonl",
            select_subject=args.subject_selection == "on",
            profile=args.profile,
            tolerance=args.event_tolerance,
        )
        report["clips"][str(relative)] = clip
        report["actions"] = aggregate(report["clips"])
        temporary_summary = args.output / "summary.json.tmp"
        temporary_summary.write_text(
            json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8"
        )
        temporary_summary.replace(summary_path)
        print(
            f"  tracking {clip['tracking_frames']}/{clip['frames']}; landmarks {clip['landmarks']}",
            flush=True,
        )
    print(json.dumps(report["actions"], indent=2))


if __name__ == "__main__":
    main()
