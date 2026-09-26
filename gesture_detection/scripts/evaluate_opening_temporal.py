"""Causal OPENED hold and rearming experiments with take-grouped validation."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

from .evaluate_timeline import (
    ROOT,
    choose,
    digest,
    extract,
    features,
    fit_predict,
    opening_diagnostics,
    positive_runs,
    runtime_settings,
)


@dataclass(frozen=True)
class TemporalConfig:
    hold_seconds: float = 0.0
    release_seconds: float = 0.0
    setup_seconds: float = 0.0
    release_mode: str = "none"
    require_initial_setup: bool = False


def release_evidence(points: np.ndarray, action: np.ndarray, mode: str) -> np.ndarray:
    """Observed release, never a missing-pose timeout or a ground-truth boundary."""
    tracked = (points[:, :, 2] > 0.5).any(axis=1)
    evidence = tracked & (action != 1)
    if mode == "hands":
        visible = (points[:, [11, 12, 15, 16], 2] > 0.5).all(axis=1)
        shoulders = np.abs(points[:, 11, 0] - points[:, 12, 0])
        separated = np.abs(points[:, 15, 0] - points[:, 16, 0]) > 0.8 * shoulders
        evidence &= visible & (shoulders > 1e-6) & separated
    return evidence


def apply_temporal(
    phase: np.ndarray,
    action: np.ndarray,
    points: np.ndarray,
    fps: float,
    config: TemporalConfig,
    *,
    initial_setup_phase_only: bool = False,
    rearm_setup_phase_only: bool = False,
    trace: list[dict] | None = None,
) -> tuple[np.ndarray, list[int]]:
    """Forward-only display and pulses; optional offline setup ablations and audit.

    The default gates preserve the original experiment. Phase-only setup never
    changes release evidence, tracking requirements, or the setup dwell time.
    """
    if not np.isfinite(fps) or fps <= 0:
        raise ValueError("FPS must be positive and finite")
    if len(phase) != len(action) or len(phase) != len(points):
        raise ValueError("Input lengths must agree")
    if config.release_mode not in {"none", "context", "hands"}:
        raise ValueError("Unknown release mode")
    if any(
        not np.isfinite(v) or v < 0
        for v in (config.hold_seconds, config.release_seconds, config.setup_seconds)
    ):
        raise ValueError("Durations must be finite and non-negative")
    release = release_evidence(points, action, config.release_mode)
    tracked = (points[:, :, 2] > 0.5).any(axis=1)
    output = np.zeros(len(phase), dtype=int)
    events = []
    state = "WAIT_SETUP" if config.require_initial_setup else "ARMED"
    last_open = -np.inf
    release_since = setup_since = None
    for index, predicted in enumerate(phase):
        now = index / fps
        before = state
        initial = not events
        phase_only = initial_setup_phase_only if initial else rearm_setup_phase_only
        ready = bool(
            tracked[index] and predicted in (1, 2) and (phase_only or action[index] == 1)
        )
        if state == "ARMED" and predicted == 3:
            state = "OPENED"
            last_open = now
            events.append(index)
        if state == "OPENED":
            if predicted == 3:
                last_open = now
            if predicted == 3 or now - last_open <= config.hold_seconds + 1e-9:
                output[index] = 3
            else:
                state = "ARMED" if config.release_mode == "none" else "LOCKED"
                release_since = setup_since = None
        if output[index] != 3 and state == "LOCKED":
            if release[index]:
                release_since = now if release_since is None else release_since
                if now - release_since + 1e-9 >= config.release_seconds:
                    state = "WAIT_SETUP"
            else:
                release_since = None
        elif output[index] != 3 and state == "WAIT_SETUP":
            if ready:
                setup_since = now if setup_since is None else setup_since
                if now - setup_since + 1e-9 >= config.setup_seconds:
                    state = "ARMED"
            else:
                setup_since = None
        if trace is not None:
            trace.append(
                dict(
                    frame=index,
                    state_before=before,
                    state_after=state,
                    initial_setup=initial,
                    setup_evidence=ready,
                    release_evidence=bool(release[index]),
                    setup_elapsed_seconds=(now - setup_since)
                    if setup_since is not None and before == "WAIT_SETUP" and ready
                    else 0.0,
                    blocked_opened=bool(predicted == 3 and output[index] != 3),
                )
            )
    return output, events


def candidates(family: str) -> list[TemporalConfig]:
    holds = (0.1, 0.25, 0.5, 0.75)
    if family == "hold":
        return [TemporalConfig(hold_seconds=h) for h in holds]
    if family == "lock":
        return [
            TemporalConfig(h, release, 0.15, mode)
            for h in holds
            for release in (0.3, 0.6)
            for mode in ("context", "hands")
        ]
    raise ValueError(family)


def measure(clip: dict, output: np.ndarray, events: list[int]) -> dict:
    result = opening_diagnostics(clip, output)
    result["notifications"] = len(events)
    result["notification_frames"] = events
    result["active_seconds"] = float((output == 3).sum() / clip["fps"])
    # Descriptive audit only: a continuous matched extension is allowed by spec.
    result["outside_action_seconds"] = float(
        ((output == 3) & (clip["action"] != 1)).sum() / clip["fps"]
    )
    result["longest_run_seconds"] = max(
        ((b - a + 1) / clip["fps"] for a, b in positive_runs(output == 3)), default=0.0
    )
    return result


def aggregate(rows: list[dict]) -> dict:
    fields = (
        "intervals",
        "intervals_hit",
        "predicted_runs",
        "reappearance_runs",
        "openings_with_reappearance",
        "occurrence_restarts",
        "occurrences_with_multiple_runs",
        "notifications",
        "active_seconds",
        "outside_action_seconds",
    )
    total = {key: sum(row[key] for row in rows) for key in fields}
    total["unanchored_runs"] = sum(len(row["unanchored_runs"]) for row in rows)
    hits, anchors, runs = (total[k] for k in ("intervals_hit", "intervals", "predicted_runs"))
    total["run_precision"] = hits / runs if runs else 0.0
    total["anchor_recall"] = hits / anchors if anchors else 0.0
    total["run_f1"] = 2 * hits / (anchors + runs) if anchors + runs else 0.0
    return total


def tune(
    validation: list[tuple[dict, np.ndarray, np.ndarray]],
    family: str,
    options: list[TemporalConfig] | None = None,
) -> tuple[TemporalConfig, list[dict]]:
    trials = []
    for config in candidates(family) if options is None else options:
        rows = []
        for clip, phase, action in validation:
            output, events = apply_temporal(phase, action, clip["points"], clip["fps"], config)
            rows.append(measure(clip, output, events))
        trials.append(dict(config=asdict(config), metrics=aggregate(rows)))
    # Equal run F1: prefer more anchors, fewer outputs outside action and shorter hold.
    selected = max(
        trials,
        key=lambda r: (
            r["metrics"]["run_f1"],
            r["metrics"]["intervals_hit"],
            -r["metrics"]["outside_action_seconds"],
            -r["config"]["hold_seconds"],
        ),
    )
    return TemporalConfig(**selected["config"]), trials


def run(clips: list[dict]) -> tuple[dict, dict]:
    rows = {
        family: []
        for family in ("raw", "hold", "lock", "context_lock", "hands_lock", "prepared_hands")
    }
    selections, saved_predictions = [], {}
    for group in (1, 2, 3, 0):
        train = [c for c in clips if c["group"] not in (0, group)]
        test = [c for c in clips if c["group"] == group]
        print(f"Outer group {group}: train {len(train)}, test {len(test)}", flush=True)
        params = {target: choose(train, target) for target in ("phase", "action")}
        outer_predictions = {
            target: fit_predict(train, test, target, *params[target]) for target in params
        }
        validation = []
        for inner in sorted({c["group"] for c in train}):
            inner_train = [c for c in train if c["group"] != inner]
            inner_test = [c for c in train if c["group"] == inner]
            predicted = {
                target: fit_predict(inner_train, inner_test, target, *params[target])
                for target in params
            }
            validation.extend(zip(inner_test, predicted["phase"], predicted["action"], strict=True))
        configs = {"raw": TemporalConfig()}
        for family in ("hold", "lock", "context_lock", "hands_lock", "prepared_hands"):
            options = None
            if family in {"context_lock", "hands_lock", "prepared_hands"}:
                mode = "context" if family == "context_lock" else "hands"
                options = [
                    TemporalConfig(
                        configs["hold"].hold_seconds,
                        release,
                        0.15,
                        mode,
                        family == "prepared_hands",
                    )
                    for release in (0.3, 0.6)
                ]
            selected, trials = tune(validation, family, options)
            configs[family] = selected
            selections.append(
                dict(
                    outer_group=group,
                    family=family,
                    classifier_parameters=params,
                    selected=asdict(selected),
                    trials=trials,
                    train_videos=[c["name"] for c in train],
                    test_videos=[c["name"] for c in test],
                )
            )
        for clip, phase, action in zip(
            test, outer_predictions["phase"], outer_predictions["action"], strict=True
        ):
            for family, config in configs.items():
                output, events = apply_temporal(phase, action, clip["points"], clip["fps"], config)
                rows[family].append(
                    dict(
                        video=clip["name"],
                        group=group,
                        config=asdict(config),
                        metrics=measure(clip, output, events),
                    )
                )
                saved_predictions[family + "/" + clip["name"]] = output
    report = dict(selections=selections, families={})
    for family, items in rows.items():
        report["families"][family] = dict(
            clips=items,
            behind=aggregate([r["metrics"] for r in items if r["group"]]),
            without=aggregate([r["metrics"] for r in items if not r["group"]]),
        )
    return report, saved_predictions


def plot_predictions(clips: list[dict], predictions: dict, path: Path) -> None:
    """Export timelines, using the same frame grid as annotation and evaluation."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    examples = [
        ("both1_behind_the_screen", 240, 390),
        ("ramune3_behind_the_screen", 140, 315),
        ("both_without_the_screen", 250, 335),
        ("ramune2_behind_the_screen", 125, 190),
    ]
    fig, axes = plt.subplots(len(examples), 1, figsize=(12, 9), layout="constrained")
    for ax, (name, left, right) in zip(axes, examples, strict=True):
        clip = next(c for c in clips if c["name"] == name)
        ax.broken_barh(
            [(a, b - a + 1) for a, b in clip["opening_intervals"]],
            (3 - 0.25, 0.5),
            facecolors="#cc4444",
        )
        for y, family, color in [
            (2, "raw", "#888888"),
            (1, "hold", "#d29922"),
            (0, "prepared_hands", "#238636"),
        ]:
            runs = positive_runs(predictions[family + "/" + name] == 3)
            ax.broken_barh([(a, b - a + 1) for a, b in runs], (y - 0.25, 0.5), facecolors=color)
        ax.set_yticks(
            [0, 1, 2, 3], ["Hold + release/setup", "Hold only", "Raw", "Annotation anchor"]
        )
        ax.set_xlim(left, right)
        ax.set_ylim(-0.6, 3.6)
        ax.set_title(name, loc="left", fontsize=10)
        ax.set_xlabel("Source frame (zero-based)")
        ax.grid(axis="x", alpha=0.25)
    fig.suptitle("OPENED continuity: held-video predictions", fontsize=14)
    fig.savefig(path, dpi=160)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, default=ROOT / "docs/0924-opening-temporal-results.json"
    )
    parser.add_argument("--plot", action="store_true")
    args = parser.parse_args()
    cache = ROOT / "shared/results/0924-cache"
    clips = []
    for path in sorted((ROOT / "shared/annotations/0924").glob("*/timeline.json")):
        clip = extract(path, cache, select_subject=False, central_mask=True)
        clip["features"] = {h: features(clip, h) for h in (0.25, 0.75)}
        clips.append(clip)
    if {c["group"] for c in clips} != {0, 1, 2, 3}:
        raise ValueError("Expected take groups 1/2/3 and without-screen group 0")
    report, predictions = run(clips)
    report["protocol"] = (
        "Central mask; outer take 1/2/3; without-screen excluded from training; "
        "base classifier selection on outer-training groups only; temporal selection on "
        "inner held-video predictions; no annotations in temporal inference; "
        "run F1 = 2*matched anchors/(anchors + output runs); labels unchanged"
    )
    report["runtime"] = runtime_settings()
    report["sources"] = [
        {k: c[k] for k in ("name", "annotation_sha256", "video_sha256")} for c in clips
    ]
    report["script_sha256"] = digest(Path(__file__))
    report["classifier_script_sha256"] = digest(Path(__file__).with_name("evaluate_timeline.py"))
    prediction_path = cache / (args.output.stem + "-predictions.npz")
    np.savez_compressed(prediction_path, **predictions)
    report["frame_predictions"] = str(prediction_path.relative_to(ROOT))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.plot:
        plot_path = args.output.with_suffix(".png")
        plot_predictions(clips, predictions, plot_path)
        report["plot"] = str(plot_path)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(args.output, flush=True)


if __name__ == "__main__":
    main()
