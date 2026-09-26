"""Run frozen 0924 classifiers on a separate, unannotated continuous video."""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict
from pathlib import Path

import cv2
import numpy as np

from gesture_detection import config
from gesture_detection.pose_worker import PoseAnalyzer

from .evaluate_opening_temporal import TemporalConfig, apply_temporal
from .evaluate_timeline import (
    ROOT,
    digest,
    extract,
    features,
    fit_predict,
    positive_runs,
    runtime_settings,
)


def video_points(source: Path) -> dict:
    provenance = dict(
        source_sha256=digest(source),
        runtime=runtime_settings(),
        code_sha256=hashlib.sha256(
            b"".join(p.read_bytes() for p in sorted((ROOT / "src/gesture_detection").glob("*.py")))
        ).hexdigest(),
        central_mask=True,
        select_subject=False,
    )
    key = hashlib.sha256(json.dumps(provenance, sort_keys=True).encode()).hexdigest()
    cache = ROOT / "shared/results/0924-cache" / ("continuous-" + key + ".npz")
    capture = cv2.VideoCapture(str(source))
    if not capture.isOpened():
        raise ValueError(f"Cannot open {source}")
    fps = capture.get(cv2.CAP_PROP_FPS)
    aspect = capture.get(cv2.CAP_PROP_FRAME_WIDTH) / capture.get(cv2.CAP_PROP_FRAME_HEIGHT)
    if not np.isfinite(fps) or fps <= 0:
        capture.release()
        raise ValueError("Invalid video FPS")
    if cache.exists():
        capture.release()
        with np.load(cache) as arrays:
            points = arrays["points"]
    else:
        analyzer = PoseAnalyzer(running_mode="VIDEO", select_subject=False)
        frames = []
        try:
            while True:
                ok, frame = capture.read()
                if not ok:
                    break
                left, _, right, _ = config.SUBJECT_AREA
                frame[:, : round(left * frame.shape[1])] = 127
                frame[:, round(right * frame.shape[1]) :] = 127
                index = len(frames)
                result = analyzer.process(frame, index / fps, index)
                frames.append(result["landmarks"] or np.zeros((33, 3)).tolist())
                if index % 150 == 0:
                    print(f"{source.name}: {index} frames", flush=True)
        finally:
            analyzer.close()
            capture.release()
        points = np.asarray(frames)
        cache.parent.mkdir(parents=True, exist_ok=True)
        with cache.with_suffix(".tmp").open("wb") as stream:
            np.savez_compressed(stream, points=points)
        cache.with_suffix(".tmp").replace(cache)
    clip = dict(
        name=source.name,
        points=points,
        fps=fps,
        aspect=aspect,
        action=np.zeros(len(points), dtype=int),
        phase=np.zeros(len(points), dtype=int),
    )
    clip["features"] = {h: features(clip, h) for h in (0.25, 0.75)}
    return dict(clip=clip, provenance=provenance)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source", type=Path, default=ROOT / "shared/videos/kohara_ramune_01-おいしいかにかま.mov"
    )
    parser.add_argument(
        "--output", type=Path, default=ROOT / "docs/0924-opening-continuous-results.json"
    )
    args = parser.parse_args()
    data = video_points(args.source)
    clip = data["clip"]
    train = []
    for path in sorted((ROOT / "shared/annotations/0924").glob("*/timeline.json")):
        if "without" in path.parent.name:
            continue
        c = extract(
            path, ROOT / "shared/results/0924-cache", select_subject=False, central_mask=True
        )
        c["features"] = {h: features(c, h) for h in (0.25, 0.75)}
        train.append(c)
    if data["provenance"]["source_sha256"] in {c["video_sha256"] for c in train}:
        raise ValueError("Continuous test source must be outside the training videos")
    previous = json.loads((ROOT / "docs/0924-opening-temporal-results.json").read_text())
    selection = next(
        row
        for row in previous["selections"]
        if row["outer_group"] == 0 and row["family"] == "prepared_hands"
    )
    params = selection["classifier_parameters"]
    predicted = {
        target: fit_predict(train, [clip], target, *params[target])[0]
        for target in ("phase", "action")
    }
    configs = dict(
        raw=TemporalConfig(),
        previous=TemporalConfig(**selection["selected"]),
        context_release_060=TemporalConfig(0.75, 0.6, 0.3, "context", True),
        context_release_100=TemporalConfig(0.75, 1.0, 0.3, "context", True),
        hands_release_010=TemporalConfig(0.75, 0.1, 0.15, "hands", True),
    )
    results = {}
    saved = dict(raw_phase=predicted["phase"], raw_action=predicted["action"])
    for name, cfg in configs.items():
        out, events = apply_temporal(
            predicted["phase"], predicted["action"], clip["points"], clip["fps"], cfg
        )
        results[name] = dict(
            config=asdict(cfg),
            notification_frames=events,
            notification_seconds=[i / clip["fps"] for i in events],
            output_runs_frames=positive_runs(out == 3),
        )
        saved[name] = out
    save = ROOT / "shared/results/0924-cache" / (args.output.stem + "-predictions.npz")
    np.savez_compressed(save, **saved)
    report = dict(
        protocol=__doc__ + " No manual action/phase ground truth; outputs are not accuracy.",
        source=str(args.source.relative_to(ROOT))
        if args.source.is_relative_to(ROOT)
        else str(args.source),
        provenance=data["provenance"],
        fps=clip["fps"],
        frames=len(clip["points"]),
        classifier_parameters=params,
        train_videos=[c["name"] for c in train],
        results=results,
        frame_predictions=str(save.relative_to(ROOT)),
        script_sha256=digest(Path(__file__)),
        readiness_frames=int(
            ((predicted["action"] == 1) & np.isin(predicted["phase"], [1, 2])).sum()
        ),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(results, indent=2), flush=True)


if __name__ == "__main__":
    main()
