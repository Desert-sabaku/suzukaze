"""Export the fixed 0924 action/relative-phase models; never tune on controls."""

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

from gesture_detection import config

from .evaluate_opening_features import feature_sets
from .evaluate_timeline import ROOT, design_matrix, digest, extract, features


def prepare_snapshot(path: Path) -> None:
    """For a fresh checkout: derive poses from the dataset with the rule profile."""
    if config.RAMUNE_DETECTOR != "rules":
        raise ValueError("Prepare poses with RAMUNE_DETECTOR=rules")
    arrays, records = {}, []
    for annotation in sorted((ROOT / "shared/annotations/0924").glob("*/timeline.json")):
        clip = extract(
            annotation, ROOT / "shared/results/0924-cache", select_subject=False, central_mask=True
        )
        records.append(
            {
                k: clip[k]
                for k in (
                    "name",
                    "fps",
                    "aspect",
                    "group",
                    "annotation_sha256",
                    "video_sha256",
                    "opening_intervals",
                    "ramune_intervals",
                )
            }
        )
        for key in ("points", "action", "phase"):
            arrays[clip["name"] + "/" + key] = clip[key]
    if len(records) != 16:
        raise ValueError("Expected the 16 annotated 0924 videos")
    metadata = dict(
        clips=records,
        pose_pipeline_sha256=hashlib.sha256(
            b"".join(p.read_bytes() for p in sorted((ROOT / "src/gesture_detection").glob("*.py")))
        ).hexdigest(),
        environment=json.loads((ROOT / "shared/results/0924-cache/environment.json").read_text()),
    )
    arrays["metadata"] = np.array(json.dumps(metadata))
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(path, **arrays)


def load_snapshot(path: Path) -> tuple[list[dict], dict]:
    with np.load(path, allow_pickle=False) as data:
        metadata = json.loads(str(data["metadata"]))
        clips = [
            dict(
                c,
                **{
                    key: data[c["name"] + "/" + key].copy() for key in ("points", "action", "phase")
                },
            )
            for c in metadata["clips"]
        ]
    for c in clips:
        annotation = ROOT / "shared/annotations/0924" / c["name"] / "timeline.json"
        if digest(annotation) != c["annotation_sha256"]:
            raise ValueError("Frozen snapshot annotation changed")
    return clips, metadata


def fit_model(clips: list[dict], target: str, params: dict) -> dict[str, np.ndarray]:
    history = params["history"]
    x = np.concatenate(
        [
            feature_sets(c)["relative_position"][history]
            if target == "phase"
            else features(c, history)
            for c in clips
        ]
    )
    y = np.concatenate([c[target] for c in clips])
    x, y = x[y >= 0], y[y >= 0]
    mean, scale = x.mean(axis=0), np.maximum(x.std(axis=0), 0.05)
    x = design_matrix(np.clip((x - mean) / scale, -10, 10), params["classifier"])
    counts = np.bincount(y, minlength=5)
    weights = 1 / counts[y]
    weights *= len(weights) / weights.sum()
    penalty = np.eye(x.shape[1]) * params["regularization"] * len(x)
    penalty[-1, -1] = 0
    beta = np.linalg.solve(
        x.T @ (weights[:, None] * x) + penalty, x.T @ (weights[:, None] * np.eye(5)[y])
    )
    projection = np.random.default_rng(924).normal(size=(len(mean), 64)) / np.sqrt(len(mean))
    return dict(mean=mean, scale=scale, beta=beta, counts=counts, projection=projection)


def build_bundle(clips: list[dict], phase_params: dict, action_params: dict) -> dict:
    arrays = {}
    for target, params in (("phase", phase_params), ("action", action_params)):
        arrays.update({target + "_" + k: v for k, v in fit_model(clips, target, params).items()})
    metadata = dict(
        format_version=1,
        feature_schema="0924-relative-position-v1",
        phase=phase_params,
        action=action_params,
        phase_labels=["NONE", "FORMING", "READY", "OPENED", "WAIT_RELEASE"],
        action_labels=["NONE", "RAMUNE", "RELAXING", "FANNING", "UCHIMIZU"],
        hold_seconds=0.75,
        release_seconds=0.6,
        setup_seconds=0.3,
        central_mask=[0.35, 0.75],
        training_sources=[
            {k: c[k] for k in ("name", "video_sha256", "annotation_sha256")} for c in clips
        ],
    )
    arrays["metadata"] = np.array(json.dumps(metadata))
    return arrays


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--snapshot", type=Path, default=ROOT / "shared/results/0924-cache/runtime-source.npz"
    )
    parser.add_argument(
        "--output", type=Path, default=ROOT / "src/gesture_detection/models/ramune_0924.npz"
    )
    parser.add_argument("--prepare-snapshot", action="store_true")
    args = parser.parse_args()
    if args.prepare_snapshot:
        if args.snapshot.exists():
            raise ValueError("Choose a new --snapshot path to preserve the frozen source")
        prepare_snapshot(args.snapshot)
    clips, provenance = load_snapshot(args.snapshot)
    phase_path = ROOT / "docs/0924-opening-features-results.json"
    action_path = ROOT / "docs/0924-timeline-central-results.json"
    phase = next(
        s
        for s in json.loads(phase_path.read_text())["selections"]["relative_position"]
        if s["group"] == 0
    )
    action = next(
        s
        for s in json.loads(action_path.read_text())["results"]["action"]["clips"]
        if s["group"] == 0
    )
    keys = ("history", "regularization", "classifier")
    arrays = build_bundle(
        [c for c in clips if c["group"] != 0],
        {k: phase[k] for k in keys},
        {k: action[k] for k in keys},
    )
    metadata = json.loads(str(arrays["metadata"]))
    metadata.update(
        snapshot_sha256=digest(args.snapshot),
        pose_provenance=provenance,
        phase_report_sha256=digest(phase_path),
        action_report_sha256=digest(action_path),
    )
    arrays["metadata"] = np.array(json.dumps(metadata))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(args.output, **arrays)
    args.output.with_suffix(".json").write_text(
        json.dumps(dict(metadata, model_sha256=digest(args.output)), indent=2) + "\n"
    )
    print(args.output, digest(args.output), flush=True)


if __name__ == "__main__":
    main()
