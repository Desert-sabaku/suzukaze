from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import pytest
from gesture_detection.pose_worker import PoseAnalyzer


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
    with patch("gesture_detection.pose_worker.time.monotonic") as clock:
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
    with patch("gesture_detection.pose_worker.time.monotonic") as clock:
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
