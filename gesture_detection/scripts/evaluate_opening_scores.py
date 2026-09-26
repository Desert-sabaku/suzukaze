"""Score audit of the frozen relative-position experiment, without retuning.

Ridge scores are not probabilities. Statistics exclude missing poses and
untrained classes. Scores from different fitted folds are not pooled.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from .evaluate_opening_features import feature_sets, relative_geometry
from .evaluate_opening_setup import CONFIG, STATES, evaluate_sample, summarize_family
from .evaluate_timeline import (
    PHASES,
    ROOT,
    digest,
    extract,
    fit_scores,
    positive_runs,
    predict_from_scores,
)

OPENED = PHASES.index("OPENED")


def score_diagnostics(scores: np.ndarray, observed: np.ndarray) -> dict[str, np.ndarray]:
    """NaN denotes unavailable evidence; rank ties follow prediction argmax."""
    opened = scores[:, OPENED]
    result = {}
    competitors = {
        "opened_minus_ready": scores[:, PHASES.index("READY")],
        "opened_minus_wait_release": scores[:, PHASES.index("WAIT_RELEASE")],
        "opened_minus_best_other": np.max(np.delete(scores, OPENED, axis=1), axis=1),
    }
    available = observed & np.isfinite(opened)
    result["opened_score"] = np.where(available, opened, np.nan)
    for key, other in competitors.items():
        valid = available & np.isfinite(other)
        values = np.full(len(scores), np.nan)
        values[valid] = opened[valid] - other[valid]
        result[key] = values
    earlier = np.arange(scores.shape[1]) < OPENED
    ahead = (scores > opened[:, None]) | ((scores == opened[:, None]) & earlier)
    result["opened_rank"] = np.where(available, 1 + ahead.sum(axis=1), np.nan)
    return result


def distribution(values: np.ndarray) -> dict:
    valid = values[np.isfinite(values)]
    if not len(valid):
        return dict(count=0, min=None, q25=None, median=None, q75=None, max=None)
    quantiles = np.quantile(valid, [0, 0.25, 0.5, 0.75, 1])
    return dict(
        count=len(valid),
        **dict(zip(("min", "q25", "median", "q75", "max"), map(float, quantiles), strict=True)),
    )


def summarize_window(
    mask: np.ndarray,
    observed: np.ndarray,
    scores: dict,
    phase: np.ndarray,
    output: np.ndarray,
    trace: list[dict],
) -> dict:
    eligible = mask & observed
    ranks = scores["opened_rank"][eligible]
    raw_opened = eligible & (phase == OPENED)
    blocked = raw_opened & (output != OPENED)
    result = dict(
        frames=int(mask.sum()),
        observed_frames=int(eligible.sum()),
        missing_pose_frames=int((mask & ~observed).sum()),
        distributions={key: distribution(value[eligible]) for key, value in scores.items()},
        rank_counts={str(rank): int((ranks == rank).sum()) for rank in range(1, len(PHASES) + 1)},
        raw_opened_frames=int(raw_opened.sum()),
        blocked_opened_frames=int(blocked.sum()),
        blocked_by_state={
            state: sum(
                bool(blocked[i]) and row["state_before"] == state for i, row in enumerate(trace)
            )
            for state in STATES
        },
    )
    return result


def phase_runs(phase: np.ndarray) -> list[dict]:
    return sorted(
        [
            dict(frames=[a, b], phase=label)
            for index, label in enumerate(PHASES)
            for a, b in positive_runs(phase == index)
        ],
        key=lambda row: row["frames"][0],
    )


def audit_clip(clip: dict, raw_scores: np.ndarray, action: np.ndarray) -> tuple[dict, dict, dict]:
    phase = predict_from_scores(raw_scores, clip["points"])
    observed = (clip["points"][:, :, 2] > 0.5).any(axis=1)
    row, output, trace = evaluate_sample(clip, phase, action, "baseline")
    diagnostics = score_diagnostics(raw_scores, observed)
    anchor_mask = np.zeros(len(phase), dtype=bool)
    for a, b in clip["opening_intervals"]:
        anchor_mask[a : b + 1] = True
    masks = {
        "whole_video": np.ones(len(phase), dtype=bool),
        "opening_anchors": anchor_mask,
        "outside_anchors_descriptive_only": ~anchor_mask,
        "annotated_ready": clip["phase"] == PHASES.index("READY"),
        "annotated_wait_release": clip["phase"] == PHASES.index("WAIT_RELEASE"),
        "annotated_action_none": clip["action"] == 0,
        "unknown_phase": clip["phase"] < 0,
    }
    summaries = {
        key: summarize_window(mask, observed, diagnostics, phase, output, trace)
        for key, mask in masks.items()
    }
    intervals = []
    for index, (start, end) in enumerate(clip["opening_intervals"]):
        parent = next((a, b) for a, b in clip["ramune_intervals"] if a <= start <= end <= b)
        padding = round(clip["fps"])
        windows = {
            "anchor": (start, end),
            "before_1s": (max(0, start - padding), start - 1),
            "after_1s": (end + 1, min(len(phase) - 1, end + padding)),
            "ramune_trial": parent,
        }
        stats = {}
        for key, (a, b) in windows.items():
            mask = np.zeros(len(phase), dtype=bool)
            mask[a : b + 1] = True
            stats[key] = dict(
                window_frames=[a, b],
                **summarize_window(mask, observed, diagnostics, phase, output, trace),
            )
        _, valid = relative_geometry(clip)
        intervals.append(
            dict(
                anchor_frames=[start, end],
                hit=row["single"]["details"][index]["matched_run"] is not None,
                matched_run=row["single"]["details"][index]["matched_run"],
                windows=stats,
                anchor_phases=[PHASES[int(p)] for p in phase[start : end + 1]],
                state_at_anchor=trace[start]["state_before"],
                valid_wrist_distance_frames=int(valid[start : end + 1, 0].sum()),
                valid_left_wrist_frames=int(valid[start : end + 1, 3].sum()),
                valid_right_wrist_frames=int(valid[start : end + 1, 5].sum()),
            )
        )
    # Descriptive high-ranking outside-anchor frames, not automatically errors:
    # accepted continuous extensions may cover such frames.
    margin = diagnostics["opened_minus_best_other"]
    candidates = np.flatnonzero(~anchor_mask & np.isfinite(margin))
    top = sorted(candidates, key=lambda i: (-margin[i], int(i)))[:10]
    audit = dict(
        video=clip["name"],
        group=clip["group"],
        fps=clip["fps"],
        summaries=summaries,
        intervals=intervals,
        phase_runs=phase_runs(phase),
        state_transitions=[t for t in trace if t["state_before"] != t["state_after"]],
        top_outside_anchor_frames=[
            dict(
                frame=int(i),
                seconds=float(i / clip["fps"]),
                opened_margin=float(margin[i]),
                opened_rank=int(diagnostics["opened_rank"][i]),
                annotated_action=int(clip["action"][i]),
                annotated_phase=int(clip["phase"][i]),
                state=trace[i]["state_before"],
                output=int(output[i]),
            )
            for i in top
        ],
    )
    arrays = dict(
        scores=raw_scores,
        observed=observed,
        phase=phase,
        output=output,
        action=action,
        state=np.array([STATES.index(t["state_after"]) for t in trace], dtype=np.int8),
        **diagnostics,
    )
    return audit, row, arrays


def plot_clip(clip: dict, arrays: dict, path: Path, window: tuple[int, int] | None = None) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    t = np.arange(len(clip["phase"])) / clip["fps"]
    fig, axes = plt.subplots(5, 1, figsize=(14, 11), sharex=True, layout="constrained")
    fig.suptitle(clip["name"] + " | relative-position ridge scores (not probabilities)")
    for ax in axes:
        for a, b in clip["opening_intervals"]:
            ax.axvspan(a / clip["fps"], (b + 1) / clip["fps"], color="gold", alpha=0.3)
        ax.grid(alpha=0.2)
    for index, label in enumerate(PHASES):
        scores = arrays["scores"][:, index]
        axes[0].plot(
            t, np.where(arrays["observed"] & np.isfinite(scores), scores, np.nan), label=label
        )
    axes[0].legend(loc="upper right", ncol=5)
    axes[0].set(ylabel="Ridge score")
    for key in ("opened_minus_ready", "opened_minus_wait_release", "opened_minus_best_other"):
        axes[1].plot(t, arrays[key], label=key.replace("opened_minus_", "OPENED - "))
    axes[1].axhline(0, color="black", linewidth=0.8)
    axes[1].legend(loc="upper right", ncol=3)
    axes[1].set(ylabel="Score difference")
    axes[2].step(t, arrays["opened_rank"], where="post", label="OPENED rank")
    axes[2].set(yticks=range(1, 6), ylim=(5.3, 0.7), ylabel="Rank (1 = winner)")
    axes[3].step(t, clip["phase"], where="post", label="annotation", linewidth=2)
    axes[3].step(t, arrays["phase"], where="post", label="prediction")
    axes[3].set(yticks=range(-1, 5), yticklabels=["UNKNOWN", *PHASES], ylabel="Phase")
    axes[3].legend(loc="upper right", ncol=2)
    axes[4].step(t, arrays["state"], where="post")
    axes[4].set(
        yticks=range(4),
        yticklabels=STATES,
        ylabel="Temporal state",
        xlabel="Time (s); gold = OPENED annotation; missing poses excluded from scores",
    )
    if window is not None:
        axes[4].set_xlim(window[0] / clip["fps"], (window[1] + 1) / clip["fps"])
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=130)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, default=ROOT / "docs/0924-opening-scores-results.json"
    )
    parser.add_argument("--plot", action="store_true")
    args = parser.parse_args()
    reference_path = ROOT / "docs/0924-opening-features-results.json"
    reference = json.loads(reference_path.read_text())
    frozen_path = ROOT / reference["frame_predictions"]
    if digest(frozen_path) != reference["frame_predictions_sha256"]:
        raise ValueError("Reference predictions changed")
    sources = {s["name"]: s for s in reference["sources"]}
    paths = sorted((ROOT / "shared/annotations/0924").glob("*/timeline.json"))
    if {p.parent.name for p in paths} != set(sources):
        raise ValueError("Source set changed")
    clips = []
    for path in paths:
        if digest(path) != sources[path.parent.name]["annotation_sha256"]:
            raise ValueError("Annotation changed")
        clip = extract(
            path,
            ROOT / "shared/results/0924-cache",
            select_subject=False,
            central_mask=True,
            cache_only=True,
        )
        clip["features"] = feature_sets(clip)["relative_position"]
        clips.append(clip)
    audits, rows, saved, plots = [], [], {}, []
    with np.load(frozen_path) as frozen:
        for selection in reference["selections"]["relative_position"]:
            group = selection["group"]
            train = [c for c in clips if c["group"] not in (0, group)]
            test = [c for c in clips if c["group"] == group]
            if [c["name"] for c in train] != selection["train_videos"] or [
                c["name"] for c in test
            ] != selection["test_videos"]:
                raise ValueError("Saved training split changed")
            scores = fit_scores(
                train,
                test,
                "phase",
                selection["history"],
                selection["regularization"],
                selection["classifier"],
            )
            for clip, score in zip(test, scores, strict=True):
                name = clip["name"]
                audit, row, arrays = audit_clip(clip, score, frozen["action/" + name])
                for key in ("phase", "output", "state"):
                    np.testing.assert_array_equal(
                        arrays[key], frozen["relative_position/" + key + "/" + name]
                    )
                previous = next(
                    r
                    for r in reference["families"]["relative_position"]["clips"]
                    if r["video"] == name
                )
                if row != {key: value for key, value in previous.items() if key != "phase_metrics"}:
                    raise ValueError("Single or repeated temporal metrics changed")
                audits.append(audit)
                rows.append(row)
                saved.update({key + "/" + name: value for key, value in arrays.items()})
                if args.plot:
                    path = args.output.parent / "0924-opening-scores" / (name + ".png")
                    plot_clip(clip, arrays, path)
                    plots.append(str(path.relative_to(ROOT)))
                    for index, (a, b) in enumerate(clip["opening_intervals"]):
                        padding = round(clip["fps"])
                        zoom = path.with_stem(path.stem + f"-anchor{index + 1}")
                        plot_clip(
                            clip,
                            arrays,
                            zoom,
                            (max(0, a - padding), min(len(score) - 1, b + padding)),
                        )
                        plots.append(str(zoom.relative_to(ROOT)))
                print(name, "verified", flush=True)
    predictions = ROOT / "shared/results/0924-cache" / (args.output.stem + "-predictions.npz")
    np.savez_compressed(predictions, **saved)
    report = dict(
        protocol=__doc__,
        sources=reference["sources"],
        selections=reference["selections"]["relative_position"],
        config=reference["config"],
        phase_labels=PHASES,
        states=STATES,
        clips=audits,
        evaluation=summarize_family(rows),
        plots=plots,
        reference_sha256=digest(reference_path),
        source_predictions_sha256=digest(frozen_path),
        script_sha256=digest(Path(__file__)),
        helper_sha256={
            p: digest(Path(__file__).with_name(p))
            for p in (
                "evaluate_timeline.py",
                "evaluate_opening_features.py",
                "evaluate_opening_setup.py",
                "evaluate_opening_temporal.py",
                "evaluate_opening_repetition.py",
            )
        },
        frame_predictions=str(predictions.relative_to(ROOT)),
        frame_predictions_sha256=digest(predictions),
    )
    if reference["config"] != vars(CONFIG):
        raise ValueError("Fixed temporal settings changed")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    print("Verified all frozen predictions and single/repeated metrics", flush=True)


if __name__ == "__main__":
    main()
