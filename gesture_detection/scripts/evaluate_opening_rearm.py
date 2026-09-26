"""Take-grouped rearm tuning with synthetic repeat-signal validation.

Repeated signals are a state-machine stress test, not independent new videos.
Only temporal state spans each join; source pose/classifier state does not.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

import numpy as np

from .evaluate_opening_repetition import repeat_clip, summarize
from .evaluate_opening_temporal import TemporalConfig, aggregate, apply_temporal, measure
from .evaluate_timeline import ROOT, digest, extract, features, fit_predict


def score_config(samples: list[tuple[dict, np.ndarray, np.ndarray]], cfg: TemporalConfig) -> dict:
    single, repeated = [], []
    for clip, phase, action in samples:
        out, events = apply_temporal(phase, action, clip["points"], clip["fps"], cfg)
        single.append(measure(clip, out, events))
        pair, p, a, _ = repeat_clip(clip, phase, action)
        out, events = apply_temporal(p, a, pair["points"], clip["fps"], cfg)
        repeated.append(measure(pair, out, events))
    s, r = aggregate(single), aggregate(repeated)
    return dict(single=s, repeated=r, score=(s["run_f1"] + r["run_f1"]) / 2)


def tune_rearm(
    samples: list[tuple[dict, np.ndarray, np.ndarray]], hold: float
) -> tuple[TemporalConfig, list[dict]]:
    trials = []
    for mode in ("context", "hands"):
        for release in (0.3, 0.6, 1.0):
            for setup in (0.15, 0.3, 0.5):
                cfg = TemporalConfig(hold, release, setup, mode, True)
                trials.append(dict(config=asdict(cfg), metrics=score_config(samples, cfg)))
    selected = max(
        trials,
        key=lambda t: (
            t["metrics"]["score"],
            t["metrics"]["single"]["intervals_hit"],
            -t["metrics"]["single"]["unanchored_runs"],
            -t["config"]["setup_seconds"],
            -t["config"]["release_seconds"],
        ),
    )
    return TemporalConfig(**selected["config"]), trials


def evaluate_sample(clip: dict, phase: np.ndarray, action: np.ndarray, cfg: TemporalConfig) -> dict:
    out, events = apply_temporal(phase, action, clip["points"], clip["fps"], cfg)
    single = measure(clip, out, events)
    repetitions = []
    for missing in (0.0, 0.5, 2.0):
        pair, p, a, offset = repeat_clip(clip, phase, action, missing)
        repeated, events = apply_temporal(p, a, pair["points"], clip["fps"], cfg)
        np.testing.assert_array_equal(out, repeated[: len(out)])
        m = measure(pair, repeated, events)
        count = len(clip["opening_intervals"])
        first = any(d["matched_run"] is not None for d in m["details"][:count])
        second = any(d["matched_run"] is not None for d in m["details"][count:])
        repetitions.append(
            dict(
                missing_seconds=missing,
                join_frame=offset,
                anchors_per_copy=count,
                first_hit=first,
                second_hit=second,
                diagnostics=m,
            )
        )
    return dict(
        video=clip["name"],
        group=clip["group"],
        config=asdict(cfg),
        single=single,
        repetitions=repetitions,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, default=ROOT / "docs/0924-opening-rearm-results.json"
    )
    args = parser.parse_args()
    previous_path = ROOT / "docs/0924-opening-temporal-results.json"
    previous = json.loads(previous_path.read_text())
    phase_report_path = ROOT / "docs/0924-timeline-central-results.json"
    phase_report = json.loads(phase_report_path.read_text())
    source_hashes = {s["name"]: s["annotation_sha256"] for s in phase_report["sources"]}
    clips = []
    for path in sorted((ROOT / "shared/annotations/0924").glob("*/timeline.json")):
        if digest(path) != source_hashes[path.parent.name]:
            raise ValueError("Annotation changed since source predictions")
        c = extract(
            path, ROOT / "shared/results/0924-cache", select_subject=False, central_mask=True
        )
        c["features"] = {h: features(c, h) for h in (0.25, 0.75)}
        clips.append(c)
    families = {key: [] for key in ("previous", "context_fixed", "retuned")}
    selections = []
    with np.load(ROOT / phase_report["frame_predictions"]) as outer:
        for group in (1, 2, 3, 0):
            print("Outer group", group, flush=True)
            train = [c for c in clips if c["group"] not in (0, group)]
            test = [c for c in clips if c["group"] == group]
            reference = next(
                s
                for s in previous["selections"]
                if s["outer_group"] == group and s["family"] == "prepared_hands"
            )
            assert {c["name"] for c in train} == set(reference["train_videos"])
            params = reference["classifier_parameters"]
            samples = []
            for inner in sorted({c["group"] for c in train}):
                itrain = [c for c in train if c["group"] != inner]
                itest = [c for c in train if c["group"] == inner]
                predicted = {
                    t: fit_predict(itrain, itest, t, *params[t]) for t in ("phase", "action")
                }
                samples.extend(zip(itest, predicted["phase"], predicted["action"], strict=True))
            old_cfg = TemporalConfig(**reference["selected"])
            selected, trials = tune_rearm(samples, old_cfg.hold_seconds)
            selections.append(
                dict(
                    group=group,
                    selected=asdict(selected),
                    trials=trials,
                    train_videos=[c["name"] for c in train],
                    test_videos=[c["name"] for c in test],
                )
            )
            configs = dict(
                previous=old_cfg,
                context_fixed=TemporalConfig(old_cfg.hold_seconds, 0.6, 0.3, "context", True),
                retuned=selected,
            )
            for c in test:
                for family, cfg in configs.items():
                    families[family].append(
                        evaluate_sample(
                            c, outer["phase/" + c["name"]], outer["action/" + c["name"]], cfg
                        )
                    )
    results = {}
    for family, rows in families.items():
        summary = {}
        for env in ("behind", "without"):
            relevant = [r for r in rows if bool(r["group"]) == (env == "behind")]
            summary[env] = dict(single=aggregate([r["single"] for r in relevant]), repetition={})
            for missing in (0.0, 0.5, 2.0):
                summary[env]["repetition"][str(missing)] = summarize(
                    [
                        m
                        for r in relevant
                        for m in r["repetitions"]
                        if m["missing_seconds"] == missing
                    ]
                )
        results[family] = dict(clips=rows, **summary)
    report = dict(
        protocol=__doc__,
        families=results,
        selections=selections,
        objective="Mean of single-sequence and two-copy run F1 on outer-training inner predictions; hold fixed to prior outer-training choice",
        previous_report_sha256=digest(previous_path),
        classifier_report_sha256=digest(phase_report_path),
        sources=phase_report["sources"],
        script_sha256=digest(Path(__file__)),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    for family, data in results.items():
        print(family, {env: data[env] for env in ("behind", "without")}, flush=True)


if __name__ == "__main__":
    main()
