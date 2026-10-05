from copy import deepcopy
from unittest.mock import patch

import numpy as np
import pytest

from gesture_detection.gesture_types import Phase
from gesture_detection.recognition import RecognitionCoordinator
from gesture_detection.rendering import status_messages
from test_pose_worker import landmarks


def test_recognition_without_inference_preserves_snapshot_and_resets_on_loss():
    coordinator = RecognitionCoordinator()
    points = landmarks()
    points[16].visibility = 0
    result = coordinator.process([], 0.0, 0, aspect_ratio=1.0)
    for frame_id, y in enumerate([0.8, 0.8, 0.8, 0.8, 0.6, 0.7]):
        points[15].y = y
        result = coordinator.process(points, frame_id / 30, frame_id, aspect_ratio=1.0)
    assert result.get("current") == {"gesture": "UCHIMIZU", "tracking": True}
    saved = deepcopy(result)
    lost = coordinator.process([], 1.0, 30, aspect_ratio=1.0)
    assert lost.get("current") == {"gesture": "NONE", "tracking": False}
    assert lost.get("timestamp") == 1.0
    assert lost.get("frame_id") == 30
    assert lost.get("ramune_state") == lost.get("uchimizu_state") == "IDLE"
    assert all(not hand.wrist_y_history for hand in coordinator.hands)
    assert result == saved
    assert "messages" not in result


def test_current_includes_relaxing_and_instances_do_not_share_state():
    first = RecognitionCoordinator()
    second = RecognitionCoordinator()
    points = landmarks()
    with patch.object(first.relaxing, "update", return_value=True):
        result = first.process(points, 0.0, 0, aspect_ratio=1.5)
    assert result.get("current") == {"gesture": "RELAXING", "tracking": True}
    assert not second.relaxing_state
    assert all(not hand.wrist_y_history for hand in second.hands)
    lost = first.process([], 0.1, 1, aspect_ratio=1.5)
    assert not lost["relaxing_state"]


def test_overlay_formats_diagnostics_without_mutating_snapshot():
    result = RecognitionCoordinator().process([], 0.0, 0, aspect_ratio=1.0)
    saved = deepcopy(result)
    messages = status_messages(result)
    assert [message[0] for message in messages][:3] == [
        "Fanning score: 0.000",
        "Uchimizu score: 0.000",
        "Uchimizu state: IDLE",
    ]
    assert messages[-1][0].startswith("Relaxing: OFF")
    assert result == saved


def test_uchimizu_occurrence_is_a_single_pulse_during_feedback():
    coordinator = RecognitionCoordinator()
    points = landmarks()
    points[16].visibility = 0
    events = []
    actions = []
    for frame_id, y in enumerate([0.8] * 4 + [0.6, 0.7] + [0.7] * 5):
        points[15].y = y
        result = coordinator.process(points, frame_id / 30, frame_id, aspect_ratio=1.0)
        events.extend(result.get("occurrences", ()))
        actions.append(result["selected_action"])
    assert events == ["UCHIMIZU"]
    assert actions.count("UCHIMIZU") > 1


def test_ramune_occurrence_is_not_reissued_during_hold():
    coordinator = RecognitionCoordinator()
    points = landmarks()
    points[15].y, points[16].y = 0.6, 0.5
    events = []
    result = coordinator.process([], 0.0, 0, aspect_ratio=1.0)
    for frame_id, now in enumerate([0.0, 0.1, 0.3, 0.4, 0.5, 0.6]):
        if now >= 0.4:
            points[16].y = 0.58
        result = coordinator.process(points, now, frame_id, aspect_ratio=1.0)
        events.extend(result.get("occurrences", ()))
    assert events == ["RAMUNE"]
    assert result["selected_action"] == "RAMUNE"


@pytest.mark.parametrize("profile", ["default", "multicam"])
@pytest.mark.parametrize("wrist", [15, 16])
def test_scoop_survives_incidental_ramune_candidate(profile, wrist):
    coordinator = RecognitionCoordinator(profile=profile, ramune_detector="rules")
    points = landmarks()
    # Both hands are visible, separated by less than the widened Ramune
    # alignment tolerance. The resting hand is not holding a bottle.
    points[31 - wrist].x, points[31 - wrist].y = 0.43, 0.5
    points[wrist].x = 0.62
    states = []
    events = []
    actions = []
    for frame, y in enumerate([0.62, 0.60, 0.58, 0.56, 0.54, 0.54, 0.60]):
        points[wrist].y = y
        result = coordinator.process(points, frame / 10, frame, aspect_ratio=1.0)
        states.append(result.get("uchimizu_state"))
        events.extend(result.get("occurrences", ()))
        actions.append(result["selected_action"])
    assert Phase.READY in states
    assert events == ["UCHIMIZU"]
    assert "FANNING" not in actions
    assert "RAMUNE" not in actions


@pytest.mark.parametrize("profile", ["default", "multicam"])
@pytest.mark.parametrize("wrist", [15, 16])
def test_gentle_fanning_starts_before_three_reversals(profile, wrist):
    coordinator = RecognitionCoordinator(ramune_detector="rules", profile=profile)
    points = landmarks()
    points[31 - wrist].visibility = 0
    actions = []
    # A small chest-level oscillation should be recognized on its first
    # cycle, using the real FFT score rather than a mocked high score.
    for frame in range(25):
        now = frame / 30
        points[wrist].y = 0.48 + 0.02 * np.sin(2 * np.pi * 1.5 * now)
        result = coordinator.process(points, now, frame, aspect_ratio=1.0)
        actions.append(result["selected_action"])
    hand = coordinator.hands[wrist - 15]
    assert not hand._has_repeated_fanning()
    assert "FANNING" in actions
    assert "UCHIMIZU" not in actions
