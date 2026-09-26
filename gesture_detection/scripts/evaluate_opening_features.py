"""Compare cached-pose phase features with nested take validation.

Action predictions and temporal settings are frozen. Feature families are
exploratory comparisons, not selected on unseen data. No pose inference runs.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

import numpy as np

from .evaluate_opening_setup import (
    CONFIG,
    STATES,
    candidate_decision,
    evaluate_sample,
    summarize_family,
)
from .evaluate_timeline import (
    PHASES,
    ROOT,
    choose,
    digest,
    extract,
    features,
    fit_predict,
    metrics,
    positive_runs,
)

FAMILIES = ("baseline", "relative_position", "relative_motion")
GEOMETRY = (
    "wrist_horizontal_distance", "wrist_vertical_distance", "wrist_distance",
    "left_wrist_x", "left_wrist_y", "right_wrist_x", "right_wrist_y",
)
LAGS = (0.1, 0.2)


def relative_geometry(clip: dict) -> tuple[np.ndarray, np.ndarray]:
    """Shoulder-width units, image x aspect-corrected, y positive downwards."""
    points = np.asarray(clip["points"][:, [11, 12, 15, 16]], dtype=float)
    valid = (points[:, :, 2] > 0.5) & np.isfinite(points).all(axis=2)
    xy = np.where(np.isfinite(points[:, :, :2]), points[:, :, :2], 0.0)
    xy[:, :, 0] *= clip["aspect"]
    center = xy[:, :2].mean(axis=1)
    width = np.linalg.norm(xy[:, 0] - xy[:, 1], axis=1)
    shoulders = valid[:, :2].all(axis=1) & (width > 1e-6)
    denominator = np.where(shoulders, width, 1.0)
    wrists = (xy[:, 2:] - center[:, None]) / denominator[:, None, None]
    delta = wrists[:, 0] - wrists[:, 1]
    values = np.column_stack([
        np.abs(delta[:, 0]), np.abs(delta[:, 1]), np.linalg.norm(delta, axis=1),
        wrists.reshape(len(points), 4),
    ])
    left, right = shoulders & valid[:, 2], shoulders & valid[:, 3]
    flags = np.column_stack([left & right] * 3 + [left] * 2 + [right] * 2)
    return np.where(flags, values, 0.0), flags


def motion_features(values: np.ndarray, flags: np.ndarray, fps: float) -> np.ndarray:
    """Endpoint-valid backward velocities; no startup padding or interpolation."""
    if not np.isfinite(fps) or fps <= 0:
        raise ValueError("FPS must be positive and finite")
    blocks = []
    for seconds in LAGS:
        lag = max(1, round(seconds * fps))
        valid = np.zeros_like(flags)
        velocity = np.zeros_like(values)
        valid[lag:] = flags[lag:] & flags[:-lag]
        velocity[lag:] = np.where(valid[lag:], (values[lag:] - values[:-lag]) / (lag / fps), 0.0)
        blocks.extend([velocity, valid.astype(float)])
    return np.column_stack(blocks)


def feature_sets(clip: dict) -> dict[str, dict[float, np.ndarray]]:
    position, valid = relative_geometry(clip)
    geometry = np.column_stack([position, valid.astype(float)])
    motion = motion_features(position, valid, clip["fps"])
    result = {key: {} for key in FAMILIES}
    for history in (0.25, 0.75):
        base = features(clip, history)
        result["baseline"][history] = base
        result["relative_position"][history] = np.column_stack([base, geometry])
        result["relative_motion"][history] = np.column_stack([base, geometry, motion])
    return result


def phase_predictions(clips: list[dict], family: str) -> tuple[dict[str, np.ndarray], list[dict]]:
    prepared = [dict(c, features=c["feature_sets"][family]) for c in clips]
    result, selections = {}, []
    for group in (1, 2, 3, 0):
        train = [c for c in prepared if c["group"] not in (0, group)]
        test = [c for c in prepared if c["group"] == group]
        trials = []
        params = choose(train, "phase", audit=trials)
        predicted = fit_predict(train, test, "phase", *params)
        result.update((c["name"], p) for c, p in zip(test, predicted, strict=True))
        selections.append(dict(
            group=group, history=params[0], regularization=params[1], classifier=params[2],
            train_videos=[c["name"] for c in train], test_videos=[c["name"] for c in test],
            inner_folds=[dict(
                train_videos=[c["name"] for c in train if c["group"] != inner],
                validation_videos=[c["name"] for c in train if c["group"] == inner],
            ) for inner in sorted({c["group"] for c in train})],
            trials=trials,
        ))
        print(f"{family}: outer {group}, selected {params}", flush=True)
    return result, selections


def anchor_details(clip: dict, phase: np.ndarray, row: dict, trace: list[dict]) -> list[dict]:
    result = []
    _, valid = relative_geometry(clip)
    for (start, end), match in zip(clip["opening_intervals"], row["single"]["details"], strict=True):
        parent = next((a, b) for a, b in clip["ramune_intervals"] if a <= start <= end <= b)
        later = [a for a, _ in positive_runs(np.array([r["state_after"] == "OPENED" for r in trace]))
                 if end < a <= parent[1]]
        result.append(dict(
            video=clip["name"], anchor_frames=[start, end],
            hit=match["matched_run"] is not None, matched_run=match["matched_run"],
            predicted_phases=[PHASES[int(p)] for p in phase[start:end + 1]],
            state_at_anchor=trace[start]["state_before"],
            first_output_after_anchor_gap_frames=later[0] - end if later else None,
            geometry_valid_anchor_frames=int(valid[start:end + 1, 0].sum()),
            geometry_valid_preparation_fraction=float(valid[parent[0]:start, 0].mean())
            if start > parent[0] else None,
        ))
    return result


def plot_trial(clip: dict, arrays: dict, path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    t = np.arange(len(clip["phase"])) / clip["fps"]
    fig, axes = plt.subplots(6, 1, figsize=(14, 12), sharex=True, layout="constrained")
    fig.suptitle(clip["name"] + " | phase feature comparison; fixed action and temporal gates")
    for ax in axes:
        for a, b in clip["opening_intervals"]:
            ax.axvspan(a / clip["fps"], (b + 1) / clip["fps"], color="gold", alpha=0.3)
        ax.grid(alpha=0.2)
    for index, family in enumerate(FAMILIES):
        axes[index].step(t, clip["phase"], where="post", label="annotation", linewidth=2)
        axes[index].step(t, arrays[family + "/phase/" + clip["name"]], where="post", label=family)
        axes[index].set(yticks=range(-1, len(PHASES)), yticklabels=["UNKNOWN", *PHASES])
        axes[index].legend(loc="upper right", ncol=2)
        for a, b in positive_runs(arrays[family + "/output/" + clip["name"]] == 3):
            axes[5].broken_barh([(a / clip["fps"], (b - a + 1) / clip["fps"])],
                                (index - 0.3, 0.6), facecolors=f"C{index}")
    position, valid = relative_geometry(clip)
    axes[3].plot(t, np.where(valid[:, 2], position[:, 2], np.nan), label="wrist distance",
                 marker=".", markersize=2)
    axes[3].plot(t, np.where(valid[:, 1], position[:, 1], np.nan), label="vertical distance",
                 marker=".", markersize=2)
    axes[3].set(ylabel="Shoulder widths")
    axes[3].legend(loc="upper right", ncol=2)
    speed = motion_features(position, valid, clip["fps"])
    for offset, lag in ((0, 0.1), (14, 0.2)):
        axes[4].plot(t, np.where(speed[:, offset + 9] > 0, speed[:, offset + 2], np.nan),
                     label=f"distance velocity {lag} s", marker=".", markersize=2)
    axes[4].set(ylabel="Shoulder widths / s")
    axes[4].legend(loc="upper right", ncol=2)
    axes[5].set(yticks=range(len(FAMILIES)), yticklabels=FAMILIES, ylim=(-0.5, 2.5),
                xlabel="Time (s); gold = annotated OPENED anchor")
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=130)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "docs/0924-opening-features-results.json")
    parser.add_argument("--plot", action="store_true")
    args = parser.parse_args()
    source_path = ROOT / "docs/0924-timeline-central-results.json"
    setup_path = ROOT / "docs/0924-opening-setup-results.json"
    source = json.loads(source_path.read_text())
    setup = json.loads(setup_path.read_text())
    sources = {row["name"]: row for row in source["sources"]}
    paths = sorted((ROOT / "shared/annotations/0924").glob("*/timeline.json"))
    if {p.parent.name for p in paths} != set(sources):
        raise ValueError("Source set changed since frozen baseline")
    frozen_path = ROOT / source["frame_predictions"]
    if digest(frozen_path) != setup["source_predictions_sha256"]:
        raise ValueError("Frozen predictions changed since setup experiment")
    clips = []
    for path in paths:
        if digest(path) != sources[path.parent.name]["annotation_sha256"]:
            raise ValueError("Annotations changed since frozen baseline")
        clip = extract(path, ROOT / "shared/results/0924-cache", select_subject=False,
                       central_mask=True, cache_only=True)
        clip["feature_sets"] = feature_sets(clip)
        clips.append(clip)
    families, selections, arrays, details = {}, {}, {}, {}
    with np.load(frozen_path) as frozen:
        for family in FAMILIES:
            predictions, selections[family] = phase_predictions(clips, family)
            rows, details[family] = [], []
            for clip in clips:
                name = clip["name"]
                phase, action = predictions[name], frozen["action/" + name]
                if len(action) != len(phase):
                    raise ValueError("Frozen action frame count mismatch")
                if family == "baseline":
                    np.testing.assert_array_equal(phase, frozen["phase/" + name])
                row, out, trace = evaluate_sample(clip, phase, action, "baseline")
                if family == "baseline":
                    previous = next(r for r in setup["families"]["baseline"]["clips"] if r["video"] == name)
                    if row != previous:
                        raise ValueError(f"Temporal baseline changed: {name}")
                details[family].extend(anchor_details(clip, phase, row, trace))
                row["phase_metrics"] = metrics(clip["phase"], phase, PHASES)
                rows.append(row)
                arrays["action/" + name] = action.copy()
                arrays[family + "/phase/" + name] = phase
                arrays[family + "/output/" + name] = out
                arrays[family + "/state/" + name] = np.array(
                    [STATES.index(r["state_after"]) for r in trace], dtype=np.int8
                )
            families[family] = summarize_family(rows)
            for env in ("behind", "without"):
                relevant = [c for c in clips if bool(c["group"]) == (env == "behind")]
                families[family][env]["phase_metrics"] = metrics(
                    np.concatenate([c["phase"] for c in relevant]),
                    np.concatenate([predictions[c["name"]] for c in relevant]), PHASES,
                )
    # Parameter selection, not just final argmax predictions, must reproduce the baseline.
    for selected in selections["baseline"]:
        previous = next(r for r in source["results"]["phase"]["clips"] if r["group"] == selected["group"])
        if any(selected[k] != previous[k] for k in ("history", "regularization", "classifier")):
            raise ValueError("Baseline parameter selection changed")
    plots = []
    if args.plot:
        for clip in clips:
            if clip["opening_intervals"]:
                path = args.output.parent / "0924-opening-features" / (clip["name"] + ".png")
                plot_trial(clip, arrays, path)
                plots.append(str(path.relative_to(ROOT)))
    prediction_path = ROOT / "shared/results/0924-cache" / (args.output.stem + "-predictions.npz")
    np.savez_compressed(prediction_path, **arrays)
    report = dict(
        protocol=__doc__, sources=source["sources"], config=asdict(CONFIG),
        feature_schema=dict(geometry=list(GEOMETRY), lags_seconds=list(LAGS),
                            units="shoulder widths; backward velocity per second",
                            dimensions={key: clips[0]["feature_sets"][key][0.25].shape[1] for key in FAMILIES},
                            layout="96 baseline + 7 geometry + 7 valid; motion adds 7 velocities + 7 valid per lag"),
        families=families, selections=selections, anchor_details=details,
        decisions={key: candidate_decision(families["baseline"], families[key]) for key in FAMILIES[1:]},
        source_report_sha256=digest(source_path), setup_report_sha256=digest(setup_path),
        source_predictions_sha256=digest(frozen_path), script_sha256=digest(Path(__file__)),
        helper_sha256={p: digest(Path(__file__).with_name(p)) for p in (
            "evaluate_timeline.py", "evaluate_opening_setup.py", "evaluate_opening_temporal.py",
            "evaluate_opening_repetition.py",
        )},
        plots=plots, states=list(STATES), frame_predictions=str(prediction_path.relative_to(ROOT)),
        frame_predictions_sha256=digest(prediction_path),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    for family in FAMILIES:
        print(family, {env: families[family][env]["single"] for env in ("behind", "without")}, flush=True)
    print(json.dumps(report["decisions"], indent=2), flush=True)


if __name__ == "__main__":
    main()
