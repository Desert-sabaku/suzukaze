"""Measure output persistence and a fixed causal stillness smoothing ablation."""

import json
from collections import Counter
from pathlib import Path
from unittest.mock import patch

import numpy as np

from gesture_detection import landmark_smoothing
from gesture_detection.relaxing import RelaxingAnalyzer

from .evaluate_multicam import ROOT, digest, score
from .evaluate_multicam_followup import objects

TAU = 0.15  # Fixed before scoring: time-based, equal physical duration for both cameras.


def output_runs(predictions: list[dict], start: int, end: int, label: str, fps: float) -> dict:
    mask = np.array([p["gesture"] == label for p in predictions[start : end + 1]], dtype=int)
    changes = np.diff(np.r_[0, mask, 0])
    lengths = np.flatnonzero(changes == -1) - np.flatnonzero(changes == 1)
    return dict(
        seconds=float(mask.sum() / fps),
        longest_seconds=float(lengths.max() / fps) if len(lengths) else 0,
        coverage=float(mask.mean()),
        runs=len(lengths),
    )


def smoothed_relaxing(
    points: np.ndarray, predictions: list[dict], fps: float, aspect: float
) -> list[dict]:
    """Only replace stillness; other gesture outputs/events use the frozen replay."""
    smoother = landmark_smoothing.LandmarkSmoother()
    detector = RelaxingAnalyzer()
    output = []
    with patch.object(landmark_smoothing, "POSE_DISPLAY_TIME_CONSTANT", TAU):
        for i, frame in enumerate(points):
            raw = frame.tolist() if frame.any() else []
            smooth = smoother.update(raw, i / fps)
            if smooth:
                active = detector.update(objects(np.asarray(smooth)), i / fps, aspect)
            else:
                detector.reset()
                active = False
            row = dict(predictions[i])
            if row["gesture"] in ("NONE", "RELAXING"):
                row["gesture"] = "RELAXING" if active else "NONE"
            output.append(row)
    return output


def main() -> None:
    source = ROOT / "docs/0928-multicam-followup-results.json"
    report = json.loads(source.read_text())
    baseline = json.loads((ROOT / "docs/0928-multicam-results.json").read_text())
    fps_lookup = {(r["take"], r["camera"]): r["effective_fps"] for r in baseline["rows"]}
    output_dir = ROOT / "shared/results/0928-multicam-followup"
    rows = []
    for original in report["rows"]:
        if original["profile"] not in ("rules_full", "rules_camera_roi"):
            continue
        take, camera = original["take"], original["camera"]
        path = ROOT / "shared/annotations" / take / f"camera_{camera:02}" / "timeline.json"
        annotation = json.loads(path.read_text()) if path.exists() else None
        intervals = annotation["intervals"] if annotation else []
        fps = fps_lookup[take, camera]
        cached = json.loads((ROOT / original["diagnostics"]).read_text())["predictions"]
        with np.load(ROOT / original["cache"]) as cache:
            points = cache["points"]
        aspect = (
            annotation["source"]["width"] / annotation["source"]["height"]
            if annotation
            else 1280 / 720
        )
        for suffix, predictions in [
            ("", cached),
            ("_smooth_relaxing", smoothed_relaxing(points, cached, fps, aspect)),
        ]:
            profile = original["profile"] + suffix
            row = dict(
                take=take,
                camera=camera,
                profile=profile,
                metrics=score(intervals, predictions, fps),
                persistence=[],
            )
            for action in intervals:
                if action["track"] != "action":
                    continue
                label, start, end = action["label"], action["start_frame"], action["end_frame"]
                opened = [
                    x
                    for x in intervals
                    if x["track"] == "ramune_phase"
                    and x["label"] == "OPENED"
                    and start <= x["start_frame"] <= x["end_frame"] <= end
                ]
                pulses = [p["frame"] for p in predictions[start : end + 1] if label in p["events"]]
                row["persistence"].append(
                    dict(
                        label=label,
                        start_frame=start,
                        end_frame=end,
                        **output_runs(predictions, start, end, label, fps),
                        event_frames=pulses,
                        opened_start=opened[0]["start_frame"] if opened else None,
                        opened_end=opened[0]["end_frame"] if opened else None,
                        delay_from_opened_start=(pulses[0] - opened[0]["start_frame"]) / fps
                        if pulses and opened
                        else None,
                    )
                )
            rows.append(row)
            if suffix:
                (output_dir / f"{take}-camera_{camera:02}-{profile}.json").write_text(
                    json.dumps(predictions, indent=2) + "\n"
                )
    summary = {}
    for profile in sorted({r["profile"] for r in rows}):
        for camera in (1, 2):
            chosen = [
                r
                for r in rows
                if r["profile"] == profile and r["camera"] == camera and r["metrics"]["trials"]
            ]
            wrong, outside = Counter(), Counter()
            for row in chosen:
                wrong.update(row["metrics"]["wrong_label_seconds"])
                outside.update(row["metrics"]["unlabelled_output_seconds"])
            summary[f"{profile}/camera{camera}"] = dict(
                relaxing_hits=sum(
                    t["detected"]
                    for r in chosen
                    for t in r["metrics"]["trials"]
                    if t["label"] == "RELAXING"
                ),
                relaxing_wrong_label_seconds=wrong["RELAXING"],
                relaxing_unlabelled_seconds=outside["RELAXING"],
            )
    result = dict(
        source_sha256=digest(source),
        script_sha256=digest(Path(__file__)),
        tau_seconds=TAU,
        summary=summary,
        rows=rows,
        note="Causal EMA only for stillness, unchanged speed/drift/dwell thresholds; exploratory same-footage result, not independent validation.",
    )
    (ROOT / "docs/0928-multicam-persistence.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(summary, indent=2))
    for row in rows:
        for interval in row["persistence"]:
            if interval["label"] in ("RELAXING", "RAMUNE"):
                print(row["take"], row["camera"], row["profile"], json.dumps(interval))


if __name__ == "__main__":
    main()
