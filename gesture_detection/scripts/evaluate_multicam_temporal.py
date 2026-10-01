"""Frozen-pose exploratory replay: moving Ramune setup and output continuity."""

from __future__ import annotations

import json
import math
from collections import Counter
from pathlib import Path

import numpy as np

from gesture_detection import config
from gesture_detection.ramune import RamuneAnalyzer
from gesture_detection.recognition import RecognitionCoordinator

from .evaluate_multicam import ROOT, digest
from .evaluate_multicam_followup import objects
from .multicam_temporal_metrics import temporal_score


class FollowingRamune(RamuneAnalyzer):
    """Experimental: re-anchor to a raised upper hand, optionally wait in setup.

    Existing visibility, base stability, press, contact and closing requirements
    remain in force. No annotation or future frame enters this detector.
    """

    def __init__(self, *, wait_in_setup: bool = False) -> None:
        self.wait_in_setup = wait_in_setup
        super().__init__()

    def update(self, landmarks, now: float) -> bool:
        if (
            self.state == "READY"
            and self.base_index is not None
            and self.last_time is not None
            and 0 < now - self.last_time <= config.RAMUNE_MAX_FRAME_GAP
            and len(landmarks) >= 25
            and all(
                p.visibility > 0.5 and math.isfinite(p.x) and math.isfinite(p.y)
                for p in [landmarks[j] for j in (11, 12, 15, 16, 23, 24)]
            )
        ):
            base = landmarks[self.base_index]
            upper = landmarks[31 - self.base_index]
            shoulder_y = (landmarks[11].y + landmarks[12].y) / 2
            hip_y = (landmarks[23].y + landmarks[24].y) / 2
            width = abs(landmarks[11].x - landmarks[12].x)
            gap = (base.y - upper.y) / self.scale
            stable = (
                abs(base.x - self.base[0]) / self.scale
                <= config.RAMUNE_BASE_X_TOLERANCE
                and abs(base.y - self.base[1]) / self.scale
                <= config.RAMUNE_BASE_TOLERANCE
            )
            ready = (
                width > 1e-6
                and stable
                and shoulder_y <= base.y <= hip_y
                and abs(base.x - upper.x) / width <= config.RAMUNE_ALIGN_TOLERANCE
                and config.RAMUNE_MIN_READY_GAP
                <= (base.y - upper.y) / width
                <= config.RAMUNE_MAX_READY_GAP
            )
            if ready:
                if upper.y < self.upper_y and gap > self.ready_gap:
                    self.upper_y, self.ready_gap = upper.y, gap
                    self.base = (base.x, base.y)
                    self.since = now
                press = (upper.y - self.upper_y) / self.scale
                closing = self.ready_gap - gap
                # The press timeout starts only after half the required press or
                # closing evidence, rather than expiring during a held setup.
                if (
                    self.wait_in_setup
                    and max(press, closing) < config.RAMUNE_MIN_PRESS / 2
                ):
                    self.since = now
        return super().update(landmarks, now)


class OutputEnvelope:
    """A causal short-loss hold ablation, not an action lock or ground-truth gate."""

    def __init__(
        self, *, enter_seconds: float = 0.2, hold_seconds: float = 0.5
    ) -> None:
        self.enter_seconds = enter_seconds
        self.hold_seconds = hold_seconds
        self.current = self.pending = "NONE"
        self.pending_since = 0.0
        self.last_evidence = -math.inf

    def update(self, gesture: str, now: float, events: list[str]) -> str:
        if gesture == self.current and gesture != "NONE":
            self.last_evidence = now
            self.pending = "NONE"
            return self.current
        if gesture != self.pending:
            self.pending = gesture
            self.pending_since = now
        accepted = gesture != "NONE" and (
            gesture in events or now - self.pending_since + 1e-9 >= self.enter_seconds
        )
        if accepted:
            self.current = gesture
            self.last_evidence = now
            self.pending = "NONE"
        elif now - self.last_evidence > self.hold_seconds + 1e-9:
            self.current = "NONE"
        return self.current


def infer(points: np.ndarray, fps: float, aspect: float, variant: str) -> list[dict]:
    coordinator = RecognitionCoordinator(ramune_detector="rules", source_fps=fps)
    if variant != "baseline":
        coordinator.ramune = FollowingRamune(wait_in_setup=variant == "follow_wait")
    predictions = []
    for i, point in enumerate(points):
        result = coordinator.process(objects(point), i / fps, i, aspect_ratio=aspect)
        predictions.append(
            dict(
                frame=i,
                seconds=i / fps,
                gesture=result["current"]["gesture"],
                events=list(result["occurrences"]),
                ramune_state=result["ramune_state"],
            )
        )
    return predictions


def envelope(predictions: list[dict]) -> list[dict]:
    gate = OutputEnvelope()
    return [
        dict(p, gesture=gate.update(p["gesture"], p["seconds"], p["events"]))
        for p in predictions
    ]


