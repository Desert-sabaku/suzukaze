"""Causal late-fusion baseline, scored against both annotation clocks."""

import json
import math
from collections import Counter
from pathlib import Path

from .evaluate_multicam import ROOT, digest
from .evaluate_multicam_temporal import envelope
from .multicam_temporal_metrics import temporal_score

PRIORITY = {"NONE": 0, "RELAXING": 1, "FANNING": 2, "UCHIMIZU": 3, "RAMUNE": 4}
GRID_FPS = 30.0
EVENT_DEDUP_SECONDS = 0.6
MAX_AGE = 0.2


def fuse(streams: list[list[dict]], duration: float) -> tuple[list[dict], dict]:
    """Use only observations received by each tick; no annotation-based choice."""
    pointers = [0] * len(streams)
    latest = [None] * len(streams)
    last_event = {}
    suppressed, conflicts = Counter(), 0
    output = []
    for i in range(math.ceil(duration * GRID_FPS)):
        now = i / GRID_FPS
        arrivals = []
        for camera, stream in enumerate(streams):
            while (
                pointers[camera] < len(stream)
                and stream[pointers[camera]]["seconds"] <= now + 1e-9
            ):
                row = stream[pointers[camera]]
                latest[camera] = row
                for label in row["events"]:
                    arrivals.append((row["seconds"], camera, label))
                pointers[camera] += 1
        events = []
        for timestamp, _, label in sorted(arrivals):
            if timestamp - last_event.get(label, -math.inf) < EVENT_DEDUP_SECONDS:
                suppressed[label] += 1
            else:
                last_event[label] = timestamp
                events.append(label)
        candidates = {
            row["gesture"]
            for row in latest
            if row is not None and now - row["seconds"] <= MAX_AGE
        }
        candidates.update(events)
        candidates.discard("NONE")
        if len(candidates) > 1:
            conflicts += 1
        gesture = max(candidates, key=PRIORITY.__getitem__) if candidates else "NONE"
        output.append(dict(frame=i, seconds=now, gesture=gesture, events=events))
    return output, dict(
        suppressed_events=dict(suppressed),
        conflicting_state_seconds=conflicts / GRID_FPS,
    )


def clock_intervals(intervals: list[dict], source_fps: float) -> list[dict]:
    """Map half-open native frame cells to the first causal output ticks."""
    return [
        dict(
            x,
            start_frame=math.ceil(x["start_frame"] / source_fps * GRID_FPS - 1e-9),
            end_frame=math.ceil((x["end_frame"] + 1) / source_fps * GRID_FPS - 1e-9)
            - 1,
        )
        for x in intervals
    ]


