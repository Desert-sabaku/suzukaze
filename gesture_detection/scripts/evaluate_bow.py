"""Replay annotated paired videos with the production multicamera recognizers."""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
from collections import Counter
from inspect import getfile
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from gesture_detection import config
from gesture_detection import pose_worker as pose_module
from gesture_detection.bow import BowAnalyzer
from gesture_detection.gesture_types import Gesture, Phase
from gesture_detection.multicam_fusion import MultiCameraFusion
from gesture_detection.pose_worker import PoseAnalyzer
from gesture_detection.recognition_types import PoseResult, current_state

from .video_annotation import load_timeline, sha256


def summarize(rows: list[dict[str, Any]], fps: float) -> dict[str, Any]:
    """Measure delivered BOW separately from the raw detector and whole action."""
    positive = [row for row in rows if row["action"] == Gesture.BOW]
    negative = [row for row in rows if row["action"] != Gesture.BOW]
    detected = [row for row in positive if row["gesture"] == Gesture.BOW]
    false_positive = [row for row in negative if row["gesture"] == Gesture.BOW]
    runs = []
    for row in rows:
        if row["gesture"] != Gesture.BOW:
            continue
        frame = row["frame_id"]
        if runs and runs[-1][1] == frame - 1:
            runs[-1][1] = frame
        else:
            runs.append([frame, frame])
    phases = {}
    for label in (Phase.BENDING, Phase.HOLD, Phase.RETURNING):
        subset = [row for row in rows if row["phase"] == label]
        phases[label] = {
            "frames": len(subset),
            "bow_frames": sum(row["gesture"] == Gesture.BOW for row in subset),
            "raw_bow_frames": sum(row["raw_bow"] for row in subset),
            "tracking_frames": sum(row["tracking"] for row in subset),
            "gestures": dict(Counter(row["gesture"] for row in subset)),
        }
        if subset and "angle" in subset[0]:
            angles = [row["angle"] for row in subset if row["angle"] is not None]
            phases[label]["diagnostics"] = {
                "angle_range": [min(angles), max(angles)] if angles else None,
                "angle_in_range_frames": sum(
                    row["angle"] is not None
                    and config.BOW_MIN_ANGLE_DEGREES <= row["angle"] <= config.BOW_MAX_ANGLE_DEGREES
                    for row in subset
                ),
                "head_aligned_frames": sum(row["head_aligned"] for row in subset),
                "head_above_shoulders_frames": sum(
                    row["head_above_shoulders"] is True for row in subset
                ),
                "invalid_bow_points_frames": sum(bool(row["invalid_bow_points"]) for row in subset),
                "subject_states": dict(Counter(row["subject_state"] for row in subset)),
            }
    first_hold = next((row["frame_id"] for row in rows if row["phase"] == Phase.HOLD), None)
    return {
        "frames": len(rows),
        "action_frames": len(positive),
        "bow_frames_in_action": len(detected),
        "action_coverage": len(detected) / len(positive) if positive else None,
        "false_positive_frames": len(false_positive),
        "negative_frames": len(negative),
        "precision": len(detected) / (len(detected) + len(false_positive))
        if detected or false_positive
        else None,
        "detected_action": bool(detected),
        "first_detection_from_hold_seconds": (detected[0]["frame_id"] - first_hold) / fps
        if detected and first_hold is not None
        else None,
        "bow_runs": runs,
        "raw_bow_suppressed_frames": sum(
            row["raw_bow"] and row["gesture"] != Gesture.BOW for row in rows
        ),
        "phases": phases,
    }


def labels_at(data: dict[str, Any], frame: int) -> tuple[str, str]:
    labels = {
        item["track"]: item["label"]
        for item in data["intervals"]
        if item["start_frame"] <= frame <= item["end_frame"]
    }
    return labels.get("action", Gesture.NONE), labels.get("bow_phase", Gesture.NONE)


def geometry(result: PoseResult) -> dict[str, Any]:
    points = result["landmarks"]
    if not points:
        return {"head_above_shoulders": None, "invalid_bow_points": "", "landmarks_json": "[]"}
    return {
        "head_above_shoulders": points[0][1] < (points[11][1] + points[12][1]) / 2,
        "invalid_bow_points": ",".join(
            str(i)
            for i in (0, 11, 12, 23, 24)
            if not 0 <= points[i][0] <= 1
            or not 0 <= points[i][1] <= 1
            or points[i][2]
            < (config.BOW_HEAD_MIN_VISIBILITY if i == 0 else config.BOW_MIN_VISIBILITY)
        ),
        "landmarks_json": json.dumps(points),
    }


