"""Synthetic two-copy signal replay: test rearming without resetting temporal state.

This is not a continuous-camera evaluation. Pose and classifier predictions come
from separately processed source clips; only the temporal state spans the join.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

import numpy as np

from .evaluate_opening_temporal import TemporalConfig, apply_temporal, release_evidence
from .evaluate_timeline import ROOT, digest, extract, opening_diagnostics, positive_runs


def repeat_clip(
    clip: dict, phase: np.ndarray, action: np.ndarray, missing_seconds: float = 0.0
) -> tuple[dict, np.ndarray, np.ndarray, int]:
    gap = round(missing_seconds * clip["fps"])
    offset = len(phase) + gap
    repeated = dict(clip)
    for key in ("phase", "action"):
        repeated[key] = np.concatenate([clip[key], np.full(gap, -1, dtype=int), clip[key]])
    repeated["points"] = np.concatenate([clip["points"], np.zeros((gap, 33, 3)), clip["points"]])
    for key in ("ramune_intervals", "opening_intervals"):
        repeated[key] = list(clip[key]) + [(a + offset, b + offset) for a, b in clip[key]]
    repeated_phase = np.concatenate([phase, np.zeros(gap, dtype=int), phase])
    repeated_action = np.concatenate([action, np.zeros(gap, dtype=int), action])
    return repeated, repeated_phase, repeated_action, offset


def summarize(rows: list[dict]) -> dict:
    positive = [row for row in rows if row["anchors_per_copy"]]
    first = sum(row["first_hit"] for row in positive)
    return dict(
        clips=len(positive),
        first_hits=first,
        second_hits=sum(row["second_hit"] for row in positive),
        second_hits_given_first=sum(row["first_hit"] and row["second_hit"] for row in positive),
        both_hit_fraction=sum(row["first_hit"] and row["second_hit"] for row in positive) / first
        if first
        else None,
        reappearance_runs=sum(row["diagnostics"]["reappearance_runs"] for row in rows),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, default=ROOT / "docs/0924-opening-repetition-results.json"
    )
    args = parser.parse_args()
    classifier_path = ROOT / "docs/0924-timeline-central-results.json"
    temporal_path = ROOT / "docs/0924-opening-temporal-results.json"
    classifier = json.loads(classifier_path.read_text())
    temporal = json.loads(temporal_path.read_text())
    configs = {
        row["video"]: TemporalConfig(**row["config"])
        for row in temporal["families"]["prepared_hands"]["clips"]
    }
    sources = {row["name"]: row for row in classifier["sources"]}
    rows = []
    with np.load(ROOT / classifier["frame_predictions"]) as predictions:
        for name, config in configs.items():
            path = ROOT / "shared/annotations/0924" / name / "timeline.json"
            if digest(path) != sources[name]["annotation_sha256"]:
                raise ValueError("Annotations changed since frozen predictions")
            clip = extract(
                path, ROOT / "shared/results/0924-cache", select_subject=False, central_mask=True
            )
            phase, action = predictions["phase/" + name], predictions["action/" + name]
            standalone, _ = apply_temporal(phase, action, clip["points"], clip["fps"], config)
            for missing in (0.0, 0.5, 2.0):
                repeated, p, a, offset = repeat_clip(clip, phase, action, missing)
                output, events = apply_temporal(p, a, repeated["points"], clip["fps"], config)
                np.testing.assert_array_equal(output[: len(phase)], standalone)
                diagnostic = opening_diagnostics(repeated, output)
                count = len(clip["opening_intervals"])
                first_hit = any(d["matched_run"] is not None for d in diagnostic["details"][:count])
                second_hit = any(
                    d["matched_run"] is not None for d in diagnostic["details"][count:]
                )
                release = positive_runs(
                    release_evidence(repeated["points"], a, config.release_mode)
                )
                rows.append(
                    dict(
                        video=name,
                        group=clip["group"],
                        missing_seconds=missing,
                        config=asdict(config),
                        anchors_per_copy=count,
                        join_frame=offset,
                        first_hit=first_hit,
                        second_hit=second_hit,
                        notification_frames=events,
                        release_runs=release,
                        diagnostics=diagnostic,
                    )
                )
    report = dict(
        protocol=__doc__,
        sources=classifier["sources"],
        classifier_report_sha256=digest(classifier_path),
        temporal_report_sha256=digest(temporal_path),
        script_sha256=digest(Path(__file__)),
        clips=rows,
        aggregates={},
    )
    for missing in (0.0, 0.5, 2.0):
        report["aggregates"][str(missing)] = {
            env: summarize(
                [
                    row
                    for row in rows
                    if row["missing_seconds"] == missing and bool(row["group"]) == (env == "behind")
                ]
            )
            for env in ("behind", "without")
        }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report["aggregates"], indent=2), flush=True)


if __name__ == "__main__":
    main()
