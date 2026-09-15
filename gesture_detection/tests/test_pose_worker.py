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
        points[index].x, points[index].y = x, y
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
    with patch("modules.pose_worker.time.monotonic") as clock:
        for frame in range(90):
            clock.return_value = frame / 30
            for index in wrist_indices:
                points[index].y = 0.22 + 0.04 * np.sin(2 * np.pi * 2 * frame / 30)
            analyzer._update_gesture_scores(points)
    assert analyzer.selected_action == "FANNING"


@pytest.mark.parametrize("wrist_index", [15, 16])
def test_uchimizu_with_either_hand(analyzer, wrist_index):
    points = landmarks()
    points[31 - wrist_index].visibility = 0
    with patch("modules.pose_worker.time.monotonic") as clock:
        for frame, y in enumerate([0.8, 0.8, 0.8, 0.8, 0.6, 0.7]):
            clock.return_value = frame / 30
            points[wrist_index].y = y
            analyzer._update_gesture_scores(points)
    assert analyzer.selected_action == "UCHIMIZU"


def test_losing_one_hand_only_resets_its_history(analyzer):
    points = landmarks()
    analyzer._update_gesture_scores(points)
    points[15].visibility = 0
    analyzer._update_gesture_scores(points)
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
    # Include a brief pass through the upper torso and a lingering FFT score.
    trajectory = [0.8] * 4 + [0.6, 0.7] + [0.45] * 4 + [0.8] * 60
    with (
        patch("modules.pose_worker.time.monotonic") as clock,
        patch("modules.pose_worker.HandGestureAnalyzer._calculate_fanning_score", return_value=0.9),
    ):
        for frame, y in enumerate(trajectory):
            clock.return_value = frame / 30
            points[wrist_index].y = y
            analyzer._update_gesture_scores(points)
            actions.append(analyzer.selected_action)
    assert "UCHIMIZU" in actions
    assert "FANNING" not in actions
    assert actions[-1] == "NONE"


@pytest.mark.parametrize("wrist_index", [15, 16])
def test_fanning_after_uchimizu_is_still_detected(analyzer, wrist_index):
    points = landmarks()
    points[31 - wrist_index].visibility = 0
    with patch("modules.pose_worker.time.monotonic") as clock:
        for frame in range(150):
            clock.return_value = frame / 30
            points[wrist_index].y = (
                [0.8, 0.8, 0.8, 0.8, 0.6, 0.7][frame]
                if frame < 6
                else 0.45 + 0.04 * np.sin(2 * np.pi * 2 * frame / 30)
            )
            analyzer._update_gesture_scores(points)
    assert analyzer.selected_action == "FANNING"


def test_lowering_hand_clears_fanning_and_position_timer(analyzer):
    points = landmarks()
    points[16].visibility = 0
    with patch("modules.pose_worker.time.monotonic") as clock:
        for frame in range(90):
            clock.return_value = frame / 30
            points[15].y = 0.22 + 0.04 * np.sin(2 * np.pi * 2 * frame / 30)
            analyzer._update_gesture_scores(points)
        assert analyzer.selected_action == "FANNING"
        clock.return_value = 3.0
        points[15].y = 0.8
        analyzer._update_gesture_scores(points)
    assert analyzer.selected_action != "FANNING"
    assert analyzer.hands[0].fanning_score == 0.0
    assert analyzer.hands[0].fanning_position_since is None


def test_lost_hand_must_reestablish_fanning_position(analyzer):
    points = landmarks()
    points[16].visibility = 0
    points[15].y = 0.22
    with patch("modules.pose_worker.time.monotonic", return_value=1.0):
        analyzer._update_gesture_scores(points)
    assert analyzer.hands[0].fanning_position_since == 1.0
    points[15].visibility = 0
    analyzer._update_gesture_scores(points)
    assert analyzer.hands[0].fanning_position_since is None
    points[15].visibility = 1
    with (
        patch("modules.pose_worker.time.monotonic", return_value=2.0),
        patch(
            "modules.pose_worker.HandGestureAnalyzer._calculate_fanning_score",
            return_value=0.9,
        ),
    ):
        analyzer._update_gesture_scores(points)
    assert analyzer.hands[0].fanning_position_since == 2.0
    assert analyzer.hands[0].fanning_score == 0.0
    assert analyzer.selected_action != "FANNING"

    with (
        patch(
            "modules.pose_worker.time.monotonic",
            return_value=2.0 + FANNING_POSITION_DWELL_SECONDS / 2,
        ),
        patch(
            "modules.pose_worker.HandGestureAnalyzer._calculate_fanning_score",
            return_value=0.9,
        ),
    ):
        analyzer._update_gesture_scores(points)
    assert analyzer.fanning_score == 0.0
    assert analyzer.selected_action != "FANNING"
