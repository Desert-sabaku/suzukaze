from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import pytest
from modules.config import FANNING_POSITION_DWELL_SECONDS
from modules.pose_worker import PoseAnalyzer


def landmarks():
    points = [SimpleNamespace(x=0.5, y=0.5, visibility=1.0) for _ in range(33)]
    for index, x, y in [
        (0, 0.5, 0.2),
        (11, 0.4, 0.4),
        (12, 0.6, 0.4),
        (23, 0.43, 0.7),
        (24, 0.57, 0.7),
    ]:
        points[index].x, points[index].y = (x, y)
    return points


@pytest.fixture
def analyzer():
    with patch.object(PoseAnalyzer, "_create_landmarker"):
        return PoseAnalyzer()


@pytest.mark.parametrize("wrist_indices", [(15,), (16,), (15, 16)])
def test_fanning_with_either_or_both_hands(analyzer, wrist_indices):
    points = landmarks()
    for index in (15, 16):
        points[index].visibility = float(index in wrist_indices)
    timestamp = 0.0
    for frame in range(90):
        timestamp = frame / 30
        for index in wrist_indices:
            points[index].y = 0.22 + 0.04 * np.sin(2 * np.pi * 2 * frame / 30)
        analyzer._update_gesture_scores(points, timestamp)
    assert analyzer.selected_action == "FANNING"


@pytest.mark.parametrize("wrist_index", [15, 16])
def test_uchimizu_with_either_hand(analyzer, wrist_index):
    points = landmarks()
    points[31 - wrist_index].visibility = 0
    timestamp = 0.0
    for frame, y in enumerate([0.8, 0.8, 0.8, 0.8, 0.6, 0.7]):
        timestamp = frame / 30
        points[wrist_index].y = y
        analyzer._update_gesture_scores(points, timestamp)
    assert analyzer.selected_action == "UCHIMIZU"


def test_losing_one_hand_only_resets_its_history(analyzer):
    points = landmarks()
    analyzer._update_gesture_scores(points, 0.0)
    points[15].visibility = 0
    analyzer._update_gesture_scores(points, 0.0)
    assert len(analyzer.hands[0].wrist_y_history) == 0
    assert len(analyzer.hands[1].wrist_y_history) == 2
    analyzer._reset_tracking_state()
    assert all(not hand.wrist_y_history for hand in analyzer.hands)
    assert analyzer.selected_action == "NONE"


@pytest.mark.parametrize("wrist_index", [15, 16])
def test_uchimizu_finish_does_not_become_fanning(analyzer, wrist_index):
    points = landmarks()
    points[31 - wrist_index].visibility = 0
    actions = []
    trajectory = [0.8] * 4 + [0.6, 0.7] + [0.45] * 4 + [0.8] * 60
    timestamp = 0.0
    with patch(
        "modules.pose_worker.HandGestureAnalyzer._calculate_fanning_score", return_value=0.9
    ):
        for frame, y in enumerate(trajectory):
            timestamp = frame / 30
            points[wrist_index].y = y
            analyzer._update_gesture_scores(points, timestamp)
            actions.append(analyzer.selected_action)
    assert "UCHIMIZU" in actions
    assert "FANNING" not in actions
    assert actions[-1] == "NONE"


@pytest.mark.parametrize("wrist_index", [15, 16])
def test_fanning_after_uchimizu_is_still_detected(analyzer, wrist_index):
    points = landmarks()
    points[31 - wrist_index].visibility = 0
    timestamp = 0.0
    for frame in range(150):
        timestamp = frame / 30
        points[wrist_index].y = (
            [0.8, 0.8, 0.8, 0.8, 0.6, 0.7][frame]
            if frame < 6
            else 0.45 + 0.04 * np.sin(2 * np.pi * 2 * frame / 30)
        )
        analyzer._update_gesture_scores(points, timestamp)
    assert analyzer.selected_action == "FANNING"


def test_lowering_hand_clears_fanning_and_position_timer(analyzer):
    points = landmarks()
    points[16].visibility = 0
    timestamp = 0.0
    for frame in range(90):
        timestamp = frame / 30
        points[15].y = 0.22 + 0.04 * np.sin(2 * np.pi * 2 * frame / 30)
        analyzer._update_gesture_scores(points, timestamp)
    assert analyzer.selected_action == "FANNING"
    timestamp = 3.0
    points[15].y = 0.8
    analyzer._update_gesture_scores(points, timestamp)
    assert analyzer.selected_action != "FANNING"
    assert analyzer.hands[0].fanning_score == 0.0
    assert analyzer.hands[0].fanning_position_since is None


