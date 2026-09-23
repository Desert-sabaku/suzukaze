"""Compare subject selection with legacy single-person tracking on controls."""

from __future__ import annotations

import argparse
import json
import time
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np

from gesture_detection.app import FrameClock, GestureApplication
from gesture_detection.config import (
    SUBJECT_AREA,
    SUBJECT_MIN_SHOULDER_WIDTH,
    SUBJECT_MIN_TORSO_HEIGHT,
)
from gesture_detection.pose_worker import PoseAnalyzer
from gesture_detection.subject_selection import SubjectSelector


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--videos", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--previews", type=Path, required=True)
    args = parser.parse_args()
    args.previews.mkdir(parents=True, exist_ok=True)
    report = {
        "area": SUBJECT_AREA,
        "min_torso_height": SUBJECT_MIN_TORSO_HEIGHT,
        "min_shoulder_width": SUBJECT_MIN_SHOULDER_WIDTH,
        "clips": [],
    }
    for source in sorted(args.videos.glob("*.mp4")):
        print(source.name, flush=True)
        cap = cv2.VideoCapture(str(source))
        if not cap.isOpened():
            raise ValueError(f"Cannot open {source}")
        analyzers = {}
        writer = None
        counts = {name: Counter() for name in ("legacy", "selected")}
        timings = {name: [] for name in counts}
        snapshots = []
        clock = FrameClock(is_video=True)
        frame_id = 0
        next_snapshot = 2.0
        try:
            analyzers["legacy"] = PoseAnalyzer(select_subject=False)
            analyzers["selected"] = PoseAnalyzer(select_subject=True)
            writer = cv2.VideoWriter(
                str(args.previews / f"{source.stem}.mp4"),
                cv2.VideoWriter_fourcc(*"mp4v"),
                cap.get(cv2.CAP_PROP_FPS),
                (1280, 360),
            )
            if not writer.isOpened():
                raise ValueError("Cannot open comparison video")
            while True:
                ok, frame = cap.read()
                if not ok:
                    break
                timestamp = clock.timestamp(cap)
                panels = []
                for name, analyzer in analyzers.items():
                    started = time.perf_counter()
                    result = analyzer.process(frame, timestamp, frame_id)
                    timings[name].append((time.perf_counter() - started) * 1000)
                    counts[name]["frames"] += 1
                    points = [
                        SimpleNamespace(x=x, y=y, visibility=v) for x, y, v in result["landmarks"]
                    ]
                    if points:
                        counts[name]["pose_frames"] += 1
                        eligible = SubjectSelector.candidate(
                            points, frame.shape[1] / frame.shape[0]
                        )
                        counts[name][
                            "eligible_geometry_frames" if eligible else "outside_geometry_frames"
                        ] += 1
                    counts[name][result.get("subject_state", "LEGACY")] += 1
                    panel = cv2.resize(
                        GestureApplication._annotate_frame(frame, result), (640, 360)
                    )
                    cv2.putText(
                        panel,
                        f"{name} {timestamp:.2f}s",
                        (350, 28),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.65,
                        (0, 255, 255),
                        2,
                    )
                    panels.append(panel)
                comparison = np.hstack(panels)
                writer.write(comparison)
                if timestamp >= next_snapshot and next_snapshot <= 8:
                    snapshots.append(comparison)
                    next_snapshot += 2
                frame_id += 1
        finally:
            cap.release()
            if writer is not None:
                writer.release()
            for analyzer in analyzers.values():
                analyzer.close()
        if snapshots:
            cv2.imwrite(str(args.previews / f"{source.stem}.jpg"), np.vstack(snapshots))
        report["clips"].append(
            {
                "source": source.name,
                "conditions": {
                    name: {
                        **counts[name],
                        "median_inference_ms": float(np.median(timings[name])),
                        "p95_inference_ms": float(np.percentile(timings[name], 95)),
                    }
                    for name in counts
                },
            }
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
