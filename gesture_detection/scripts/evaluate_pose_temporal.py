"""Offline tracking/interpolation experiment; interpolated points are not detections."""

import argparse
import json
from pathlib import Path

import cv2
import numpy as np
import torch
from ultralytics import YOLO

from scripts.evaluate_yolo_pose import DEFAULT_CLIPS, IMPORTANT_KEYPOINTS


def choose_person(boxes, previous):
    """Associate foreground boxes by overlap; do not switch on a single miss."""
    if not len(boxes):
        return None
    areas = np.prod(boxes[:, 2:] - boxes[:, :2], axis=1)
    candidates = np.flatnonzero(areas >= 0.08)
    if not len(candidates):
        return None
    if previous is None:
        return int(candidates[np.argmax(areas[candidates])])
    intersection = np.prod(
        np.maximum(
            0,
            np.minimum(boxes[:, 2:], previous[2:])
            - np.maximum(boxes[:, :2], previous[:2]),
        ),
        axis=1,
    )
    overlap = intersection / np.maximum(
        areas + np.prod(previous[2:] - previous[:2]) - intersection, 1e-9
    )
    best = int(candidates[np.argmax(overlap[candidates])])
    return best if overlap[best] >= 0.3 else None


def repair(points, times, segments, max_gap=0.15, tau=0.05):
    """Bracketed interpolation within one track, followed by causal EMA.

    Offline interpolation requires future observations (up to max_gap latency).
    Never extrapolate or fill a track boundary. Long gaps reset smoothing.
    """
    filled = points.copy()
    imputed = np.zeros(points.shape[:2], dtype=bool)
    for joint in range(points.shape[1]):
        valid = np.flatnonzero(np.isfinite(points[:, joint]).all(axis=1))
        for start, end in zip(valid[:-1], valid[1:], strict=True):
            if (
                end <= start + 1
                or times[end] - times[start] > max_gap
                or segments[start] != segments[end]
            ):
                continue
            weight = (times[start + 1 : end] - times[start]) / (
                times[end] - times[start]
            )
            filled[start + 1 : end, joint] = points[start, joint] + weight[:, None] * (
                points[end, joint] - points[start, joint]
            )
            imputed[start + 1 : end, joint] = True
    smooth = filled.copy()
    for i in range(1, len(times)):
        if segments[i] != segments[i - 1]:
            continue
        valid = np.isfinite(filled[i]).all(axis=1) & np.isfinite(smooth[i - 1]).all(
            axis=1
        )
        alpha = 1 - np.exp(-(times[i] - times[i - 1]) / tau)
        smooth[i, valid] = smooth[i - 1, valid] + alpha * (
            filled[i, valid] - smooth[i - 1, valid]
        )
    return filled, smooth, imputed


def summarize(points, segments):
    valid = np.isfinite(points).all(axis=2)
    adjacent = valid[1:] & valid[:-1] & (segments[1:] == segments[:-1])[:, None]
    jumps = np.linalg.norm(np.diff(points, axis=0), axis=2)[adjacent]
    return {
        "all_seven_available_ratio": float(valid.all(axis=1).mean()),
        "per_joint_available_ratio": valid.mean(axis=0).tolist(),
        "valid_adjacent_pairs": int(adjacent.sum()),
        "p95_valid_point_displacement": (
            float(np.percentile(jumps, 95)) if len(jumps) else None
        ),
    }


