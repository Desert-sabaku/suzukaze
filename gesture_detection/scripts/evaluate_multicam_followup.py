"""Fixed-footage ROI ablation and causal detector diagnostics for 0928."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import cv2
import numpy as np

from gesture_detection import config, pose_worker, subject_selection
from gesture_detection.learned_ramune import LearnedRamuneAnalyzer
from gesture_detection.ramune import RamuneAnalyzer
from gesture_detection.recognition import RecognitionCoordinator

from .evaluate_multicam import ROOT, digest, score

# Chosen once from the scene contact sheets, without optimizing recognition scores.
# Left/top/right/bottom; the current seed mask uses left/right only.
AREAS = {1: (0.20, 0.0, 0.95, 1.0), 2: (0.0, 0.0, 0.70, 1.0)}
NAMES = {
    0: "nose",
    11: "left_shoulder",
    12: "right_shoulder",
    13: "left_elbow",
    14: "right_elbow",
    15: "left_wrist",
    16: "right_wrist",
    23: "left_hip",
    24: "right_hip",
    25: "left_knee",
    26: "right_knee",
    27: "left_ankle",
    28: "right_ankle",
    29: "left_heel",
    30: "right_heel",
    31: "left_foot",
    32: "right_foot",
}


def objects(points: np.ndarray) -> list:
    return (
        [SimpleNamespace(x=p[0], y=p[1], visibility=p[2]) for p in points]
        if points.any()
        else []
    )


def ramune_probe(detector: RamuneAnalyzer, points: np.ndarray, now: float) -> dict:
    """Measure inputs to the existing rule before update; do not advance its state."""
    row = dict(before=detector.state, reset_conditions=[])
    reasons = row["reset_conditions"]
    if not points.any():
        reasons.append("missing_pose")
        return row
    if (points[[11, 12, 15, 16, 23, 24], 2] <= 0.5).any():
        reasons.append("required_visibility")
        return row
    scale = abs(points[11, 0] - points[12, 0])
    if scale < 1e-6:
        reasons.append("shoulder_scale")
        return row
    lower = max((15, 16), key=lambda i: points[i, 1])
    gap = (points[lower, 1] - points[31 - lower, 1]) / scale
    aligned = (
        abs(points[15, 0] - points[16, 0]) / scale <= config.RAMUNE_ALIGN_TOLERANCE
    )
    in_torso = (
        points[[11, 12], 1].mean() <= points[lower, 1] <= points[[23, 24], 1].mean()
    )
    row.update(gap=float(gap), aligned=bool(aligned), in_torso=bool(in_torso))
    if detector.state not in ("FORMING", "READY"):
        return row
    assert detector.base_index is not None
    base, pressing = points[detector.base_index], points[31 - detector.base_index]
    base_dx = abs(base[0] - detector.base[0]) / detector.scale
    base_dy = abs(base[1] - detector.base[1]) / detector.scale
    if base_dx > config.RAMUNE_BASE_X_TOLERANCE:
        reasons.append("base_x_drift")
    if base_dy > config.RAMUNE_BASE_TOLERANCE:
        reasons.append("base_y_drift")
    if not aligned:
        reasons.append("hand_alignment")
    if not in_torso:
        reasons.append("outside_torso")
    if detector.state == "FORMING":
        if not config.RAMUNE_MIN_READY_GAP <= gap <= config.RAMUNE_MAX_READY_GAP:
            reasons.append("forming_gap")
        if lower != detector.base_index:
            reasons.append("base_hand_swap")
        return row
    press = (pressing[1] - detector.upper_y) / detector.scale
    remaining = (base[1] - pressing[1]) / detector.scale
    closing = detector.ready_gap - remaining
    if now - detector.since > config.RAMUNE_PRESS_TIMEOUT:
        reasons.append("press_timeout")
    if press < -config.RAMUNE_BASE_TOLERANCE:
        reasons.append("upper_hand_rose")
    if remaining < -config.RAMUNE_CONTACT_GAP:
        reasons.append("upper_hand_overshot")
    row.update(
        press=float(press),
        closing=float(closing),
        remaining=float(remaining),
        base_dx=float(base_dx),
        base_dy=float(base_dy),
        press_enough=bool(press >= config.RAMUNE_MIN_PRESS),
        closing_enough=bool(closing >= config.RAMUNE_MIN_PRESS),
        contact=bool(abs(remaining) <= config.RAMUNE_CONTACT_GAP),
    )
    return row


def replay(
    points: np.ndarray, fps: float, aspect: float, mode: str
) -> tuple[list, list]:
    coordinator = RecognitionCoordinator(ramune_detector=mode, source_fps=fps)
    predictions, diagnostics = [], []
    for i, frame in enumerate(points):
        now = i / fps
        probe = (
            ramune_probe(coordinator.ramune, frame, now)
            if isinstance(coordinator.ramune, RamuneAnalyzer)
            else {}
        )
        relaxing = coordinator.relaxing
        previous = relaxing._previous
        previous_time, previous_scale = relaxing._last_time, relaxing._scale
        result = coordinator.process(objects(frame), now, i, aspect_ratio=aspect)
        predictions.append(
            dict(
                frame=i,
                seconds=now,
                gesture=result["current"]["gesture"],
                events=list(result["occurrences"]),
                ramune_state=result["ramune_state"],
            )
        )
        detail = dict(
            frame=i,
            ramune=probe,
            still_seconds=relaxing.still_seconds,
            motion_speed=relaxing.motion_speed,
            fastest_joint=None,
        )
        probe["after"] = result["ramune_state"]
        if isinstance(coordinator.ramune, LearnedRamuneAnalyzer):
            model = coordinator.ramune
            probe.update(
                gate=model.gate,
                action=model.metadata["action_labels"][model.action],
                phase=model.metadata["phase_labels"][model.phase],
            )
        if (
            relaxing.motion_speed is not None
            and previous is not None
            and previous_time is not None
        ):
            indices = np.asarray(config.RELAXING_LANDMARKS)
            current = frame[indices, :2] * [aspect, 1]
            distances = np.linalg.norm(current - previous, axis=1)
            assert relaxing._visible is not None
            distances[~relaxing._visible] = -1
            fastest = int(distances.argmax())
            speed = distances[fastest] / previous_scale / (now - previous_time)
            if not np.isclose(speed, relaxing.motion_speed):
                raise ValueError("Stillness diagnostic differs from runtime")
            detail["fastest_joint"] = NAMES[int(indices[fastest])]
            detail["fastest_index"] = int(indices[fastest])
        diagnostics.append(detail)
    return predictions, diagnostics


def diagnostic_summary(intervals: list[dict], diagnostics: list[dict]) -> list[dict]:
    rows = []
    for action in intervals:
        if action["track"] != "action" or action["label"] not in ("RAMUNE", "RELAXING"):
            continue
        selected = diagnostics[action["start_frame"] : action["end_frame"] + 1]
        row = dict(
            label=action["label"],
            start_frame=action["start_frame"],
            end_frame=action["end_frame"],
        )
        if action["label"] == "RAMUNE":
            resets = [
                dict(frame=d["frame"], **d["ramune"])
                for d in selected
                if d["ramune"].get("before") in ("FORMING", "READY")
                and d["ramune"]["after"] == "IDLE"
            ]
            ready = [d["ramune"] for d in selected if "press" in d["ramune"]]
            row.update(
                resets=resets,
                ready_frames=len(ready),
                ready_condition_counts={
                    k: sum(r[k] for r in ready)
                    for k in ("press_enough", "closing_enough", "contact")
                },
                ready_press_max=max((r["press"] for r in ready), default=None),
                learned_action=dict(
                    Counter(
                        d["ramune"]["action"]
                        for d in selected
                        if "action" in d["ramune"]
                    )
                ),
                learned_phase=dict(
                    Counter(
                        d["ramune"]["phase"] for d in selected if "phase" in d["ramune"]
                    )
                ),
                learned_gate=dict(
                    Counter(
                        d["ramune"]["gate"] for d in selected if "gate" in d["ramune"]
                    )
                ),
            )
        else:
            excess = [
                d
                for d in selected
                if d["motion_speed"] is not None
                and d["motion_speed"] > config.RELAXING_MAX_SPEED
            ]
            row.update(
                max_still_seconds=max(d["still_seconds"] for d in selected),
                speed_excess_frames=len(excess),
                total_frames=len(selected),
                fastest_joints=dict(Counter(d["fastest_joint"] for d in excess)),
            )
        rows.append(row)
    return rows


def compare(rows: list[dict]) -> dict:
    summary = {}
    for profile in sorted({r["profile"] for r in rows}):
        chosen = [r for r in rows if r["profile"] == profile and r["metrics"]["trials"]]
        cameras = {}
        for camera in (1, 2):
            c = [r for r in chosen if r["camera"] == camera]
            events = Counter()
            hits = Counter()
            frames = sum(r["frames"] for r in c)
            for row in c:
                events.update(row["metrics"]["unmatched_events"])
                for trial in row["metrics"]["trials"]:
                    hits[trial["label"]] += trial["detected"]
            cameras[camera] = dict(
                hits=dict(hits),
                unmatched_events=dict(events),
                pose_fraction=sum(r["pose_fraction"] * r["frames"] for r in c) / frames,
            )
        summary[profile] = cameras
    return summary


def make_sheet(
    source: Path,
    points: np.ndarray,
    predictions: list,
    diagnostics: list,
    intervals: list,
    area: tuple,
    destination: Path,
) -> None:
    actions = [x for x in intervals if x["track"] == "action"]
    if not actions:
        return
    start, end = actions[0]["start_frame"], actions[0]["end_frame"]
    frames = [start, (start + end) // 2, end]
    opened = [
        x for x in intervals if x["track"] == "ramune_phase" and x["label"] == "OPENED"
    ]
    if opened:
        frames[1] = (opened[0]["start_frame"] + opened[0]["end_frame"]) // 2
    cap = cv2.VideoCapture(str(source))
    panels = []
    try:
        for i in frames:
            cap.set(cv2.CAP_PROP_POS_FRAMES, i)
            ok, image = cap.read()
            if not ok:
                raise ValueError("Unable to render diagnostic frame")
            image = cv2.resize(image, (640, 360))
            p = points[i]
            for a, b in config.POSE_CONNECTIONS:
                if min(p[a, 2], p[b, 2]) > 0.5 and np.all(
                    (p[[a, b], :2] >= 0) & (p[[a, b], :2] <= 1)
                ):
                    xy = (p[[a, b], :2] * [640, 360]).astype(int)
                    cv2.line(image, tuple(xy[0]), tuple(xy[1]), (0, 255, 0), 2)
            for j in config.RELAXING_LANDMARKS:
                x, y, visibility = p[j]
                if visibility > 0.5 and 0 <= x <= 1 and 0 <= y <= 1:
                    xy = (int(x * 640), int(y * 360))
                    cv2.circle(image, xy, 4, (0, 255, 255), -1)
                    cv2.putText(
                        image, str(j), xy, cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 255), 1
                    )
            x1, y1, x2, y2 = area
            cv2.rectangle(
                image,
                (int(x1 * 640), int(y1 * 360)),
                (int(x2 * 640) - 1, int(y2 * 360) - 1),
                (255, 180, 0),
                2,
            )
            header = np.zeros((75, 640, 3), dtype=np.uint8)
            text = [
                f"{source.parent.name[-6:]} {source.stem} frame={i}",
                f"gesture={predictions[i]['gesture']} ramune={predictions[i]['ramune_state']}",
                f"fastest={diagnostics[i]['fastest_joint']} still={diagnostics[i]['still_seconds']:.2f}s",
            ]
            for line, value in enumerate(text):
                cv2.putText(
                    header,
                    value,
                    (8, 19 + line * 24),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.48,
                    (255, 255, 255),
                    1,
                )
            panels.append(np.vstack([header, image]))
    finally:
        cap.release()
    if not cv2.imwrite(str(destination), np.hstack(panels)):
        raise ValueError("Unable to save diagnostic sheet")


def main() -> None:
    baseline_path = ROOT / "shared/results/0928-multicam-results.json"
    baseline = json.loads(baseline_path.read_text())
    for name, expected in baseline["runtime_sha256"].items():
        if digest(ROOT / "src/gesture_detection" / name) != expected:
            raise ValueError(f"Runtime changed since baseline: {name}")
    output = ROOT / "shared/results/0928-multicam-followup"
    output.mkdir(parents=True, exist_ok=True)
    rows, findings = [], []
    for base in baseline["rows"]:
        if base["profile"] != "rules_full":
            continue
        take, camera = base["take"], base["camera"]
        stem = f"camera_{camera:02}"
        source = ROOT / "shared/videos/0928" / take / (stem + ".mp4")
        annotation_path = ROOT / "shared/annotations" / take / stem / "timeline.json"
        if digest(source) != base["video_sha256"]:
            raise ValueError("Source changed")
        annotation = (
            json.loads(annotation_path.read_text())
            if annotation_path.exists()
            else None
        )
        if annotation and digest(annotation_path) != base["annotation_sha256"]:
            raise ValueError("Annotations changed")
        intervals = annotation["intervals"] if annotation else []
        with np.load(ROOT / base["cache"]) as cache:
            raw = cache["points"]
        cap = cv2.VideoCapture(str(source))
        aspect = cap.get(cv2.CAP_PROP_FRAME_WIDTH) / cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
        fps = base["effective_fps"]
        roi_points, live_predictions = [], []
        with (
            patch.object(pose_worker, "SUBJECT_AREA", AREAS[camera]),
            patch.object(subject_selection, "SUBJECT_AREA", AREAS[camera]),
        ):
            analyzer = pose_worker.PoseAnalyzer(
                running_mode="VIDEO",
                select_subject=True,
                ramune_detector="rules",
                source_fps=fps,
            )
            try:
                for i in range(base["frames"]):
                    ok, frame = cap.read()
                    if not ok:
                        raise ValueError("Truncated source")
                    result = analyzer.process(frame, i / fps, i)
                    roi_points.append(result["landmarks"] or np.zeros((33, 3)).tolist())
                    live_predictions.append(
                        dict(
                            frame=i,
                            seconds=i / fps,
                            gesture=result["current"]["gesture"],
                            events=list(result["occurrences"]),
                            ramune_state=result["ramune_state"],
                        )
                    )
                if cap.read()[0]:
                    raise ValueError("Extra source frame")
            finally:
                analyzer.close()
                cap.release()
        for profile, points, mode in (
            ("rules_full", raw, "rules"),
            ("rules_camera_roi", np.asarray(roi_points), "rules"),
            ("learned_full", raw, "learned"),
        ):
            predictions, diagnostics = replay(points, fps, aspect, mode)
            if profile == "rules_full":
                expected = json.loads((ROOT / base["predictions"]).read_text())
                if predictions != expected:
                    raise ValueError("Cached baseline replay differs")
            elif profile == "rules_camera_roi" and predictions != live_predictions:
                raise ValueError("ROI replay differs from video inference")
            path = output / f"{take}-{stem}-{profile}"
            path.with_suffix(".json").write_text(
                json.dumps(
                    dict(predictions=predictions, diagnostics=diagnostics), indent=2
                )
                + "\n"
            )
            np.savez_compressed(path.with_suffix(".npz"), points=points)
            rows.append(
                dict(
                    take=take,
                    camera=camera,
                    profile=profile,
                    frames=len(points),
                    pose_fraction=float(np.any(points, axis=(1, 2)).mean()),
                    metrics=score(intervals, predictions, fps),
                    cache=str(path.with_suffix(".npz").relative_to(ROOT)),
                    diagnostics=str(path.with_suffix(".json").relative_to(ROOT)),
                )
            )
            findings.append(
                dict(
                    take=take,
                    camera=camera,
                    profile=profile,
                    actions=diagnostic_summary(intervals, diagnostics),
                )
            )
            if profile in ("rules_full", "rules_camera_roi"):
                make_sheet(
                    source,
                    points,
                    predictions,
                    diagnostics,
                    intervals,
                    AREAS[camera],
                    path.with_suffix(".jpg"),
                )
        print(take, stem, "baseline and ROI replay parity verified", flush=True)
    summary = compare(
        baseline["rows"] + [r for r in rows if r["profile"] != "rules_full"]
    )
    report = dict(
        baseline_sha256=digest(baseline_path),
        script_sha256=digest(Path(__file__)),
        camera_areas=AREAS,
        summary=summary,
        rows=rows,
        findings=findings,
        parity="All baseline and camera-ROI frame predictions exactly match coordinator replay.",
        limitations=[
            "Same footage, exploratory ablation; no independent validation.",
            "learned_full uses frozen full-frame poses, outside the trained mask profile.",
            "Time correction remains uniform-capture approximation.",
            "Reset conditions are measured simultaneously, not unique causal attributions.",
        ],
    )
    (ROOT / "shared/results/0928-multicam-followup-results.json").write_text(
        json.dumps(report, indent=2) + "\n"
    )
    print(json.dumps(summary, indent=2))
    for finding in findings:
        if finding["actions"]:
            print(json.dumps(finding))


if __name__ == "__main__":
    main()
