"""Evaluate native-rate tracking and display smoothing against bright annotations."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np

from gesture_detection.config import POSE_CONNECTIONS
from gesture_detection.landmark_smoothing import LandmarkSmoother
from gesture_detection.pose_worker import PoseAnalyzer
from gesture_detection.rendering import draw_landmarks

from .evaluate_landmark_annotations import LANDMARK_INDICES, load_frames, reference_scale


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--annotations", type=Path, required=True)
    parser.add_argument("--videos", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--preview", type=Path)
    args = parser.parse_args()
    sessions = defaultdict(dict)
    for frame in load_frames(args.annotations):
        sessions[frame.session][frame.frame_id] = frame
    report = {}
    writer = None
    try:
        for session, annotations in sessions.items():
            print(session, flush=True)
            capture = cv2.VideoCapture(str(args.videos / f"{session}.mp4"))
            if not capture.isOpened():
                raise ValueError(f"Cannot open {session}")
            fps = capture.get(cv2.CAP_PROP_FPS)
            analyzer = PoseAnalyzer(running_mode="VIDEO")
            smoother = LandmarkSmoother()
            errors = {"raw": [], "smooth": []}
            steps = {"raw": [], "smooth": []}
            previous = {}
            counts = dict(present=0, detected=0, absent=0, false_positive=0, marked=0)
            frame_id = 0
            try:
                while True:
                    ok, image = capture.read()
                    if not ok:
                        break
                    timestamp = frame_id / fps
                    raw = analyzer.process(image, timestamp, frame_id)["landmarks"]
                    smooth = smoother.update(raw, timestamp)
                    height, width = image.shape[:2]
                    for name, points in [("raw", raw), ("smooth", smooth)]:
                        # Same visible pairs for both conditions; motion includes real movement.
                        old = previous.get(name, [])
                        if old and points:
                            for index in LANDMARK_INDICES.values():
                                if points[index][2] > 0.5 and old[index][2] > 0.5:
                                    steps[name].append(
                                        float(
                                            np.hypot(
                                                (points[index][0] - old[index][0]) * width / height,
                                                points[index][1] - old[index][1],
                                            )
                                        )
                                    )
                        previous[name] = points
                    if frame_id in annotations:
                        annotated = annotations[frame_id]
                        present = any(
                            a.status in {"marked", "uncertain"} for a in annotated.annotations
                        )
                        counts["present" if present else "absent"] += 1
                        counts["detected" if present else "false_positive"] += bool(raw)
                        scale = reference_scale(annotated.annotations, width, height)
                        for item in annotated.annotations:
                            if item.status != "marked":
                                continue
                            counts["marked"] += 1
                            for name, points in [("raw", raw), ("smooth", smooth)]:
                                if points:
                                    x, y, _ = points[LANDMARK_INDICES[item.landmark]]
                                    errors[name].append(
                                        float(
                                            np.hypot(
                                                x * width - item.x_px,
                                                y * height - item.y_px,
                                            )
                                            / scale
                                        )
                                    )
                    if args.preview and session == "ramune1_4-7":
                        panels = []
                        for label, points in [("RAW", raw), ("SMOOTH (display)", smooth)]:
                            panel = cv2.resize(image, (640, 360))
                            draw_landmarks(panel, points, POSE_CONNECTIONS)
                            cv2.putText(
                                panel,
                                label,
                                (10, 25),
                                cv2.FONT_HERSHEY_SIMPLEX,
                                0.7,
                                (0, 255, 255),
                                2,
                            )
                            panels.append(panel)
                        if writer is None:
                            args.preview.parent.mkdir(parents=True, exist_ok=True)
                            writer = cv2.VideoWriter(
                                str(args.preview), cv2.VideoWriter_fourcc(*"mp4v"), fps, (1280, 360)
                            )
                            if not writer.isOpened():
                                raise ValueError("Cannot open preview writer")
                        writer.write(np.hstack(panels))
                    frame_id += 1
            finally:
                analyzer.close()
                capture.release()
            report[session] = {
                "frames": frame_id,
                "fps": fps,
                **counts,
                **{
                    name: {
                        "correct_points": sum(e <= 0.2 for e in errors[name]),
                        "pck_at_0_2": sum(e <= 0.2 for e in errors[name]) / counts["marked"],
                        "step_p95_image_height": float(np.percentile(steps[name], 95))
                        if steps[name]
                        else None,
                        "step_pairs": len(steps[name]),
                    }
                    for name in errors
                },
            }
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(report, indent=2) + "\n")
    finally:
        if writer is not None:
            writer.release()


if __name__ == "__main__":
    main()
