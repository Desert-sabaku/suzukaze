from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import pytest
from scripts.evaluate_opening_features import feature_sets
from scripts.evaluate_opening_temporal import TemporalConfig, apply_temporal

from gesture_detection.learned_ramune import DEFAULT_MODEL, LearnedRamuneAnalyzer
from gesture_detection.pose_worker import PoseAnalyzer
from gesture_detection.recognition import RecognitionCoordinator


def objects(points):
    return [SimpleNamespace(x=p[0], y=p[1], visibility=p[2]) for p in points]


def test_streaming_features_equal_research_at_source_frame_rate():
    rng = np.random.default_rng(924)
    points = rng.random((50, 33, 3))
    points[12:16] = 0
    clip = dict(points=points, fps=29.6953, aspect=16 / 9)
    offline = feature_sets(clip)
    detector = LearnedRamuneAnalyzer(fps=clip["fps"])
    from gesture_detection.learned_ramune import current_features

    for i, point in enumerate(points):
        detector.update(objects(point), i / clip["fps"], aspect_ratio=clip["aspect"], frame_id=i)
        base, geometry = current_features(point, clip["aspect"])
        for target, family in (("action", "baseline"), ("phase", "relative_position")):
            history = detector.metadata[target]["history"]
            np.testing.assert_allclose(
                detector.features(base, geometry, target), offline[family][history][i], atol=1e-12
            )
    assert len(detector.history) <= max(detector.windows.values()) + 1


def test_streaming_temporal_output_and_pulses_equal_research_with_loss_and_rearm():
    phase = np.array([1] * 5 + [3] * 3 + [0] * 20 + [2] * 5 + [3] * 3 + [0] * 20)
    action = np.where(phase != 0, 1, 0)
    points = np.ones((len(phase), 33, 3))
    points[9:14] = 0
    expected, events = apply_temporal(
        phase, action, points, 10, TemporalConfig(0.75, 0.6, 0.3, "context", True)
    )
    detector = LearnedRamuneAnalyzer(fps=10)
    actual, pulses = [], []
    for i, (p, a) in enumerate(zip(phase, action, strict=True)):
        actual.append(3 if detector.advance(int(p), int(a), bool(points[i].any()), i / 10) else 0)
        if detector.just_opened:
            pulses.append(i)
    np.testing.assert_array_equal(actual, expected)
    assert pulses == events == [5, 33]


def test_coordinator_does_not_unlock_or_reemit_after_missing_pose():
    coordinator = RecognitionCoordinator(ramune_detector="learned", source_fps=10)
    detector = coordinator.ramune
    points = objects(np.ones((33, 3)))
    detector.gate = "ARMED"
    with patch.object(
        detector, "predict", side_effect=lambda f, target: 1 if target == "action" else 3
    ):
        first = coordinator.process(points, 0, 0, aspect_ratio=1)
        missing = coordinator.process([], 0.9, 9, aspect_ratio=1)
        again = coordinator.process(points, 1, 10, aspect_ratio=1)
    assert first["occurrences"] == ("RAMUNE",)
    assert missing["current"] == dict(gesture="NONE", tracking=False)
    assert again["occurrences"] == () and again["ramune_state"] == "WAIT_RELEASE"
    assert detector.gate == "LOCKED"


def test_dropped_frames_are_not_continuous_setup_or_release():
    detector = LearnedRamuneAnalyzer(fps=10)
    points = objects(np.ones((33, 3)))
    with patch.object(detector, "predict", side_effect=lambda f, t: 1 if t == "action" else 2):
        detector.update(points, 0, frame_id=0)
        detector.update(points, 0.4, frame_id=4)
    assert detector.gate == "WAIT_SETUP"
    detector.gate = "LOCKED"
    with patch.object(detector, "predict", return_value=0):
        detector.update(points, 0.5, frame_id=5)
        detector.update(points, 1.2, frame_id=12)
    assert detector.gate == "LOCKED"


def test_rules_remain_default_and_other_gestures_remain_available():
    from gesture_detection.ramune import RamuneAnalyzer

    assert isinstance(RecognitionCoordinator(ramune_detector="rules").ramune, RamuneAnalyzer)
    coordinator = RecognitionCoordinator(ramune_detector="learned")
    with (
        patch.object(coordinator.ramune, "predict", return_value=0),
        patch.object(coordinator.relaxing, "update", return_value=True),
    ):
        result = coordinator.process(objects(np.ones((33, 3))), 0, 0, aspect_ratio=1)
    assert result["current"]["gesture"] == "RELAXING"


@pytest.mark.parametrize("gesture", ["FANNING", "UCHIMIZU"])
def test_learned_profile_keeps_existing_hand_detectors(gesture):
    from test_pose_worker import landmarks

    coordinator = RecognitionCoordinator(ramune_detector="learned")
    points = landmarks()
    points[16].visibility = 0
    ys = (
        [0.22 + 0.04 * np.sin(2 * np.pi * 2 * i / 30) for i in range(90)]
        if gesture == "FANNING"
        else [0.8, 0.8, 0.8, 0.8, 0.6, 0.7]
    )
    with patch.object(coordinator.ramune, "predict", return_value=0):
        for i, y in enumerate(ys):
            points[15].y = y
            result = coordinator.process(points, i / 30, i, aspect_ratio=1)
    assert result["selected_action"] == gesture


def test_learned_profile_masks_every_frame_and_does_not_seed_or_mutate_input():
    with patch.object(PoseAnalyzer, "_create_landmarker"):
        analyzer = PoseAnalyzer(ramune_detector="learned", select_subject=True)
    assert analyzer.subject_selector is None
    frame = np.full((100, 100, 3), 255, dtype=np.uint8)
    analyzer.landmarker.detect_for_video.return_value = SimpleNamespace(pose_landmarks=[])
    with patch("gesture_detection.pose_worker.mp_core.Image") as image:
        analyzer.process(frame, 0, 0)
        first = image.call_args.kwargs["data"]
        analyzer.process(frame, 0.1, 1)
        second = image.call_args.kwargs["data"]
    for value in (first, second):
        assert np.all(value[:, :35] == 127) and np.all(value[:, 75:] == 127)
        assert np.all(value[:, 35:75] == 255)
    assert np.all(frame == 255)


def test_profile_errors_fail_clearly_instead_of_silent_rule_fallback(tmp_path):
    with pytest.raises(ValueError, match="VIDEO"):
        PoseAnalyzer(ramune_detector="learned", running_mode="IMAGE")
    with pytest.raises(FileNotFoundError):
        LearnedRamuneAnalyzer(Path(tmp_path / "absent.npz"))
    with np.load(DEFAULT_MODEL, allow_pickle=False) as source:
        data = {k: source[k] for k in source.files}
    data["phase_scale"] = np.zeros(110)
    path = tmp_path / "invalid.npz"
    np.savez_compressed(path, **data)
    with pytest.raises(ValueError, match="scale"):
        LearnedRamuneAnalyzer(path)


def test_timestamp_and_frame_order_are_explicit_not_a_silent_reset():
    detector = LearnedRamuneAnalyzer()
    detector.update([], 1, frame_id=1)
    with pytest.raises(ValueError, match="timestamps"):
        detector.update([], 1, frame_id=2)
    with pytest.raises(ValueError, match="frame IDs"):
        detector.update([], 2, frame_id=1)
