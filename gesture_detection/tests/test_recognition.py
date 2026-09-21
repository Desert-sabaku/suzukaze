from copy import deepcopy
from unittest.mock import patch

from modules.recognition import RecognitionCoordinator
from modules.rendering import status_messages

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