def aggregate(rows: list[dict]) -> dict:
    summary = {}
    for key in sorted({(r["input"], r["variant"], r["camera"]) for r in rows}):
        chosen = [
            r
            for r in rows
            if (r["input"], r["variant"], r["camera"]) == key and r["metrics"]["trials"]
        ]
        counts, repeats, events, wrong, outside = (Counter() for _ in range(5))
        tails = []
        for row in chosen:
            for t in row["metrics"]["trials"]:
                counts[t["label"]] += t["detected"]
                repeats[t["label"]] += t["reappearances"]
                tails.append(t["tail_overrun_seconds"])
            events.update(row["metrics"]["unmatched_events"])
            wrong.update(row["metrics"]["wrong_label_seconds"])
            outside.update(row["metrics"]["unlabelled_output_seconds"])
        summary[f"{key[0]}/{key[1]}/camera{key[2]}"] = dict(
            detections=dict(counts),
            reappearances=dict(repeats),
            unmatched_events=dict(events),
            wrong_label_seconds=dict(wrong),
            unlabelled_output_seconds=dict(outside),
            max_tail_seconds=max(tails, default=0),
        )
    return summary


def main() -> None:
    baseline_path = ROOT / "shared/results/0928-multicam-results.json"
    followup_path = ROOT / "shared/results/0928-multicam-followup-results.json"
    baseline = json.loads(baseline_path.read_text())
    followup = json.loads(followup_path.read_text())
    for name, expected in baseline["runtime_sha256"].items():
        if digest(ROOT / "src/gesture_detection" / name) != expected:
            raise ValueError("Baseline runtime changed")
    inputs = [
        r for r in baseline["rows"] if r["profile"] in ("rules_full", "rules_subject")
    ]
    inputs += [
        dict(
            r,
            effective_fps=next(
                b["effective_fps"]
                for b in baseline["rows"]
                if b["take"] == r["take"] and b["camera"] == r["camera"]
            ),
        )
        for r in followup["rows"]
        if r["profile"] == "rules_camera_roi"
    ]
    output = ROOT / "shared/results/0928-multicam-temporal"
    output.mkdir(parents=True, exist_ok=True)
    rows = []
    for source in inputs:
        take, camera, profile = source["take"], source["camera"], source["profile"]
        ann_path = (
            ROOT / "shared/annotations" / take / f"camera_{camera:02}" / "timeline.json"
        )
        ann = json.loads(ann_path.read_text()) if ann_path.exists() else None
        reference = next(
            r for r in baseline["rows"] if r["take"] == take and r["camera"] == camera
        )
        if ann and digest(ann_path) != reference["annotation_sha256"]:
            raise ValueError("Annotation changed since baseline")
        intervals = ann["intervals"] if ann else []
        fps = source["effective_fps"]
        aspect = ann["source"]["width"] / ann["source"]["height"] if ann else 1280 / 720
        with np.load(ROOT / source["cache"]) as cache:
            points = cache["points"]
        for variant in ("baseline", "follow_peak", "follow_wait"):
            raw = infer(points, fps, aspect, variant)
            if variant == "baseline":
                expected = (
                    json.loads((ROOT / source["predictions"]).read_text())
                    if "predictions" in source
                    else json.loads((ROOT / source["diagnostics"]).read_text())[
                        "predictions"
                    ]
                )
                if raw != expected:
                    raise ValueError("Baseline parity failure")
            for suffix, predictions in (("", raw), ("_envelope", envelope(raw))):
                name = variant + suffix
                path = output / f"{take}-camera{camera}-{profile}-{name}.json"
                path.write_text(json.dumps(predictions, indent=2) + "\n")
                rows.append(
                    dict(
                        take=take,
                        camera=camera,
                        input=profile,
                        variant=name,
                        metrics=temporal_score(intervals, predictions, fps),
                        predictions=str(path.relative_to(ROOT)),
                    )
                )
        print(
            take,
            camera,
            profile,
            "verified baseline and evaluated candidates",
            flush=True,
        )
    report = dict(
        baseline_sha256=digest(baseline_path),
        followup_sha256=digest(followup_path),
        script_sha256=digest(Path(__file__)),
        metric_sha256=digest(Path(__file__).with_name("multicam_temporal_metrics.py")),
        phase_tolerance_seconds=1,
        envelope=dict(enter_seconds=0.2, hold_seconds=0.5),
        rows=rows,
        summary=aggregate(rows),
        limitations=[
            "Same-footage exploratory analysis; no independent validation.",
            "Phase tolerance affects scoring only, not model thresholds or smoothing.",
            "Short-loss envelope may still reappear after longer loss; measure rather than guarantee continuity.",
            "Action spans include preparation; coverage does not require output from preparation onset.",
            "Output events are not suppressed by the envelope; duplicate events remain visible in metrics.",
        ],
    )
    (ROOT / "shared/results/0928-multicam-temporal-results.json").write_text(
        json.dumps(report, indent=2) + "\n"
    )
    print(json.dumps(report["summary"], indent=2))


if __name__ == "__main__":
    main()
