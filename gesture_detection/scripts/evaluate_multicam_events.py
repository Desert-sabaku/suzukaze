"""Gesture-specific criteria, anchored scoop evidence, and observed rearming."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from unittest.mock import patch

import numpy as np

from gesture_detection import hand_gesture
from gesture_detection.recognition import RecognitionCoordinator
from gesture_detection.uchimizu import UchimizuAnalyzer

from .evaluate_multicam import ROOT, digest
from .evaluate_multicam_followup import objects
from .evaluate_multicam_fusion import GRID_FPS, clock_intervals, fuse
from .evaluate_multicam_temporal import FollowingRamune
from .multicam_event_policy import AnchoredUchimizu, EventLatch, apply_gesture_policy
from .multicam_temporal_metrics import temporal_score

VARIANTS = (
    "peak",
    "peak_anchor",
    "peak_latch",
    "peak_anchor_latch",
    "peak_anchor_hand_latch",
)


def infer_events(
    points: np.ndarray, fps: float, aspect: float, variant: str
) -> tuple[list[dict], dict]:
    anchored, latched = "anchor" in variant, "latch" in variant
    AnchoredUchimizu.audit = Counter()
    latch = EventLatch(active_hand_release="hand_latch" in variant)
    output, event_evidence = [], []
    hand_setups, ramune_setup = {}, None
    with patch.object(
        hand_gesture,
        "UchimizuAnalyzer",
        AnchoredUchimizu if anchored else UchimizuAnalyzer,
    ):
        coordinator = RecognitionCoordinator(ramune_detector="rules", source_fps=fps)
        coordinator.ramune = FollowingRamune()
        for i, frame in enumerate(points):
            previous_hands = [
                (id(h.uchimizu), h.uchimizu.state) for h in coordinator.hands
            ]
            previous_ramune = coordinator.ramune.state
            result = coordinator.process(
                objects(frame), i / fps, i, aspect_ratio=aspect
            )
            for hand, previous in zip(coordinator.hands, previous_hands, strict=True):
                if hand.uchimizu.state == "READY" and previous != (
                    id(hand.uchimizu),
                    "READY",
                ):
                    hand_setups[hand.wrist_index] = i / fps
                elif hand.uchimizu.state == "IDLE":
                    hand_setups.pop(hand.wrist_index, None)
            if coordinator.ramune.state == "FORMING" and previous_ramune != "FORMING":
                ramune_setup = i / fps
            row = dict(
                frame=i,
                seconds=i / fps,
                gesture=result["current"]["gesture"],
                events=list(result["occurrences"]),
                ramune_state=result["ramune_state"],
            )
            event_wrists, event_setups = {}, {}
            for hand in coordinator.hands:
                if (
                    "UCHIMIZU" in row["events"]
                    and hand.uchimizu.completed_at == i / fps
                ):
                    event_wrists["UCHIMIZU"] = hand.wrist_index
                    if hand.wrist_index in hand_setups:
                        event_setups["UCHIMIZU"] = hand_setups[hand.wrist_index]
            if "RAMUNE" in row["events"] and coordinator.ramune.base_index is not None:
                event_wrists["RAMUNE"] = 31 - coordinator.ramune.base_index
                if ramune_setup is not None:
                    event_setups["RAMUNE"] = ramune_setup
            if event_wrists:
                event_evidence.append(
                    dict(seconds=i / fps, wrists=event_wrists, setups=event_setups)
                )
            output.append(latch.update(row, frame, event_wrists) if latched else row)
    return output, dict(
        scoop=dict(AnchoredUchimizu.audit),
        latch=dict(latch.audit),
        event_evidence=event_evidence,
    )


def shared_latch(
    predictions: list[dict],
    views: list[tuple[np.ndarray, float]],
    evidence: list[list[dict]],
    *,
    require_new_setup: bool = False,
) -> tuple[list[dict], dict]:
    """One event lock; either recent view may supply observed release evidence."""
    latch = EventLatch(active_hand_release=True, require_new_setup=require_new_setup)
    output = []
    for row in predictions:
        now = row["seconds"]
        recent = []
        for points, fps in views:
            index = min(len(points) - 1, int(now * fps + 1e-9))
            if index >= 0 and now - index / fps <= 0.2:
                recent.append(points[index])
        wrists, setups = {}, {}
        for label in row["events"]:
            arrivals = [
                (
                    e["seconds"],
                    camera,
                    e["wrists"][label],
                    e.get("setups", {}).get(label),
                )
                for camera, stream in enumerate(evidence)
                for e in stream
                if label in e["wrists"]
                and now - 1 / GRID_FPS + 1e-9 < e["seconds"] <= now + 1e-9
            ]
            if arrivals:
                owner = min(arrivals, key=lambda x: x[:2])
                wrists[label] = owner[2]
                if owner[3] is not None:
                    setups[label] = owner[3]
        output.append(
            latch.update(
                row,
                np.zeros((33, 3)),
                wrists,
                release_views=recent,
                event_setups=setups,
            )
        )
    return output, dict(latch.audit)


def summarize(rows: list[dict]) -> dict:
    summary = {}
    keys = sorted({(r["profile"], r["reference_camera"]) for r in rows})
    for profile, camera in keys:
        selected = [
            r
            for r in rows
            if r["profile"] == profile
            and r["reference_camera"] == camera
            and r["metrics"]["trials"]
        ]
        hits, accepted, repeats, duplicates, unmatched, wrong, outside = (
            Counter() for _ in range(7)
        )
        coverage = defaultdict(list)
        for row in selected:
            for trial in row["metrics"]["trials"]:
                label = trial["label"]
                hits[label] += trial["detected"]
                accepted[label] += trial["accepted"]
                repeats[label] += trial["penalized_reappearances"]
                duplicates[label] += trial["extra_events"]
                coverage[label].append(trial["coverage"])
            unmatched.update(row["metrics"]["unmatched_events"])
            wrong.update(row["metrics"]["wrong_label_seconds"])
            outside.update(row["metrics"]["unlabelled_output_seconds"])
        summary[f"{profile}/reference{camera}"] = dict(
            detected=dict(hits),
            accepted=dict(accepted),
            event_reappearances=dict(repeats),
            extra_events=dict(duplicates),
            unmatched_events=dict(unmatched),
            mean_action_coverage={k: float(np.mean(v)) for k, v in coverage.items()},
            wrong_label_seconds=dict(wrong),
            unlabelled_output_seconds=dict(outside),
        )
    return summary


def main() -> None:
    temporal_path = ROOT / "shared/results/0928-multicam-temporal-results.json"
    baseline_path = ROOT / "shared/results/0928-multicam-results.json"
    followup_path = ROOT / "shared/results/0928-multicam-followup-results.json"
    temporal = json.loads(temporal_path.read_text())
    baseline = json.loads(baseline_path.read_text())
    followup = json.loads(followup_path.read_text())
    for name, expected in baseline["runtime_sha256"].items():
        if digest(ROOT / "src/gesture_detection" / name) != expected:
            raise ValueError("Baseline runtime changed")
    inputs = [
        r for r in baseline["rows"] if r["profile"] in ("rules_full", "rules_subject")
    ]
    inputs += [r for r in followup["rows"] if r["profile"] == "rules_camera_roi"]
    output_dir = ROOT / "shared/results/0928-multicam-events"
    output_dir.mkdir(parents=True, exist_ok=True)
    rows, streams, metadata, repeats = [], {}, {}, []
    pose_cache, evidence_cache, shared_controls = {}, {}, []
    for source in inputs:
        take, camera, profile = source["take"], source["camera"], source["profile"]
        reference = next(
            r for r in baseline["rows"] if r["take"] == take and r["camera"] == camera
        )
        fps = reference["effective_fps"]
        annotation_path = (
            ROOT / "shared/annotations" / take / f"camera_{camera:02}" / "timeline.json"
        )
        ann = (
            json.loads(annotation_path.read_text())
            if annotation_path.exists()
            else None
        )
        if ann and digest(annotation_path) != reference["annotation_sha256"]:
            raise ValueError("Annotation changed")
        intervals = ann["intervals"] if ann else []
        aspect = ann["source"]["width"] / ann["source"]["height"] if ann else 1280 / 720
        metadata[take, camera] = fps, intervals
        with np.load(ROOT / source["cache"]) as cache:
            points = cache["points"]
        pose_cache[take, camera, profile] = points, fps, aspect
        for variant in VARIANTS:
            predictions, audit = infer_events(points, fps, aspect, variant)
            if variant == "peak":
                previous = next(
                    r
                    for r in temporal["rows"]
                    if r["take"] == take
                    and r["camera"] == camera
                    and r["input"] == profile
                    and r["variant"] == "follow_peak"
                )
                if predictions != json.loads(
                    (ROOT / previous["predictions"]).read_text()
                ):
                    raise ValueError("Baseline replay mismatch")
            streams[take, camera, profile, variant] = predictions
            evidence_cache[take, camera, profile, variant] = audit["event_evidence"]
            path = output_dir / f"{take}-camera{camera}-{profile}-{variant}.json"
            path.write_text(json.dumps(predictions, indent=2) + "\n")
            metrics = apply_gesture_policy(temporal_score(intervals, predictions, fps))
            rows.append(
                dict(
                    take=take,
                    profile=f"{profile}/{variant}",
                    reference_camera=camera,
                    metrics=metrics,
                    audit=audit,
                    predictions=str(path.relative_to(ROOT)),
                )
            )
            # Counterfactual splice control: the entire original clip is repeated,
            # including its original preparation and return, with no detector reset.
            if any(t["detected"] and t["kind"] == "event" for t in metrics["trials"]):
                repeated, _ = infer_events(
                    np.concatenate([points, points]), fps, aspect, variant
                )
                n = len(points)
                doubled = intervals + [
                    dict(
                        x,
                        start_frame=x["start_frame"] + n,
                        end_frame=x["end_frame"] + n,
                    )
                    for x in intervals
                ]
                control = apply_gesture_policy(temporal_score(doubled, repeated, fps))
                repeats.append(
                    dict(
                        take=take,
                        camera=camera,
                        input=profile,
                        variant=variant,
                        metrics=control,
                    )
                )
        print(
            take,
            camera,
            profile,
            "parity verified; event candidates scored",
            flush=True,
        )
    fusion_rows = []
    combinations = {
        "full": ("rules_full", "rules_full"),
        "roi": ("rules_camera_roi", "rules_camera_roi"),
        "asymmetric": ("rules_subject", "rules_full"),
    }
    for take in sorted({r["take"] for r in rows}):
        session = json.loads(
            (ROOT / "shared/videos/0928" / take / "session.json").read_text()
        )
        for name, profiles in combinations.items():
            for variant in VARIANTS:
                selected = [streams[take, c, profiles[c - 1], variant] for c in (1, 2)]
                predictions, audit = fuse(selected, session["duration_seconds"])
                candidates = [(variant, predictions, audit)]
                if variant == "peak_anchor":
                    views = [pose_cache[take, c, profiles[c - 1]][:2] for c in (1, 2)]
                    evidence = [
                        evidence_cache[take, c, profiles[c - 1], variant]
                        for c in (1, 2)
                    ]
                    shared, shared_audit = shared_latch(predictions, views, evidence)
                    candidates.append(
                        (
                            "peak_anchor_shared_latch",
                            shared,
                            dict(audit, shared_latch=shared_audit),
                        )
                    )
                    fresh, fresh_audit = shared_latch(
                        predictions, views, evidence, require_new_setup=True
                    )
                    candidates.append(
                        (
                            "peak_anchor_fresh_setup",
                            fresh,
                            dict(audit, shared_latch=fresh_audit),
                        )
                    )
                    if any(
                        x["track"] == "action" and x["label"] in ("UCHIMIZU", "RAMUNE")
                        for x in metadata[take, 1][1]
                    ):
                        doubled_views, doubled_streams, doubled_evidence = [], [], []
                        for c in (1, 2):
                            p, fps, aspect = pose_cache[take, c, profiles[c - 1]]
                            p = np.concatenate([p, p])
                            replayed, detail = infer_events(p, fps, aspect, variant)
                            doubled_views.append((p, fps))
                            doubled_streams.append(replayed)
                            doubled_evidence.append(detail["event_evidence"])
                        twice, _ = fuse(
                            doubled_streams, 2 * session["duration_seconds"]
                        )
                        for fresh in (False, True):
                            gated, _ = shared_latch(
                                twice,
                                doubled_views,
                                doubled_evidence,
                                require_new_setup=fresh,
                            )
                            for c in (1, 2):
                                fps, intervals = metadata[take, c]
                                n = len(pose_cache[take, c, profiles[c - 1]][0])
                                doubled = intervals + [
                                    dict(
                                        x,
                                        start_frame=x["start_frame"] + n,
                                        end_frame=x["end_frame"] + n,
                                    )
                                    for x in intervals
                                ]
                                metrics = apply_gesture_policy(
                                    temporal_score(
                                        clock_intervals(doubled, fps), gated, GRID_FPS
                                    )
                                )
                                shared_controls.append(
                                    dict(
                                        take=take,
                                        combination=name,
                                        fresh_setup_required=fresh,
                                        reference_camera=c,
                                        metrics=metrics,
                                    )
                                )
                for candidate, result, detail in candidates:
                    path = output_dir / f"{take}-fusion-{name}-{candidate}.json"
                    path.write_text(json.dumps(result, indent=2) + "\n")
                    for camera in (1, 2):
                        fps, intervals = metadata[take, camera]
                        metrics = apply_gesture_policy(
                            temporal_score(
                                clock_intervals(intervals, fps), result, GRID_FPS
                            )
                        )
                        fusion_rows.append(
                            dict(
                                take=take,
                                profile=f"fusion_{name}/{candidate}",
                                reference_camera=camera,
                                metrics=metrics,
                                audit=detail,
                                predictions=str(path.relative_to(ROOT)),
                            )
                        )
    report = dict(
        phase_tolerance_seconds=1,
        state_reappearances_allowed=True,
        baseline_sha256=digest(baseline_path),
        temporal_sha256=digest(temporal_path),
        followup_sha256=digest(followup_path),
        script_sha256=digest(Path(__file__)),
        policy_sha256=digest(Path(__file__).with_name("multicam_event_policy.py")),
        rows=rows,
        fusion_rows=fusion_rows,
        summary=summarize(rows),
        fusion_summary=summarize(fusion_rows),
        repeated_clip_controls=repeats,
        shared_latch_controls=shared_controls,
        limitations=[
            "State acceptance means at least one output; inspect coverage and wrong labels separately.",
            "Repeated-clip controls are synthetic splices, not newly filmed consecutive actions.",
            "Asymmetric input is fixed by camera, not selected using each trial label.",
            "Same-footage exploratory result; missing capture timestamps remain approximated.",
        ],
    )
    (ROOT / "shared/results/0928-multicam-events-results.json").write_text(
        json.dumps(report, indent=2) + "\n"
    )
    for group in (report["summary"], report["fusion_summary"]):
        for name, values in group.items():
            if not name.endswith("reference2") or name.startswith("rules_full"):
                print(name, json.dumps(values))
    for control in repeats:
        print(
            "REPEAT",
            control["take"],
            control["camera"],
            control["input"],
            control["variant"],
            [
                (t["label"], t["accepted"], t["events_inside_action"])
                for t in control["metrics"]["trials"]
            ],
        )
    for control in shared_controls:
        if control["reference_camera"] == 1:
            print(
                "SHARED REPEAT",
                control["take"],
                control["combination"],
                control["fresh_setup_required"],
                [
                    (t["label"], t["accepted"], t["events_inside_action"])
                    for t in control["metrics"]["trials"]
                ],
            )


if __name__ == "__main__":
    main()
