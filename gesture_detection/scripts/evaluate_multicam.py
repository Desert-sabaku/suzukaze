"""Replay paired recordings with an approximate wall clock and frozen detectors."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

import cv2
import numpy as np

from gesture_detection.config import POSE_MODEL_PATH
from gesture_detection.learned_ramune import DEFAULT_MODEL
from gesture_detection.pose_worker import PoseAnalyzer

ROOT = Path(__file__).resolve().parents[1]
PROFILES = ("rules_full", "rules_subject", "learned")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def score(intervals: list[dict], predictions: list[dict], fps: float) -> dict:
    """Score every annotation separately; event gestures require an occurrence."""
    actions = [x for x in intervals if x["track"] == "action"]
    trials = []
    for interval in actions:
        label = interval["label"]
        start, end = interval["start_frame"], interval["end_frame"]
        event = label in ("RAMUNE", "UCHIMIZU")
        hits = [
            p["frame"]
            for p in predictions
            if start <= p["frame"] <= end
            and (label in p["events"] if event else p["gesture"] == label)
        ]
        opened = [
            x
            for x in intervals
            if x["track"] == "ramune_phase"
            and x["label"] == "OPENED"
            and start <= x["start_frame"] <= x["end_frame"] <= end
        ]
        trials.append(
            dict(
                label=label,
                start_frame=start,
                end_frame=end,
                detected=bool(hits),
                first_response_seconds=(hits[0] - start) / fps if hits else None,
                event_count=len(hits) if event else None,
                extra_events=max(0, len(hits) - 1) if event else None,
                opened_phase_hit=(
                    any(x["start_frame"] <= f <= x["end_frame"] for x in opened for f in hits)
                    if opened
                    else None
                ),
            )
        )
    # Outside annotations is a diagnostic, not verified negative ground truth.
    outside = Counter()
    wrong = Counter()
    outside_events = Counter()
    for p in predictions:
        truth = {x["label"] for x in actions if x["start_frame"] <= p["frame"] <= x["end_frame"]}
        if p["gesture"] != "NONE" and p["gesture"] not in truth:
            (wrong if truth else outside)[p["gesture"]] += 1
        for event in p["events"]:
            if event not in truth:
                outside_events[event] += 1
    return dict(
        trials=trials,
        wrong_label_seconds={k: v / fps for k, v in wrong.items()},
        unlabelled_output_seconds={k: v / fps for k, v in outside.items()},
        unmatched_events=dict(outside_events),
    )


def summarize(rows: list[dict]) -> dict:
    result = {}
    for profile in PROFILES:
        pairs = []
        for take in sorted({r["take"] for r in rows}):
            cameras = {
                r["camera"]: r for r in rows if r["take"] == take and r["profile"] == profile
            }
            if set(cameras) != {1, 2}:
                continue
            a, b = [cameras[c]["metrics"]["trials"] for c in (1, 2)]
            if not a or [x["label"] for x in a] != [x["label"] for x in b]:
                continue
            for x, y in zip(a, b, strict=True):
                pairs.append(
                    dict(
                        take=take,
                        label=x["label"],
                        camera1=x["detected"],
                        camera2=y["detected"],
                        either=x["detected"] or y["detected"],
                        opened1=x["opened_phase_hit"],
                        opened2=y["opened_phase_hit"],
                    )
                )
        counts = {}
        for label in sorted({p["label"] for p in pairs}):
            selected = [p for p in pairs if p["label"] == label]
            counts[label] = dict(
                trials=len(selected),
                **{k: sum(p[k] for p in selected) for k in ("camera1", "camera2", "either")},
                camera2_rescues=sum(p["camera2"] and not p["camera1"] for p in selected),
                camera1_rescues=sum(p["camera1"] and not p["camera2"] for p in selected),
            )
        result[profile] = dict(counts=counts, pairs=pairs)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--videos", type=Path, default=ROOT / "shared/videos/0928")
    parser.add_argument("--annotations", type=Path, default=ROOT / "shared/annotations")
    parser.add_argument("--output", type=Path, default=ROOT / "docs/0928-multicam-results.json")
    parser.add_argument("--cache", type=Path, default=ROOT / "shared/results/0928-multicam")
    args = parser.parse_args()
    args.cache.mkdir(parents=True, exist_ok=True)
    rows, audit, sheets = [], [], []
    for session_path in sorted(args.videos.glob("*/session.json")):
        session = json.loads(session_path.read_text())
        take = session_path.parent.name
        duration = session["duration_seconds"]
        for camera in session["cameras"]:
            source = session_path.parent / camera["file"]
            annotation_path = args.annotations / take / source.stem / "timeline.json"
            annotation = (
                json.loads(annotation_path.read_text()) if annotation_path.exists() else None
            )
            video_hash = digest(source)
            if annotation and annotation["source"]["sha256"] != video_hash:
                raise ValueError(f"Annotation/video mismatch: {source}")
            cap = cv2.VideoCapture(str(source))
            frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            nominal_fps = cap.get(cv2.CAP_PROP_FPS)
            cap.release()
            if frames != camera["frames_written"] or (
                annotation and frames != annotation["source"]["total_frames"]
            ):
                raise ValueError(f"Frame count mismatch: {source}")
            fps = frames / duration
            audit.append(
                dict(
                    take=take,
                    camera=camera["camera_index"],
                    frames=frames,
                    duration=duration,
                    nominal_fps=nominal_fps,
                    effective_fps=fps,
                    annotated=annotation is not None,
                )
            )
            for profile in PROFILES:
                analyzer = PoseAnalyzer(
                    running_mode="VIDEO",
                    select_subject=profile == "rules_subject",
                    ramune_detector="learned" if profile == "learned" else "rules",
                    source_fps=fps,
                )
                cap = cv2.VideoCapture(str(source))
                predictions, points, timestamps, thumbnails = [], [], [], []
                try:
                    for i in range(frames):
                        ok, frame = cap.read()
                        if not ok:
                            raise ValueError(f"Decode stopped at {i}: {source}")
                        pts = cap.get(cv2.CAP_PROP_POS_MSEC) / 1000
                        timestamps.append(pts)
                        result = analyzer.process(frame, i / fps, i)
                        points.append(result["landmarks"] or np.zeros((33, 3)).tolist())
                        predictions.append(
                            dict(
                                frame=i,
                                seconds=i / fps,
                                gesture=result["current"]["gesture"],
                                events=list(result["occurrences"]),
                                ramune_state=result["ramune_state"],
                            )
                        )
                        if profile == "rules_full" and i in {
                            int(frames * f) for f in (0.2, 0.5, 0.8)
                        }:
                            thumb = cv2.resize(frame, (384, 216))
                            cv2.putText(
                                thumb,
                                f"{take[-6:]} cam{camera['camera_index']} {i / fps:.1f}s",
                                (5, 20),
                                cv2.FONT_HERSHEY_SIMPLEX,
                                0.5,
                                (0, 255, 255),
                                1,
                            )
                            thumbnails.append(thumb)
                    if cap.read()[0]:
                        raise ValueError(f"Extra decoded frames: {source}")
                finally:
                    cap.release()
                    analyzer.close()
                if thumbnails:
                    sheets.append(np.hstack(thumbnails))
                data = np.asarray(points)
                path = args.cache / f"{take}-{source.stem}-{profile}.npz"
                np.savez_compressed(
                    path,
                    points=data,
                    container_seconds=timestamps,
                    corrected_seconds=np.arange(frames) / fps,
                )
                prediction_path = path.with_suffix(".json")
                prediction_path.write_text(json.dumps(predictions, indent=2) + "\n")
                intervals = annotation["intervals"] if annotation else []
                row = dict(
                    take=take,
                    camera=camera["camera_index"],
                    profile=profile,
                    effective_fps=fps,
                    video_sha256=video_hash,
                    annotation_sha256=digest(annotation_path) if annotation else None,
                    frames=frames,
                    pose_fraction=float(np.any(data, axis=(1, 2)).mean()),
                    both_wrists_visible_fraction=float(
                        (data[:, [15, 16], 2] > 0.5).all(axis=1).mean()
                    ),
                    metrics=score(intervals, predictions, fps),
                    predictions=str(prediction_path.relative_to(ROOT)),
                    cache=str(path.relative_to(ROOT)),
                )
                rows.append(row)
                print(take, source.stem, profile, row["metrics"]["trials"], flush=True)
        # Keep each take's two views together; one sheet per take.
        if sheets:
            cv2.imwrite(str(args.cache / f"{take}.jpg"), np.vstack(sheets))
            sheets.clear()
    report = dict(
        recording_context={
            "os": "Windows 11",
            "recorder": "Desert-sabaku/multicam-recorder",
            "cameras": {"1": "Insta360 Link 2C (left)", "2": "Logicool HD Webcam C615 (right)"},
            "phase_explanation_ui": {"RAMUNE": False, "RELAXING": False},
            "note": "Performer reports harder conditions than intended guided operation; the effect of the missing UI has not been measured.",
        },
        clock="frame * session duration / decoded frame count; uniform capture assumed",
        profiles={
            "rules_full": "rules, full image, subject selector disabled",
            "rules_subject": "rules, production subject selector enabled",
            "learned": "frozen 0924 model, production central mask [0.35, 0.75]",
        },
        limitations=[
            "No per-frame capture timestamps; synchronization is approximate.",
            "Either-camera score is an oracle opportunity, not deployable fusion.",
            "Unlabelled frames are not verified negatives.",
            "Action hits alone do not verify event timing; OPENED scored separately.",
            "All decoded frames processed; live queue drops and latency not measured.",
        ],
        script_sha256=digest(Path(__file__)),
        pose_model_sha256=digest(POSE_MODEL_PATH),
        learned_model_sha256=digest(DEFAULT_MODEL),
        runtime_sha256={p.name: digest(p) for p in (ROOT / "src/gesture_detection").glob("*.py")},
        audit=audit,
        rows=rows,
        summary=summarize(rows),
    )
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report["summary"], indent=2))


if __name__ == "__main__":
    main()
