"""Rescore cached predictions against one frozen set of partial annotations."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import cv2

from .evaluate_timeline import (
    LANDMARK_NAMES,
    aggregate,
    landmark_errors,
    summarize,
    summarize_landmarks,
)
from .video_annotation import load_timeline, sha256


def rescore(data: dict[str, Any], rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    source = data["source"]
    if len(rows) != source["total_frames"]:
        raise ValueError("Cached frame count differs from annotation")
    annotations = {row["frame_id"]: row["points"] for row in data["landmarks"]}
    scored = []
    for frame_id, row in enumerate(rows):
        if row["frame_id"] != frame_id or abs(row["timestamp"] - frame_id / source["fps"]) > 1e-6:
            raise ValueError("Cached frame order/timestamps differ from annotation")
        scored.append(
            {
                **row,
                "landmark_errors": landmark_errors(
                    annotations.get(frame_id, {}),
                    row["landmarks"],
                    source["width"],
                    source["height"],
                ),
            }
        )
    return scored


def previews(data: dict[str, Any], rows: list[dict[str, Any]], video: Path, output: Path) -> None:
    capture = cv2.VideoCapture(str(video))
    try:
        for annotation in data["landmarks"]:
            frame_id = annotation["frame_id"]
            marked = {
                name: p for name, p in annotation["points"].items() if p["status"] == "marked"
            }
            if not marked:
                continue
            capture.set(cv2.CAP_PROP_POS_FRAMES, frame_id)
            ok, frame = capture.read()
            if not ok:
                raise ValueError(f"Cannot read preview: {video}, frame {frame_id}")
            points = rows[frame_id]["landmarks"]
            for name, point in marked.items():
                index = LANDMARK_NAMES.index(name)
                target = (round(point["x_px"]), round(point["y_px"]))
                if points:
                    x, y, _ = points[index]
                    predicted = (round(x * frame.shape[1]), round(y * frame.shape[0]))
                    cv2.line(frame, target, predicted, (0, 255, 255), 1)
                    cv2.drawMarker(frame, predicted, (0, 0, 255), cv2.MARKER_CROSS, 12, 2)
                cv2.circle(frame, target, 5, (0, 255, 0), 2)
                cv2.putText(
                    frame,
                    f"{index}:{name}",
                    (target[0] + 6, target[1]),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.4,
                    (0, 255, 0),
                    1,
                )
            cv2.putText(
                frame,
                f"frame {frame_id}: green=annotation red=prediction",
                (10, 25),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (255, 255, 255),
                2,
            )
            output.mkdir(parents=True, exist_ok=True)
            if not cv2.imwrite(str(output / f"frame_{frame_id:06}.jpg"), frame):
                raise OSError("Cannot save preview")
    finally:
        capture.release()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("runs", type=Path, nargs="+")
    parser.add_argument("--annotations", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--videos", type=Path, help="Also save marked-frame comparison images")
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Use a new output directory")
    timelines = sorted(args.annotations.rglob("timeline.json"))
    if not timelines:
        parser.error("No timelines")
    frozen = {}
    for path in timelines:
        relative = path.relative_to(args.annotations)
        snapshot = args.output / "annotations" / relative
        snapshot.parent.mkdir(parents=True, exist_ok=True)
        snapshot.write_bytes(path.read_bytes())
        frozen[str(relative.parent)] = (load_timeline(snapshot), sha256(snapshot))
    comparison = {}
    for run in args.runs:
        cached = json.loads((run / "summary.json").read_text(encoding="utf-8"))
        clips = {}
        all_errors = []
        for name, (data, annotation_hash) in frozen.items():
            source = cached["clips"][name]["source"]
            if any(
                source[key] != data["source"][key]
                for key in ("sha256", "fps", "total_frames", "width", "height")
            ):
                raise ValueError(f"Cached source differs from annotation: {run}/{name}")
            rows = rescore(
                data,
                [
                    json.loads(line)
                    for line in (run / name / "frames.jsonl")
                    .read_text(encoding="utf-8")
                    .splitlines()
                ],
            )
            clips[name] = {
                "annotation_sha256": annotation_hash,
                **summarize(data, rows, cached["settings"]["event_tolerance_seconds"]),
            }
            all_errors.extend(point for row in rows for point in row["landmark_errors"])
            if args.videos is not None:
                video = args.videos / f"{name}.mp4"
                if sha256(video) != source["sha256"]:
                    raise ValueError(f"Video hash mismatch: {video}")
                previews(data, rows, video, args.output / run.name / name)
        comparison[str(run)] = {
            "cached_summary_sha256": sha256(run / "summary.json"),
            "clips": clips,
            "actions": aggregate(clips),
            "landmarks": summarize_landmarks(all_errors),
        }
        print(run.name, comparison[str(run)]["landmarks"], flush=True)
    (args.output / "comparison.json").write_text(
        json.dumps(comparison, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