def main() -> None:
    temporal_path = ROOT / "shared/results/0928-multicam-temporal-results.json"
    temporal = json.loads(temporal_path.read_text())
    baseline = json.loads(
        (ROOT / "shared/results/0928-multicam-results.json").read_text()
    )
    output = ROOT / "shared/results/0928-multicam-temporal"
    rows, ramune = [], []
    for row in temporal["rows"]:
        if row["variant"] not in ("baseline", "follow_peak", "follow_wait"):
            continue
        for trial in row["metrics"]["trials"]:
            if trial["label"] == "RAMUNE" and trial["detected"]:
                ramune.append(
                    dict(
                        take=row["take"],
                        camera=row["camera"],
                        input=row["input"],
                        variant=row["variant"],
                        **trial,
                    )
                )
    configurations = (
        ("rules_full", "baseline"),
        ("rules_full", "follow_peak"),
        ("rules_camera_roi", "baseline"),
    )
    for profile, variant in configurations:
        for take in sorted({r["take"] for r in temporal["rows"]}):
            selected = sorted(
                [
                    r
                    for r in temporal["rows"]
                    if r["take"] == take
                    and r["input"] == profile
                    and r["variant"] == variant
                ],
                key=lambda r: r["camera"],
            )
            if len(selected) != 2:
                raise ValueError("Expected two camera streams")
            session = json.loads(
                (ROOT / "shared/videos/0928" / take / "session.json").read_text()
            )
            streams = [
                json.loads((ROOT / r["predictions"]).read_text()) for r in selected
            ]
            fused, diagnostic = fuse(streams, session["duration_seconds"])
            for suffix, predictions in (("", fused), ("_envelope", envelope(fused))):
                name = f"{profile}-{variant}-fusion{suffix}"
                path = output / f"{take}-{name}.json"
                path.write_text(json.dumps(predictions, indent=2) + "\n")
                for camera in (1, 2):
                    annotation_path = (
                        ROOT
                        / "shared/annotations"
                        / take
                        / f"camera_{camera:02}"
                        / "timeline.json"
                    )
                    annotation = (
                        json.loads(annotation_path.read_text())
                        if annotation_path.exists()
                        else None
                    )
                    reference = next(
                        r
                        for r in baseline["rows"]
                        if r["take"] == take and r["camera"] == camera
                    )
                    if (
                        annotation
                        and digest(annotation_path) != reference["annotation_sha256"]
                    ):
                        raise ValueError("Annotation changed")
                    intervals = (
                        clock_intervals(
                            annotation["intervals"], reference["effective_fps"]
                        )
                        if annotation
                        else []
                    )
                    rows.append(
                        dict(
                            take=take,
                            profile=name,
                            annotation_camera=camera,
                            metrics=temporal_score(intervals, predictions, GRID_FPS),
                            diagnostic=diagnostic,
                            predictions=str(path.relative_to(ROOT)),
                        )
                    )
    summary = {}
    for profile in sorted({r["profile"] for r in rows}):
        for camera in (1, 2):
            selected = [
                r
                for r in rows
                if r["profile"] == profile
                and r["annotation_camera"] == camera
                and r["metrics"]["trials"]
            ]
            hits, repeated, extras, unmatched, wrong, outside = (
                Counter() for _ in range(6)
            )
            tails, stable = [], Counter()
            for row in selected:
                for trial in row["metrics"]["trials"]:
                    label = trial["label"]
                    hits[label] += trial["detected"]
                    repeated[label] += trial["reappearances"]
                    extras[label] += trial["extra_events"]
                    stable[label] += (
                        trial["detected"]
                        and trial["output_runs"] == 1
                        and not trial["extra_events"]
                    )
                    tails.append(trial["tail_overrun_seconds"])
                unmatched.update(row["metrics"]["unmatched_events"])
                wrong.update(row["metrics"]["wrong_label_seconds"])
                outside.update(row["metrics"]["unlabelled_output_seconds"])
            summary[f"{profile}/annotation{camera}"] = dict(
                detections=dict(hits),
                single_run_trials=dict(stable),
                reappearances=dict(repeated),
                extra_events=dict(extras),
                unmatched_events=dict(unmatched),
                wrong_label_seconds=dict(wrong),
                unlabelled_output_seconds=dict(outside),
                max_tail_seconds=max(tails, default=0),
            )
    report = dict(
        temporal_sha256=digest(temporal_path),
        script_sha256=digest(Path(__file__)),
        grid_fps=GRID_FPS,
        event_dedup_seconds=EVENT_DEDUP_SECONDS,
        max_age=MAX_AGE,
        priority=PRIORITY,
        summary=summary,
        rows=rows,
        ramune_detections=ramune,
        limitations=[
            "Uniform-capture clock approximation; annotation1/2 are sensitivity checks, not two independent datasets.",
            "State priority and 0.6s pulse dedup are fixed naive baselines, not selected per trial.",
            "Single-run trial count does not guarantee full action coverage or correct event timing beyond the stated tolerance.",
        ],
    )
    (ROOT / "shared/results/0928-multicam-fusion-results.json").write_text(
        json.dumps(report, indent=2) + "\n"
    )
    print(json.dumps(summary, indent=2))
    print("RAMUNE detections", json.dumps(ramune, indent=2))


if __name__ == "__main__":
    main()