def save_hold_previews(annotations: Path, output: Path) -> None:
    """Overlay cached landmarks for visual checking without rerunning inference."""
    from gesture_detection.rendering import draw_landmarks

    for take in sorted(output.glob("take_00*")):
        for camera in ("camera_1", "camera_2"):
            with (take / f"{camera}.csv").open(encoding="utf-8") as source:
                holds = [row for row in csv.DictReader(source) if row["phase"] == Phase.HOLD]
            if not holds:
                continue
            row = holds[len(holds) // 2]
            timeline = load_timeline(annotations / take.name / camera / "timeline.json")
            capture = cv2.VideoCapture(timeline["source"]["path"])
            try:
                capture.set(cv2.CAP_PROP_POS_FRAMES, int(row["frame_id"]))
                ok, image = capture.read()
                if not ok:
                    raise ValueError("Cannot read preview frame")
            finally:
                capture.release()
            points = json.loads(row["landmarks_json"])
            draw_landmarks(np.asarray(image, dtype=np.uint8), points, config.POSE_CONNECTIONS)
            for i in (0, 11, 12, 23, 24):
                if points:
                    x, y = points[i][:2]
                    cv2.putText(
                        image,
                        str(i),
                        (round(x * image.shape[1]), round(y * image.shape[0])),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.7,
                        (0, 0, 255),
                        2,
                    )
            cv2.putText(
                image,
                f"{take.name} {camera} frame {row['frame_id']} HOLD angle={row['angle']}",
                (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (0, 255, 255),
                2,
            )
            if not cv2.imwrite(str(take / f"{camera}-hold.jpg"), image):
                raise ValueError("Cannot write preview")


def evaluate_take(
    directory: Path, output: Path, select_subject: tuple[bool, bool]
) -> dict[str, Any]:
    timelines = [
        load_timeline(directory / f"camera_{camera}" / "timeline.json") for camera in (1, 2)
    ]
    paths = [Path(data["source"]["path"]) for data in timelines]
    for data, path in zip(timelines, paths, strict=True):
        if sha256(path) != data["source"]["sha256"]:
            raise ValueError(f"Video hash differs from annotation: {path}")
    sources = [data["source"] for data in timelines]
    if (
        sources[0]["fps"] != sources[1]["fps"]
        or sources[0]["total_frames"] != sources[1]["total_frames"]
    ):
        raise ValueError("Paired videos must have matching FPS and frame counts")
    fps = float(sources[0]["fps"])
    captures = [cv2.VideoCapture(str(path)) for path in paths]
    analyzers: list[PoseAnalyzer] = []
    rows: list[list[dict[str, Any]]] = [[], [], []]
    fusion = MultiCameraFusion()
    try:
        for slot in range(2):
            analyzers.append(
                PoseAnalyzer(
                    running_mode="VIDEO",
                    select_subject=select_subject[slot],
                    ramune_detector="rules",
                    source_fps=fps,
                    recognition_profile="multicam",
                )
            )
        for frame_id in range(sources[0]["total_frames"]):
            timestamp = frame_id / fps
            for slot, (capture, analyzer, timeline) in enumerate(
                zip(captures, analyzers, timelines, strict=True)
            ):
                ok, frame = capture.read()
                if not ok or frame.shape[:2] != (sources[slot]["height"], sources[slot]["width"]):
                    raise ValueError(f"Invalid video frame {frame_id}: {paths[slot]}")
                result = analyzer.process(frame, timestamp, frame_id)
                fusion.submit(slot, result)
                action, phase = labels_at(timeline, frame_id)
                rows[slot].append(
                    {
                        "frame_id": frame_id,
                        "timestamp": timestamp,
                        "action": action,
                        "phase": phase,
                        "gesture": current_state(result)["gesture"],
                        "raw_bow": result.get("bow_state", False),
                        "tracking": current_state(result)["tracking"],
                        "angle": result.get("bow_angle"),
                        "head_deviation": result.get("bow_head_deviation"),
                        "head_aligned": result.get("bow_head_aligned", False),
                        "hold_seconds": result.get("bow_hold_seconds", 0.0),
                        "subject_state": result.get("subject_state", "DISABLED"),
                        **geometry(result),
                        "minimum_bow_visibility": min(
                            (result["landmarks"][i][2] for i in (0, 11, 12, 23, 24)), default=None
                        )
                        if result["landmarks"]
                        else None,
                    }
                )
            fused = fusion.advance(timestamp)
            # Both synchronized annotations describe the same performance; use
            # their union for action/HOLD and retain per-view labels in the CSVs.
            current_rows = [rows[slot][-1] for slot in range(2)]
            phase = next(
                (
                    label
                    for label in (Phase.HOLD, Phase.BENDING, Phase.RETURNING)
                    if any(row["phase"] == label for row in current_rows)
                ),
                Gesture.NONE,
            )
            rows[2].append(
                {
                    "frame_id": frame_id,
                    "timestamp": timestamp,
                    "action": Gesture.BOW
                    if any(row["action"] == Gesture.BOW for row in current_rows)
                    else Gesture.NONE,
                    "phase": phase,
                    "gesture": current_state(fused)["gesture"],
                    "raw_bow": any(row["raw_bow"] for row in current_rows),
                    "tracking": current_state(fused)["tracking"],
                }
            )
    finally:
        for capture in captures:
            capture.release()
        for analyzer in analyzers:
            analyzer.close()
    output.mkdir(parents=True, exist_ok=True)
    for name, values in zip(("camera_1", "camera_2", "fused"), rows, strict=True):
        with (output / f"{name}.csv").open("w", newline="", encoding="utf-8") as target:
            writer = csv.DictWriter(target, fieldnames=list(values[0]))
            writer.writeheader()
            writer.writerows(values)
    metadata_path = paths[0].parent / "metadata.json"
    metadata = json.loads(metadata_path.read_text()) if metadata_path.exists() else {}
    return {
        "split": "held_out" if directory.name == "take_001" else "development",
        "sources": sources,
        "fps": fps,
        "repeated_batches": metadata.get("repeated_batches"),
        "views": {
            name: summarize(values, fps)
            for name, values in zip(("camera_1", "camera_2", "fused"), rows, strict=True)
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("annotations", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--pose-model",
        choices=("configured", "lite", "full", "heavy"),
        default="configured",
        help="Offline model comparison; leaves application configuration unchanged",
    )
    parser.add_argument(
        "--takes",
        nargs="+",
        choices=[f"take_{i:03}" for i in range(1, 5)],
        default=[f"take_{i:03}" for i in range(1, 5)],
    )
    parser.add_argument(
        "--disable-subject-selection",
        action="store_true",
        help="Diagnostic full-frame inference on both cameras",
    )
    args = parser.parse_args()
    if args.pose_model != "configured":
        pose_module.POSE_MODEL_PATH = (
            config.PROJECT_ROOT / f"pose_landmarker_{args.pose_model}.task"
        )
        pose_module.POSE_MODEL_URL = (
            "https://storage.googleapis.com/mediapipe-models/pose_landmarker/"
            f"pose_landmarker_{args.pose_model}/float16/1/pose_landmarker_{args.pose_model}.task"
        )
    directories = [args.annotations / take for take in sorted(set(args.takes))]
    if not all(directory.is_dir() for directory in directories):
        parser.error("Missing selected take directory")
    select_subject = (
        (False, False) if args.disable_subject_selection else config.MULTICAM_SELECT_SUBJECT
    )
    report: dict[str, Any] = {
        "revision": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "protocol": "All encoded frames, frame_id / FPS; multicam profile; no live scheduling/drop simulation.",
        "fused_annotation": "Union of paired BOW intervals; phase precedence HOLD, BENDING, RETURNING.",
        "settings": {
            "select_subject": select_subject,
            "subject_area": config.SUBJECT_AREA,
            "model_path": str(pose_module.POSE_MODEL_PATH),
            "model_sha256": None,
            "recognizer_sha256": sha256(Path(getfile(BowAnalyzer))),
            **{name: getattr(config, name) for name in dir(config) if name.startswith("BOW_")},
        },
        "takes": {},
    }
    for directory in directories:
        print(f"Evaluating {directory.name}", flush=True)
        report["takes"][directory.name] = evaluate_take(
            directory, args.output / directory.name, select_subject
        )
    report["settings"]["model_sha256"] = sha256(pose_module.POSE_MODEL_PATH)
    save_hold_previews(args.annotations, args.output)
    (args.output / "summary.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    for take, value in report["takes"].items():
        for name, metrics in value["views"].items():
            hold = metrics["phases"][Phase.HOLD]
            print(
                f"{take} {name}: HOLD {hold['bow_frames']}/{hold['frames']}, "
                f"false positive frames {metrics['false_positive_frames']}"
            )


if __name__ == "__main__":
    main()