def evaluate(model, source, output):
    cap = cv2.VideoCapture(str(source))
    fps = cap.get(cv2.CAP_PROP_FPS)
    if not cap.isOpened() or not np.isfinite(fps) or fps <= 0:
        raise ValueError(f"Invalid source: {source}")
    raw, tracked, times, segments = [], [], [], []
    previous = None
    last_seen = -1.0
    segment = 0
    frame_id = 0
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            now = frame_id / fps
            result = model.predict(
                frame, conf=0.05, imgsz=640, device="cpu", verbose=False
            )[0]
            boxes = result.boxes.xyxyn.cpu().numpy()
            if previous is not None and now - last_seen > 0.25:
                previous = None
                segment += 1
            naive = choose_person(boxes, None)
            selected = choose_person(boxes, previous)

            def extract(person, result=result):
                points = np.full((7, 2), np.nan)
                if person is not None:
                    xy = (
                        result.keypoints.xyn[person]
                        .cpu()
                        .numpy()[list(IMPORTANT_KEYPOINTS)]
                    )
                    confidence = (
                        result.keypoints.conf[person]
                        .cpu()
                        .numpy()[list(IMPORTANT_KEYPOINTS)]
                    )
                    good = (
                        (confidence > 0.5)
                        & np.isfinite(xy).all(axis=1)
                        & ((xy > 0) & (xy < 1)).all(axis=1)
                    )
                    points[good] = xy[good]
                return points

            raw.append(extract(naive))
            tracked.append(extract(selected))
            if selected is not None:
                previous = boxes[selected]
                last_seen = now
            times.append(now)
            segments.append(segment)
            frame_id += 1
    finally:
        cap.release()
    raw, tracked, times, segments = map(np.asarray, (raw, tracked, times, segments))
    filled, smooth, imputed = repair(tracked, times, segments)
    output.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        output / f"{source.stem}.npz",
        raw=raw,
        tracked=tracked,
        filled=filled,
        smooth=smooth,
        imputed=imputed,
        times=times,
        segments=segments,
    )
    # Inspect original-frame coordinates: green observations, orange imputations.
    capture = cv2.VideoCapture(str(source))
    thumbnails = []
    for index in np.linspace(0, len(times) - 1, 12, dtype=int):
        capture.set(cv2.CAP_PROP_POS_FRAMES, int(index))
        ok, frame = capture.read()
        if not ok:
            continue
        frame = cv2.resize(frame, (480, 270))
        for joint, point in enumerate(smooth[index]):
            if np.isfinite(point).all():
                color = (0, 165, 255) if imputed[index, joint] else (0, 255, 0)
                position = tuple((point * [480, 270]).astype(int))
                cv2.circle(frame, position, 4, color, -1)
                cv2.putText(
                    frame,
                    str(IMPORTANT_KEYPOINTS[joint]),
                    position,
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.4,
                    color,
                    1,
                )
        cv2.putText(
            frame,
            f"{times[index]:.2f}s track {segments[index]}",
            (8, 22),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (0, 255, 255),
            1,
        )
        thumbnails.append(frame)
    capture.release()
    if len(thumbnails) == 12:
        cv2.imwrite(
            str(output / f"{source.stem}.jpg"),
            np.vstack([np.hstack(thumbnails[i : i + 4]) for i in range(0, 12, 4)]),
        )
    return {
        "source": source.name,
        "frames": len(times),
        "track_segments": segment + 1,
        "raw": summarize(raw, np.zeros(len(times))),
        "tracked": summarize(tracked, segments),
        "interpolated": summarize(filled, segments),
        "smoothed": summarize(smooth, segments),
        "imputed_joint_frames": int(imputed.sum()),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--sample-dir", type=Path, default=Path("sample_movies"))
    parser.add_argument("--output", type=Path, default=Path("output/pose-temporal"))
    parser.add_argument("--clip", action="append")
    parser.add_argument("--threads", type=int, default=2)
    args = parser.parse_args()
    if args.threads < 1:
        parser.error("--threads must be positive")
    torch.set_num_threads(args.threads)
    model = YOLO(str(args.model))
    report = {
        "method": {
            "confidence": 0.05,
            "joint_confidence": 0.5,
            "min_area": 0.08,
            "min_iou": 0.3,
            "track_timeout_seconds": 0.25,
            "interpolation_bracket_seconds": 0.15,
            "ema_tau_seconds": 0.05,
        },
        "limitations": "Availability is not correctness. Displacement includes real motion; smoothing lowers it by construction. Interpolation uses future frames.",
        "clips": [],
    }
    for filename in args.clip or DEFAULT_CLIPS:
        print(filename, flush=True)
        report["clips"].append(evaluate(model, args.sample_dir / filename, args.output))
        (args.output / "report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n"
        )


if __name__ == "__main__":
    main()