def test_lost_hand_must_reestablish_fanning_position(analyzer):
    points = landmarks()
    points[16].visibility = 0
    points[15].y = 0.22
    timestamp = 1.0
    analyzer._update_gesture_scores(points, timestamp)
    assert analyzer.hands[0].fanning_position_since == 1.0
    points[15].visibility = 0
    analyzer._update_gesture_scores(points, timestamp)
    assert analyzer.hands[0].fanning_position_since is None
    points[15].visibility = 1
    timestamp = 2.0
    with patch(
        "modules.pose_worker.HandGestureAnalyzer._calculate_fanning_score", return_value=0.9
    ):
        analyzer._update_gesture_scores(points, timestamp)
    assert analyzer.hands[0].fanning_position_since == 2.0
    assert analyzer.hands[0].fanning_score == 0.0
    assert analyzer.selected_action != "FANNING"
    timestamp = 2.0 + FANNING_POSITION_DWELL_SECONDS / 2
    with patch(
        "modules.pose_worker.HandGestureAnalyzer._calculate_fanning_score", return_value=0.9
    ):
        analyzer._update_gesture_scores(points, timestamp)
    assert analyzer.fanning_score == 0.0
    assert analyzer.selected_action != "FANNING"


@pytest.mark.parametrize("base_index", [15, 16])
def test_ramune_takes_priority_and_resets_on_tracking_loss(analyzer, base_index):
    points = landmarks()
    points[base_index].y = 0.6
    points[31 - base_index].y = 0.5
    timestamp = 0.0
    for now in (0.0, 0.1, 0.3):
        timestamp = now
        analyzer._update_gesture_scores(points, timestamp)
        assert analyzer.selected_action == "NONE"
    points[31 - base_index].y = 0.58
    timestamp = 0.4
    analyzer._update_gesture_scores(points, timestamp)
    assert analyzer.selected_action == "RAMUNE"
    assert analyzer.uchimizu_score == 0
    assert all(not hand.wrist_y_history for hand in analyzer.hands)
    analyzer._reset_tracking_state()
    assert analyzer.ramune.state == "IDLE"
    assert analyzer.selected_action == "NONE"


@pytest.mark.parametrize("wrist_index", [15, 16])
@pytest.mark.parametrize("base_y", [0.48, 0.54, 0.56])
def test_repeated_fanning_across_torso_boundary(analyzer, wrist_index, base_y):
    points = landmarks()
    points[31 - wrist_index].visibility = 0
    actions = []
    timestamp = 0.0
    for frame in range(150):
        timestamp = frame / 30
        points[wrist_index].y = base_y + 0.04 * np.sin(2 * np.pi * 2 * frame / 30)
        analyzer._update_gesture_scores(points, timestamp)
        if frame >= 90:
            actions.append(analyzer.selected_action)
    assert set(actions) == {"FANNING"}


def test_boundary_grace_expires_when_hand_stays_low(analyzer):
    points = landmarks()
    points[16].visibility = 0
    timestamp = 0.0
    for frame in range(90):
        timestamp = frame / 30
        points[15].y = 0.48 + 0.04 * np.sin(2 * np.pi * 2 * frame / 30)
        analyzer._update_gesture_scores(points, timestamp)
    points[15].y = 0.6
    for now in (3.0, 3.15, 3.4):
        timestamp = now
        analyzer._update_gesture_scores(points, timestamp)
    assert analyzer.hands[0].fanning_position_since is None
    assert analyzer.hands[0].fanning_score == 0.0
    assert analyzer.selected_action != "FANNING"


def test_process_passes_source_timestamp_to_all_detectors(analyzer):
    points = landmarks()
    analyzer.landmarker.detect.return_value = SimpleNamespace(pose_landmarks=[points])
    with (
        patch("time.monotonic", side_effect=AssertionError("Wall clock used")),
        patch.object(analyzer.ramune, "update", return_value=False) as ramune,
        patch.object(analyzer.hands[0].uchimizu, "update", return_value=False) as left,
        patch.object(analyzer.hands[1].uchimizu, "update", return_value=False) as right,
    ):
        analyzer.process(np.zeros((4, 5, 3), dtype=np.uint8), 12.5)
    for detector in (ramune, left, right):
        detector.assert_called_once_with(points, 12.5)
    for hand in analyzer.hands:
        assert list(hand.wrist_t_history) == [12.5]


def test_worker_forwards_frame_timestamp():
    from unittest.mock import MagicMock

    from modules.pose_worker import pose_worker

    frame = np.zeros((4, 5, 3), dtype=np.uint8)
    channel = MagicMock()
    channel.get.side_effect = [(frame, 3.25), None]
    results = MagicMock()
    results.empty.return_value = True
    with patch("modules.pose_worker.PoseAnalyzer") as factory:
        pose_worker(channel, results)
    factory.return_value.process.assert_called_once_with(frame, 3.25)
    factory.return_value.close.assert_called_once()
