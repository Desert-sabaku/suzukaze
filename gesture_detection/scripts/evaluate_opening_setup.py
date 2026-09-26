"""Frozen 0924 setup-gate ablations and label-substitution diagnostics.

No fitting or threshold selection. Oracle substitutions are diagnostic only;
unknown phase remains predicted. Repeated signals are not independent examples
or a continuous-camera test. Only postprocessing state spans their joins.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

import numpy as np

from .evaluate_opening_repetition import repeat_clip, summarize
from .evaluate_opening_temporal import TemporalConfig, aggregate, apply_temporal, measure
from .evaluate_timeline import ACTIONS, PHASES, ROOT, digest, extract, positive_runs

CONFIG = TemporalConfig(0.75, 0.6, 0.3, "context", True)
POLICIES = {
    "baseline": (False, False),
    "initial_phase_only": (True, False),
    "rearm_phase_only": (False, True),
    "both_phase_only": (True, True),
}
ORACLES = ("oracle_action", "oracle_phase", "oracle_both")
STATES = ("WAIT_SETUP", "ARMED", "OPENED", "LOCKED")


def substitute(
    clip: dict, phase: np.ndarray, action: np.ndarray, family: str
) -> tuple[np.ndarray, np.ndarray]:
    """Diagnostic intervention, never filling unknown ground truth with NONE."""
    p, a = phase.copy(), action.copy()
    if family in ("oracle_action", "oracle_both"):
        known = clip["action"] >= 0
        a[known] = clip["action"][known]
    if family in ("oracle_phase", "oracle_both"):
        known = clip["phase"] >= 0
        p[known] = clip["phase"][known]
    return p, a


def predict(
    clip: dict, phase: np.ndarray, action: np.ndarray, family: str
) -> tuple[np.ndarray, list[int], list[dict]]:
    if family not in POLICIES and family not in ORACLES:
        raise ValueError(f"Unknown family: {family}")
    p, a = substitute(clip, phase, action, family)
    initial, rearm = POLICIES.get(family, (False, False))
    trace = []
    out, events = apply_temporal(
        p,
        a,
        clip["points"],
        clip["fps"],
        CONFIG,
        initial_setup_phase_only=initial,
        rearm_setup_phase_only=rearm,
        trace=trace,
    )
    return out, events, trace


def longest_evidence(mask: np.ndarray, fps: float) -> dict:
    """Dwell is timestamp span, (frames - 1) / fps, as used by the gate."""
    runs = positive_runs(mask)
    frames = max((b - a + 1 for a, b in runs), default=0)
    return dict(frames=frames, elapsed_seconds=max(0, frames - 1) / fps)


def diagnose(
    clip: dict,
    phase: np.ndarray,
    action: np.ndarray,
    outputs: dict[str, np.ndarray],
    trace: list[dict],
    family_traces: dict[str, list[dict]] | None = None,
) -> list[dict]:
    tracked = (clip["points"][:, :, 2] > 0.5).any(axis=1)
    wrists = (clip["points"][:, [15, 16], 2] > 0.5).all(axis=1)
    ready = np.isin(phase, (1, 2))
    rows = []
    diagnostics = {key: measure(clip, out, []) for key, out in outputs.items()}
    for number, (start, end) in enumerate(clip["opening_intervals"]):
        parent = next((a, b) for a, b in clip["ramune_intervals"] if a <= start <= end <= b)
        window = slice(parent[0], end + 1)
        preparation = slice(parent[0], start)
        joint = tracked & ready & (action == 1)
        masks = {
            "tracked": tracked,
            "both_wrists_visible": wrists,
            "action_ramune": action == 1,
            "phase_ready": ready,
            "tracked_phase_ready": tracked & ready,
            "joint_setup": joint,
        }
        hits = {
            key: data["details"][number]["matched_run"] is not None
            for key, data in diagnostics.items()
        }
        opened = np.flatnonzero(phase[window] == 3) + parent[0]
        future = np.flatnonzero(phase[end + 1 : parent[1] + 1] == 3) + end + 1
        starts = [a for a, _ in positive_runs(outputs["baseline"] == 3) if end < a <= parent[1]]
        blocks = {}
        for i in opened:
            if trace[i]["blocked_opened"]:
                state = trace[i]["state_before"]
                blocks[state] = blocks.get(state, 0) + 1
        gt_ready = np.isin(clip["phase"][preparation], (1, 2))
        if hits["baseline"]:
            outcome = "detected"
        elif not len(opened):
            outcome = (
                "phase_late_one_frame"
                if len(future) and future[0] == end + 1
                else "phase_no_opened_by_anchor"
            )
        elif blocks:
            outcome = "temporal_blocked_opened"
        else:
            outcome = "earlier_opened_did_not_cover_anchor"
        rows.append(
            dict(
                video=clip["name"],
                group=clip["group"],
                outcome=outcome,
                action_frames=list(parent),
                anchor_frames=[start, end],
                preparation_window=[preparation.start, preparation.stop - 1],
                setup_window=[parent[0], end],
                longest={
                    key: longest_evidence(mask[preparation], clip["fps"])
                    for key, mask in masks.items()
                },
                preparation_frames=preparation.stop - preparation.start,
                missing_pose_frames=int((~tracked[preparation]).sum()),
                low_wrist_visibility_frames=int((~wrists[preparation]).sum()),
                phase_ready_action_disagreement_frames=int(
                    (tracked[preparation] & ready[preparation] & (action[preparation] != 1)).sum()
                ),
                annotated_ready_frames=int(gt_ready.sum()),
                annotated_ready_action_miss_frames=int(
                    (gt_ready & (action[preparation] != 1)).sum()
                ),
                annotated_ready_phase_miss_frames=int((gt_ready & ~ready[preparation]).sum()),
                anchor_predicted_phases=[PHASES[int(value)] for value in phase[start : end + 1]],
                anchor_tracked_frames=int(tracked[start : end + 1].sum()),
                anchor_both_wrists_visible_frames=int(wrists[start : end + 1].sum()),
                raw_opened_frames_before_anchor_end=opened.tolist(),
                first_raw_opened_after_anchor_gap_frames=int(future[0] - end)
                if len(future)
                else None,
                first_output_after_anchor_gap_frames=starts[0] - end if starts else None,
                blocked_opened_frames_by_state=blocks,
                baseline_state_at_anchor=trace[start]["state_before"],
                baseline_state_transitions=[
                    row for row in trace if row["state_before"] != row["state_after"]
                ],
                family_state_transitions={
                    key: [row for row in audit if row["state_before"] != row["state_after"]]
                    for key, audit in (family_traces or {"baseline": trace}).items()
                },
                hits=hits,
            )
        )
    return rows


def evaluate_sample(
    clip: dict, phase: np.ndarray, action: np.ndarray, family: str
) -> tuple[dict, np.ndarray, list[dict]]:
    out, events, trace = predict(clip, phase, action, family)
    repetitions = []
    # Oracles are evaluated only on real source clips, not synthetic copies.
    if family in POLICIES:
        for missing in (0.0, 0.5, 2.0):
            pair, p, a, offset = repeat_clip(clip, phase, action, missing)
            repeated, pulses, _ = predict(pair, p, a, family)
            np.testing.assert_array_equal(out, repeated[: len(out)])
            result = measure(pair, repeated, pulses)
            count = len(clip["opening_intervals"])
            repetitions.append(
                dict(
                    missing_seconds=missing,
                    join_frame=offset,
                    anchors_per_copy=count,
                    first_hit=any(d["matched_run"] is not None for d in result["details"][:count]),
                    second_hit=any(d["matched_run"] is not None for d in result["details"][count:]),
                    diagnostics=result,
                )
            )
    row = dict(
        video=clip["name"],
        group=clip["group"],
        single=measure(clip, out, events),
        repetitions=repetitions,
    )
    return row, out, trace


def summarize_family(rows: list[dict]) -> dict:
    result = dict(clips=rows)
    for env in ("behind", "without"):
        relevant = [r for r in rows if bool(r["group"]) == (env == "behind")]
        repeats = {}
        for missing in (0.0, 0.5, 2.0):
            samples = [
                s for r in relevant for s in r["repetitions"] if s["missing_seconds"] == missing
            ]
            if samples:
                stats = summarize(samples)
                stats["unanchored_runs"] = sum(
                    len(s["diagnostics"]["unanchored_runs"]) for s in samples
                )
                stats["second_misses_given_first"] = (
                    stats["first_hits"] - stats["second_hits_given_first"]
                )
                repeats[str(missing)] = stats
        result[env] = dict(single=aggregate([r["single"] for r in relevant]), repetition=repeats)
    return result


def candidate_decision(baseline: dict, candidate: dict) -> dict:
    """No trade of missed openings for duplicates, even across environments."""
    reasons = []
    improved = False
    for env in ("behind", "without"):
        b, c = baseline[env]["single"], candidate[env]["single"]
        improved |= c["intervals_hit"] > b["intervals_hit"]
        if c["intervals_hit"] < b["intervals_hit"]:
            reasons.append(f"{env}: fewer anchors hit")
        for key in ("reappearance_runs", "unanchored_runs", "occurrence_restarts"):
            if c[key] > b[key]:
                reasons.append(f"{env}: increased {key}")
        for gap, b in baseline[env]["repetition"].items():
            c = candidate[env]["repetition"][gap]
            for key in ("second_misses_given_first", "reappearance_runs", "unanchored_runs"):
                if c[key] > b[key]:
                    reasons.append(f"{env}, gap {gap}: increased {key}")
    if not improved:
        reasons.append("no increase in anchors hit")
    return dict(eligible_for_next_validation=not reasons, reasons=reasons)


def plot_trial(
    clip: dict, phase: np.ndarray, action: np.ndarray, outputs: dict, trace: list[dict], path: Path
) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    t = np.arange(len(phase)) / clip["fps"]
    fig, axes = plt.subplots(6, 1, figsize=(14, 12), sharex=True, layout="constrained")
    fig.suptitle(clip["name"] + " | frozen predictions, fixed setup 0.3 s")
    for ax in axes:
        for a, b in clip["opening_intervals"]:
            ax.axvspan(a / clip["fps"], (b + 1) / clip["fps"], color="gold", alpha=0.3)
        ax.grid(alpha=0.2)
    axes[0].step(t, clip["action"], where="post", label="annotation", linewidth=2)
    axes[0].step(t, action, where="post", label="prediction", alpha=0.8)
    axes[0].set(yticks=range(len(ACTIONS)), yticklabels=ACTIONS, ylabel="Action")
    axes[0].legend(loc="upper right", ncol=2)
    axes[1].step(t, clip["phase"], where="post", label="annotation", linewidth=2)
    axes[1].step(t, phase, where="post", label="prediction", alpha=0.8)
    axes[1].set(yticks=range(-1, len(PHASES)), yticklabels=["UNKNOWN", *PHASES], ylabel="Phase")
    axes[2].plot(t, clip["points"][:, 15, 2], label="left wrist")
    axes[2].plot(t, clip["points"][:, 16, 2], label="right wrist")
    tracked = (clip["points"][:, :, 2] > 0.5).any(axis=1)
    axes[2].step(t, tracked.astype(float), where="post", label="any tracked", alpha=0.5)
    axes[2].axhline(0.5, color="gray", linestyle="--")
    axes[2].set(ylabel="Visibility", ylim=(-0.05, 1.05))
    axes[2].legend(loc="upper right", ncol=3)
    masks = [tracked & np.isin(phase, (1, 2)) & (action == 1), tracked & np.isin(phase, (1, 2))]
    for lane, mask in enumerate(masks):
        for a, b in positive_runs(mask):
            axes[3].broken_barh(
                [(a / clip["fps"], (b - a + 1) / clip["fps"])],
                (lane - 0.3, 0.6),
                facecolors=f"C{lane}",
            )
    axes[3].set(yticks=[0, 1], yticklabels=["joint setup", "phase-only setup"], ylim=(-0.5, 1.5))
    axes[4].step(t, [STATES.index(r["state_after"]) for r in trace], where="post")
    axes[4].set(yticks=range(len(STATES)), yticklabels=STATES, ylabel="Baseline state")
    for lane, family in enumerate(POLICIES):
        for a, b in positive_runs(outputs[family] == 3):
            axes[5].broken_barh(
                [(a / clip["fps"], (b - a + 1) / clip["fps"])],
                (lane - 0.3, 0.6),
                facecolors=f"C{lane}",
            )
    axes[5].set(
        yticks=range(len(POLICIES)),
        yticklabels=list(POLICIES),
        ylim=(-0.5, len(POLICIES) - 0.5),
        xlabel="Time (s); gold = annotated OPENED anchor",
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=130)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, default=ROOT / "docs/0924-opening-setup-results.json"
    )
    parser.add_argument("--plot", action="store_true")
    args = parser.parse_args()
    classifier_path = ROOT / "docs/0924-timeline-central-results.json"
    reference_path = ROOT / "docs/0924-opening-rearm-results.json"
    classifier = json.loads(classifier_path.read_text())
    reference = json.loads(reference_path.read_text())
    sources = {s["name"]: s for s in classifier["sources"]}
    paths = sorted((ROOT / "shared/annotations/0924").glob("*/timeline.json"))
    if {p.parent.name for p in paths} != set(sources):
        raise ValueError("Source set differs from frozen classifier report")
    prediction_path = ROOT / classifier["frame_predictions"]
    rows = {family: [] for family in (*POLICIES, *ORACLES)}
    diagnostics, plots, arrays = [], [], {}
    with np.load(prediction_path) as predictions:
        for path in paths:
            name = path.parent.name
            if digest(path) != sources[name]["annotation_sha256"]:
                raise ValueError("Annotations changed since frozen predictions")
            clip = extract(
                path, ROOT / "shared/results/0924-cache", select_subject=False, central_mask=True
            )
            phase, action = predictions["phase/" + name], predictions["action/" + name]
            if len(phase) != len(clip["phase"]) or len(action) != len(phase):
                raise ValueError("Frozen prediction frame count mismatch")
            outputs, traces = {}, {}
            for family in rows:
                row, out, trace = evaluate_sample(clip, phase, action, family)
                rows[family].append(row)
                outputs[family], traces[family] = out, trace
                arrays[family + "/" + name] = out
                arrays[family + "/state/" + name] = np.array(
                    [STATES.index(r["state_after"]) for r in trace], dtype=np.int8
                )
            # Ensure the added switches and trace did not alter existing behavior.
            old = next(
                r for r in reference["families"]["context_fixed"]["clips"] if r["video"] == name
            )
            if rows["baseline"][-1] != {k: v for k, v in old.items() if k != "config"}:
                raise ValueError(f"Fixed baseline changed: {name}")
            diagnostics.extend(diagnose(clip, phase, action, outputs, traces["baseline"], traces))
            if args.plot and clip["opening_intervals"]:
                plot_path = args.output.parent / "0924-opening-setup" / (name + ".png")
                plot_trial(clip, phase, action, outputs, traces["baseline"], plot_path)
                plots.append(str(plot_path.relative_to(ROOT)))
            print(name, "done", flush=True)
    families = {key: summarize_family(value) for key, value in rows.items()}
    output_predictions = (
        ROOT / "shared/results/0924-cache" / (args.output.stem + "-predictions.npz")
    )
    np.savez_compressed(output_predictions, **arrays)
    report = dict(
        protocol=__doc__,
        config=asdict(CONFIG),
        policies={
            key: dict(initial_setup_phase_only=a, rearm_setup_phase_only=b)
            for key, (a, b) in POLICIES.items()
        },
        oracle_families=list(ORACLES),
        families=families,
        diagnostics=diagnostics,
        decisions={
            key: candidate_decision(families["baseline"], families[key])
            for key in POLICIES
            if key != "baseline"
        },
        sources=classifier["sources"],
        classifier_report_sha256=digest(classifier_path),
        source_predictions_sha256=digest(prediction_path),
        reference_report_sha256=digest(reference_path),
        script_sha256=digest(Path(__file__)),
        helper_sha256={
            p: digest(Path(__file__).with_name(p))
            for p in (
                "evaluate_opening_temporal.py",
                "evaluate_opening_repetition.py",
                "evaluate_timeline.py",
            )
        },
        states=list(STATES),
        plots=plots,
        frame_predictions=str(output_predictions.relative_to(ROOT)),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    for key, family in families.items():
        print(key, {env: family[env]["single"] for env in ("behind", "without")}, flush=True)
    print(json.dumps(report["decisions"], indent=2), flush=True)


if __name__ == "__main__":
    main()
