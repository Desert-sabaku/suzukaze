"""Causal ridge pilot with nested take-grouped validation; no production changes."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import tempfile
from pathlib import Path

import cv2
import mediapipe
import numpy as np

from gesture_detection import config
from gesture_detection.pose_worker import PoseAnalyzer

ROOT = Path(__file__).resolve().parents[1]
ACTIONS = ["NONE", "RAMUNE", "RELAXING", "FANNING", "UCHIMIZU"]
PHASES = ["NONE", "FORMING", "READY", "OPENED", "WAIT_RELEASE"]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def labels(doc: dict) -> tuple[np.ndarray, np.ndarray]:
    n = doc["source"]["total_frames"]
    action, phase = np.zeros(n, dtype=int), np.zeros(n, dtype=int)
    occupied = {}
    for item in doc["intervals"]:
        start, end, track = item["start_frame"], item["end_frame"], item["track"]
        if not 0 <= start <= end < n:
            raise ValueError("Invalid frame bounds")
        used = occupied.setdefault(track, np.zeros(n, dtype=bool))
        if used[start : end + 1].any():
            raise ValueError("Overlapping exclusive intervals")
        used[start : end + 1] = True
        if track == "action":
            action[start : end + 1] = ACTIONS.index(item["label"])
    phase[action != 0] = -1
    for item in doc["intervals"]:
        if item["track"] == "ramune_phase":
            start, end = item["start_frame"], item["end_frame"]
            if not np.all(action[start : end + 1] == 1):
                raise ValueError("Phase outside RAMUNE")
            phase[start : end + 1] = PHASES.index(item["label"])
    return action, phase


def runtime_settings() -> dict:
    return dict(
        python=platform.python_version(),
        numpy=np.__version__,
        opencv=cv2.__version__,
        mediapipe=mediapipe.__version__,
        model_sha256=digest(config.POSE_MODEL_PATH),
        subject_area=list(config.SUBJECT_AREA),
        subject_min_torso_height=config.SUBJECT_MIN_TORSO_HEIGHT,
        subject_min_shoulder_width=config.SUBJECT_MIN_SHOULDER_WIDTH,
        running_mode="VIDEO",
        timestamps="zero-based frame / annotation fps",
    )


def extract(
    path: Path,
    cache_root: Path,
    *,
    select_subject: bool = True,
    central_mask: bool = False,
    cache_only: bool = False,
) -> dict:
    doc = json.loads(path.read_text())
    name = path.parent.name
    source = ROOT / "shared/videos/0924" / (name + ".mp4")
    video_hash = digest(source)
    if video_hash != doc["source"]["sha256"]:
        raise ValueError(f"Video hash mismatch: {source}")
    code = b"".join(p.read_bytes() for p in sorted((ROOT / "src/gesture_detection").glob("*.py")))
    key = hashlib.sha256(
        code
        + config.POSE_MODEL_PATH.read_bytes()
        + video_hash.encode()
        + (b"full-fps-v1" if select_subject else b"full-fps-raw-v1")
        + (b"central-mask" if central_mask else b"")
    ).hexdigest()
    manifest = cache_root / "environment.json"
    cache = cache_root / (key + ".npz")
    if cache_only and (not cache.exists() or not manifest.exists()):
        raise FileNotFoundError(f"Required pose cache or manifest is missing: {cache}")
    cache_root.mkdir(parents=True, exist_ok=True)
    settings = runtime_settings()
    if manifest.exists() and json.loads(manifest.read_text()) != settings:
        raise ValueError("Inference environment changed; use a fresh --cache directory")
    if not manifest.exists():
        manifest.write_text(json.dumps(settings, indent=2) + "\n")
    action, phase = labels(doc)
    if not cache.exists():
        capture, analyzer = (
            cv2.VideoCapture(str(source)),
            PoseAnalyzer(running_mode="VIDEO", select_subject=select_subject),
        )
        points, predictions, states = [], [], []
        try:
            for index in range(len(action)):
                ok, frame = capture.read()
                if not ok:
                    raise ValueError(f"Truncated video: {source}")
                if central_mask:
                    left, _, right, _ = config.SUBJECT_AREA
                    width = frame.shape[1]
                    frame[:, : round(left * width)] = 127
                    frame[:, round(right * width) :] = 127
                result = analyzer.process(frame, index / doc["source"]["fps"], index)
                points.append(result["landmarks"] or np.zeros((33, 3)).tolist())
                predictions.append(ACTIONS.index(result["current"]["gesture"]))
                state = result["ramune_state"]
                states.append(PHASES.index(state) if state in PHASES else 0)
            if capture.read()[0]:
                raise ValueError("Frame count mismatch")
        finally:
            capture.release()
            analyzer.close()
        with tempfile.NamedTemporaryFile(dir=cache_root, suffix=".npz", delete=False) as temporary:
            np.savez_compressed(
                temporary, points=points, baseline=predictions, baseline_phase=states
            )
            temporary_path = Path(temporary.name)
        temporary_path.replace(cache)
    with np.load(cache) as data:
        arrays = {key: data[key] for key in data.files}
    if len(arrays["points"]) != len(action):
        raise ValueError("Cached frame count mismatch")
    return dict(
        name=name,
        action=action,
        phase=phase,
        fps=doc["source"]["fps"],
        aspect=doc["source"]["width"] / doc["source"]["height"],
        group=0 if "without" in name else int(name.split("_")[0][-1]),
        annotation_sha256=digest(path),
        video_sha256=video_hash,
        ramune_intervals=[
            (i["start_frame"], i["end_frame"])
            for i in doc["intervals"]
            if i["track"] == "action" and i["label"] == "RAMUNE"
        ],
        opening_intervals=[
            (i["start_frame"], i["end_frame"])
            for i in doc["intervals"]
            if i["track"] == "ramune_phase" and i["label"] == "OPENED"
        ],
        **arrays,
    )


def features(clip: dict, history: float) -> np.ndarray:
    """Body-relative geometry and causal history, without clip/time identifiers."""
    points = clip["points"][:, [11, 12, 13, 14, 15, 16, 23, 24]].copy()
    xy, vis = points[:, :, :2], points[:, :, 2]
    xy[:, :, 0] *= clip["aspect"]
    center, hips = (xy[:, 0] + xy[:, 1]) / 2, (xy[:, 6] + xy[:, 7]) / 2
    scale = np.maximum(np.linalg.norm(center - hips, axis=1), 0.03)
    xy = np.clip((xy - center[:, None]) / scale[:, None, None], -5, 5)
    xy[vis < 0.5] = 0
    current = np.concatenate([xy.reshape(len(xy), -1), vis], axis=1)
    window = max(1, round(history * clip["fps"]))
    means, stds, deltas = [], [], []
    for i in range(len(current)):
        segment = current[max(0, i - window + 1) : i + 1]
        means.append(segment.mean(axis=0))
        stds.append(segment.std(axis=0))
        deltas.append(current[i] - current[max(0, i - window)])
    return np.concatenate([current, means, stds, deltas], axis=1)


def design_matrix(values: np.ndarray, classifier: str) -> np.ndarray:
    if classifier == "rbf":
        projection = np.random.default_rng(924).normal(size=(values.shape[1], 64))
        projection /= np.sqrt(values.shape[1])
        angles = values @ projection
        values = np.column_stack([values, np.sin(angles), np.cos(angles)])
    return np.column_stack([values, np.ones(len(values))])


def fit_scores(
    train: list[dict],
    test: list[dict],
    target: str,
    history: float,
    regularization: float,
    classifier: str = "linear",
) -> list[np.ndarray]:
    """Return uncalibrated ridge scores; untrained classes are negative infinity."""
    x = np.concatenate([c["features"][history] for c in train])
    y = np.concatenate([c[target] for c in train])
    x, y = x[y >= 0], y[y >= 0]
    mean, scale = x.mean(axis=0), np.maximum(x.std(axis=0), 0.05)
    x = design_matrix(np.clip((x - mean) / scale, -10, 10), classifier)
    classes = len(ACTIONS if target == "action" else PHASES)
    counts = np.bincount(y, minlength=classes)
    weights = 1 / counts[y]
    weights *= len(weights) / weights.sum()
    penalty = np.eye(x.shape[1]) * regularization * len(x)
    penalty[-1, -1] = 0
    beta = np.linalg.solve(
        x.T @ (weights[:, None] * x) + penalty, x.T @ (weights[:, None] * np.eye(classes)[y])
    )
    output = []
    for clip in test:
        tx = design_matrix(np.clip((clip["features"][history] - mean) / scale, -10, 10), classifier)
        scores = tx @ beta
        scores[:, counts == 0] = -np.inf
        output.append(scores)
    return output


def predict_from_scores(scores: np.ndarray, points: np.ndarray) -> np.ndarray:
    """Preserve argmax tie order and the existing missing-pose NONE override."""
    pred = scores.argmax(axis=1)
    pred[~(points[:, :, 2] > 0.5).any(axis=1)] = 0
    return pred


def fit_predict(
    train: list[dict],
    test: list[dict],
    target: str,
    history: float,
    regularization: float,
    classifier: str = "linear",
) -> list[np.ndarray]:
    return [
        predict_from_scores(scores, clip["points"])
        for clip, scores in zip(
            test, fit_scores(train, test, target, history, regularization, classifier), strict=True
        )
    ]


def metrics(truth: np.ndarray, pred: np.ndarray, names: list[str]) -> dict:
    valid = truth >= 0
    truth, pred = truth[valid], pred[valid]
    matrix = np.zeros((len(names), len(names)), dtype=int)
    np.add.at(matrix, (truth, pred), 1)
    rows = {}
    for i, name in enumerate(names):
        tp, support, predicted = int(matrix[i, i]), int(matrix[i].sum()), int(matrix[:, i].sum())
        rows[name] = dict(
            support=support,
            precision=tp / predicted if predicted else 0,
            recall=tp / support if support else 0,
            f1=2 * tp / (support + predicted) if support + predicted else 0,
        )
    return dict(
        frames=len(truth),
        accuracy=float(np.mean(truth == pred)),
        macro_f1=float(np.mean([r["f1"] for r in rows.values() if r["support"]])),
        per_class=rows,
        confusion=matrix.tolist(),
    )


def choose(
    train: list[dict],
    target: str,
    classifiers: tuple[str, ...] = ("linear", "rbf"),
    *,
    audit: list[dict] | None = None,
) -> tuple[float, float, str]:
    candidates = []
    names = ACTIONS if target == "action" else PHASES
    for classifier in classifiers:
        for history in (0.25, 0.75):
            for regularization in (0.01, 0.1, 1.0):
                truths, predictions = [], []
                for group in sorted({c["group"] for c in train}):
                    inner_train = [c for c in train if c["group"] != group]
                    inner_test = [c for c in train if c["group"] == group]
                    predictions.extend(
                        fit_predict(
                            inner_train, inner_test, target, history, regularization, classifier
                        )
                    )
                    truths.extend(c[target] for c in inner_test)
                score = metrics(np.concatenate(truths), np.concatenate(predictions), names)[
                    "macro_f1"
                ]
                candidates.append((score, history, regularization, classifier))
                if audit is not None:
                    audit.append(
                        dict(
                            history=history,
                            regularization=regularization,
                            classifier=classifier,
                            macro_f1=score,
                        )
                    )
    _, history, regularization, classifier = max(candidates)
    return history, regularization, classifier


def evaluate(clips: list[dict], classifiers: tuple[str, ...] = ("linear", "rbf")) -> dict:
    report = {}
    for target, names, baseline_key in [
        ("action", ACTIONS, "baseline"),
        ("phase", PHASES, "baseline_phase"),
    ]:
        rows, accumulated = [], {"behind": [[], [], []], "without": [[], [], []]}
        for group in (1, 2, 3, 0):
            train = [c for c in clips if c["group"] not in (0, group)]
            test = [c for c in clips if c["group"] == group]
            history, regularization, classifier = choose(train, target, classifiers)
            predictions = fit_predict(train, test, target, history, regularization, classifier)
            for clip, pred in zip(test, predictions, strict=True):
                rows.append(
                    dict(
                        video=clip["name"],
                        group=group,
                        history=history,
                        regularization=regularization,
                        classifier=classifier,
                        baseline=metrics(clip[target], clip[baseline_key], names),
                        learned=metrics(clip[target], pred, names),
                        pose_fraction=float((clip["points"][:, :, 2] > 0.5).any(axis=1).mean()),
                        predictions=pred.tolist(),
                    )
                )
            truth, learned, baseline = accumulated["behind" if group else "without"]
            truth.extend(c[target] for c in test)
            learned.extend(predictions)
            baseline.extend(c[baseline_key] for c in test)
        result = dict(labels=names, clips=rows)
        for environment, (truth, learned, baseline) in accumulated.items():
            result[environment + "_baseline"] = metrics(
                np.concatenate(truth), np.concatenate(baseline), names
            )
            result[environment + "_learned"] = metrics(
                np.concatenate(truth), np.concatenate(learned), names
            )
        report[target] = result
    return report


def positive_runs(mask: np.ndarray) -> list[tuple[int, int]]:
    """Inclusive runs; even a one-frame interruption starts another run."""
    edges = np.diff(np.r_[False, mask, False].astype(int))
    return [
        (int(a), int(b - 1))
        for a, b in zip(np.flatnonzero(edges == 1), np.flatnonzero(edges == -1), strict=True)
    ]


def opening_diagnostics(clip: dict, prediction: np.ndarray) -> dict:
    """Accept continuous extension around anchors; identify separate reappearances.

    One run matches at most one opening. Recurrence observation ends at the next
    annotated RAMUNE occurrence, or video end. No gaps are silently bridged.
    """
    anchors = sorted(clip.get("opening_intervals", positive_runs(clip["phase"] == 3)))
    actions = sorted(clip.get("ramune_intervals", positive_runs(clip["action"] == 1)))
    runs = positive_runs(prediction == PHASES.index("OPENED"))
    matched, repeated = set(), set()
    details = []
    fps = clip.get("fps", 1.0)
    for start, end in anchors:
        parent = next((a for a in actions if a[0] <= start <= end <= a[1]), None)
        if parent is None:
            raise ValueError("OPENED anchor outside RAMUNE occurrence")
        limit = next((a[0] for a in actions if a[0] > parent[0]), len(prediction))
        hits = [
            i
            for i, (a, b) in enumerate(runs)
            if i not in matched | repeated and a <= end and b >= start
        ]
        row = dict(
            annotation_frames=[start, end],
            recurrence_window_end_frame=limit - 1,
            matched_run=None,
            reappearances=[],
        )
        if hits:
            selected = hits[0]
            matched.add(selected)
            a, b = runs[selected]
            row["matched_run"] = dict(
                frames=[a, b],
                extension_before_seconds=max(0, start - a) / fps,
                extension_after_seconds=max(0, b - end) / fps,
            )
            previous_end = b
            for i, (later_start, later_end) in enumerate(runs):
                if b < later_start < limit and i not in matched | repeated:
                    repeated.add(i)
                    row["reappearances"].append(
                        dict(
                            frames=[later_start, later_end],
                            gap_seconds=(later_start - previous_end - 1) / fps,
                        )
                    )
                    previous_end = later_end
        details.append(row)
    occurrence_details = []
    for index, (start, end) in enumerate(actions):
        limit = actions[index + 1][0] if index + 1 < len(actions) else len(prediction)
        observed = [(a, b) for a, b in runs if a < limit and b >= start]
        occurrence_details.append(
            dict(
                action_frames=[start, end],
                observation_end_frame=limit - 1,
                runs=[list(run) for run in observed],
                gap_seconds=[
                    (a - previous_end - 1) / fps
                    for (_, previous_end), (a, _) in zip(observed[:-1], observed[1:], strict=True)
                ],
            )
        )
    return dict(
        specification="anchor-overlap-v2; continuous extension accepted; every gap splits runs",
        intervals=len(anchors),
        intervals_hit=len(matched),
        predicted_runs=len(runs),
        reappearance_runs=len(repeated),
        openings_with_reappearance=sum(bool(d["reappearances"]) for d in details),
        unanchored_runs=[list(run) for i, run in enumerate(runs) if i not in matched | repeated],
        details=details,
        occurrences_with_multiple_runs=sum(len(d["runs"]) > 1 for d in occurrence_details),
        occurrence_restarts=sum(max(0, len(d["runs"]) - 1) for d in occurrence_details),
        occurrence_details=occurrence_details,
    )


def rescore_openings(output: Path, cache: Path) -> None:
    """Rescore frozen predictions, preserving original annotations and models."""
    report = json.loads(output.read_text())
    prediction_path = Path(report["frame_predictions"])
    if not prediction_path.is_absolute():
        prediction_path = ROOT / prediction_path
    sources = {source["name"]: source for source in report["sources"]}
    with np.load(prediction_path) as predictions:
        for row in report["results"]["phase"]["clips"]:
            path = ROOT / "shared/annotations/0924" / row["video"] / "timeline.json"
            if digest(path) != sources[row["video"]]["annotation_sha256"]:
                raise ValueError("Annotations changed since frozen prediction evaluation")
            clip = extract(
                path,
                cache,
                select_subject=report["select_subject"],
                central_mask=report.get("central_mask", False),
            )
            row["opening_baseline"] = opening_diagnostics(clip, clip["baseline_phase"])
            row["opening_learned"] = opening_diagnostics(clip, predictions["phase/" + row["video"]])
    report["opening_evaluation"] = (
        "anchor-overlap-v2; models selected with original strict frame labels"
    )
    output.write_text(json.dumps(report, indent=2) + "\n")


def enrich(report: dict, clips: list[dict]) -> None:
    for row in report["action"]["clips"]:
        clip = next(c for c in clips if c["name"] == row["video"])
        available = (clip["points"][:, :, 2] > 0.5).any(axis=1)
        row["pose_by_action"] = {
            name: float(available[clip["action"] == index].mean())
            for index, name in enumerate(ACTIONS)
            if (clip["action"] == index).any()
        }
    for environment, group_test in [
        ("behind", lambda c: c["group"] != 0),
        ("without", lambda c: c["group"] == 0),
    ]:
        selected = [c for c in clips if group_test(c)]
        context = []
        for clip in selected:
            prediction = clip["baseline"].copy()
            prediction[clip["baseline_phase"] > 0] = 1
            context.append(prediction)
        truth = np.concatenate([c["action"] for c in selected])
        report["action"][environment + "_context_baseline"] = metrics(
            truth, np.concatenate(context), ACTIONS
        )
        report["action"][environment + "_always_none"] = metrics(
            truth, np.zeros_like(truth), ACTIONS
        )
    for row in report["phase"]["clips"]:
        clip = next(c for c in clips if c["name"] == row["video"])
        row["opening_baseline"] = opening_diagnostics(clip, clip["baseline_phase"])
        row["opening_learned"] = opening_diagnostics(clip, np.asarray(row["predictions"]))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "docs/0924-timeline-results.json")
    parser.add_argument("--cache", type=Path, default=ROOT / "shared/results/0924-cache")
    parser.add_argument("--linear-only", action="store_true")
    parser.add_argument("--central-mask", action="store_true")
    parser.add_argument("--no-subject-selection", action="store_true")
    parser.add_argument("--rescore-openings", action="store_true")
    args = parser.parse_args()
    if args.rescore_openings:
        rescore_openings(args.output, args.cache)
        return
    clips = []
    for path in sorted((ROOT / "shared/annotations/0924").glob("*/timeline.json")):
        print(f"Extracting {path.parent.name}", flush=True)
        clip = extract(
            path,
            args.cache,
            select_subject=not args.no_subject_selection,
            central_mask=args.central_mask,
        )
        clip["features"] = {h: features(clip, h) for h in (0.25, 0.75)}
        clips.append(clip)
    if {c["group"] for c in clips} != {0, 1, 2, 3}:
        raise ValueError("Expected three behind-screen takes and without-screen controls")
    print("Nested grouped evaluation", flush=True)
    report = dict(
        select_subject=not args.no_subject_selection,
        central_mask=args.central_mask,
        protocol="Behind: outer take 1/2/3, inner leave-take-out; without: held out; full source fps; causal features; unlabelled action=NONE; unknown phase excluded; inclusive endpoints",
        sources=[
            {k: c[k] for k in ("name", "fps", "annotation_sha256", "video_sha256")} for c in clips
        ],
        opening_evaluation="anchor-overlap-v2; models selected with original strict frame labels",
        classifier_candidates=["linear"] if args.linear_only else ["linear", "rbf"],
        results=evaluate(clips, ("linear",) if args.linear_only else ("linear", "rbf")),
    )
    enrich(report["results"], clips)
    report["runtime"] = runtime_settings()
    frame_predictions = {}
    for target, result in report["results"].items():
        for row in result["clips"]:
            frame_predictions[target + "/" + row["video"]] = np.asarray(row.pop("predictions"))
    prediction_path = args.cache / (args.output.stem + "-predictions.npz")
    np.savez_compressed(prediction_path, **frame_predictions)
    report["frame_predictions"] = (
        str(prediction_path.relative_to(ROOT))
        if prediction_path.is_relative_to(ROOT)
        else str(prediction_path)
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(args.output, flush=True)


if __name__ == "__main__":
    main()
