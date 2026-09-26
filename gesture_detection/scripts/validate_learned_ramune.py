"""Verify streaming application inference against the frozen research folds."""

import argparse
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np

from gesture_detection.app import FrameClock
from gesture_detection.learned_ramune import DEFAULT_MODEL, LearnedRamuneAnalyzer
from gesture_detection.pose_worker import PoseAnalyzer
from gesture_detection.recognition import RecognitionCoordinator

from .evaluate_opening_setup import STATES
from .evaluate_opening_temporal import measure
from .evaluate_timeline import ROOT, digest
from .export_ramune_model import build_bundle, load_snapshot


def objects(points: np.ndarray) -> list:
    return [SimpleNamespace(x=p[0], y=p[1], visibility=p[2]) for p in points] if points.any() else []


def verify(clips: list[dict], model_path: Path, expected: dict, *, compare_action: bool = True) -> list[dict]:
    rows = []
    for clip in clips:
        detector = LearnedRamuneAnalyzer(model_path, fps=clip["fps"])
        output, pulses, phase, action, state = [], [], [], [], []
        for i, points in enumerate(clip["points"]):
            opened = detector.update(objects(points), i / clip["fps"], aspect_ratio=clip["aspect"], frame_id=i)
            output.append(3 if opened else 0)
            phase.append(detector.phase)
            action.append(detector.action)
            state.append(STATES.index(detector.gate))
            if detector.just_opened:
                pulses.append(i)
        name = clip["name"]
        np.testing.assert_array_equal(phase, expected["phase/" + name])
        if compare_action:
            np.testing.assert_array_equal(action, expected["action/" + name])
        np.testing.assert_array_equal(output, expected["output/" + name])
        np.testing.assert_array_equal(state, expected["state/" + name])
        rows.append(dict(video=name, frames=len(output), metrics=measure(clip, np.array(output), pulses)))
        print("stream parity", name, flush=True)
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, default=ROOT / "shared/results/0924-cache/runtime-source.npz")
    parser.add_argument("--videos", nargs="*", default=[])
    parser.add_argument("--app-clock", action="store_true", help="Use video PTS via the actual application clock")
    parser.add_argument("--output", type=Path, default=ROOT / "docs/0924-runtime-validation.json")
    args = parser.parse_args()
    clips, _ = load_snapshot(args.snapshot)
    reference_path = ROOT / "docs/0924-opening-features-results.json"
    reference = json.loads(reference_path.read_text())
    action_ref = json.loads((ROOT / "docs/0924-timeline-central-results.json").read_text())
    with np.load(ROOT / reference["frame_predictions"], allow_pickle=False) as data:
        expected = {k.removeprefix("relative_position/"): data[k].copy() for k in data.files
                    if k.startswith(("relative_position/", "action/"))}
    fold_rows = []
    keys = ("history", "regularization", "classifier")
    with tempfile.TemporaryDirectory() as directory:
        for selection in reference["selections"]["relative_position"]:
            group = selection["group"]
            training = [c for c in clips if c["group"] not in (0, group)]
            testing = [c for c in clips if c["group"] == group]
            action = next(r for r in action_ref["results"]["action"]["clips"] if r["group"] == group)
            bundle = build_bundle(training, {k: selection[k] for k in keys}, {k: action[k] for k in keys})
            path = Path(directory) / f"fold{group}.npz"
            np.savez_compressed(path, **bundle)
            fold_rows.extend(verify(testing, path, expected))
        # The shipped all-curtain model has held-out predictions only on group 0.
        verify([c for c in clips if c["group"] == 0], DEFAULT_MODEL, expected)
    videos = []
    for name in args.videos:
        clip = next(c for c in clips if c["name"] == name)
        source = ROOT / "shared/videos/0924" / (name + ".mp4")
        if digest(source) != clip["video_sha256"]:
            raise ValueError("Video changed")
        cap = cv2.VideoCapture(str(source))
        analyzer = PoseAnalyzer(ramune_detector="learned", source_fps=clip["fps"])
        # Reference coordinator on frozen poses: verify the complete app result,
        # including the existing other-gesture arbitration and event pulses.
        reference_coordinator = RecognitionCoordinator(ramune_detector="learned", source_fps=clip["fps"])
        events = []
        output = []
        clock = FrameClock(is_video=True)
        try:
            for i, points in enumerate(clip["points"]):
                ok, frame = cap.read()
                if not ok:
                    raise ValueError("Truncated video")
                timestamp = clock.timestamp(cap) if args.app_clock else i / clip["fps"]
                result = analyzer.process(frame, timestamp, i)
                if not args.app_clock:
                    np.testing.assert_allclose(result["landmarks"] or np.zeros((33, 3)), points, atol=1e-6)
                reference_points = np.array(result["landmarks"]) if args.app_clock else points
                previous = reference_coordinator.process(objects(reference_points), timestamp, i, aspect_ratio=clip["aspect"])
                for key in ("current", "occurrences", "ramune_state", "selected_action"):
                    if result[key] != previous[key]:
                        raise ValueError(f"App replay differs: {name} frame {i} key {key}")
                if "RAMUNE" in result["occurrences"]:
                    events.append(i)
                output.append(3 if result["selected_action"] == "RAMUNE" else 0)
            if cap.read()[0]:
                raise ValueError("Extra video frames")
        finally:
            cap.release()
            analyzer.close()
        videos.append(dict(video=name, frames=len(clip["points"]), ramune_events=events,
                           frozen_pose_parity_checked=not args.app_clock, coordinator_parity=True,
                           metrics=measure(clip, np.array(output), events)))
        print("real video parity", name, events, flush=True)
    report = dict(
        model_sha256=digest(DEFAULT_MODEL), reference_sha256=digest(reference_path),
        snapshot_sha256=digest(args.snapshot), outer_fold_replay=fold_rows, real_videos=videos,
        video_clock="application-video-PTS" if args.app_clock else "uniform-annotation-fps",
        script_sha256=digest(Path(__file__)),
        runtime_sha256={p.name: digest(p) for p in (ROOT / "src/gesture_detection").glob("*.py")},
        note="Fold parity reproduces research, not new accuracy evidence. Shipped model trains all 12 curtain clips; group 0 alone is held out. Live camera and new motions not validated.",
    )
    args.output.write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
