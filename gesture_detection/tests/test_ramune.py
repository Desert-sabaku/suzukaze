from dataclasses import dataclass

import pytest

from gesture_detection.config import RAMUNE_PRESS_TIMEOUT
from gesture_detection.ramune import FollowingRamuneAnalyzer, RamuneAnalyzer


@dataclass
class Point:
    x: float = 0.5
    y: float = 0.5
    visibility: float = 1.0


def points(base_index=15):
    result = [Point() for _ in range(33)]
    result[11].x, result[12].x = 0.3, 0.7
    result[11].y = result[12].y = 0.3
    result[23].y = result[24].y = 0.85
    result[base_index].y = 0.65
    result[31 - base_index].y = 0.45
    return result


def prepare(analyzer, landmarks):
    for now in (0.0, 0.1, 0.3):
        assert not analyzer.update(landmarks, now)
    assert analyzer.state == "READY"


@pytest.mark.parametrize("base_index", [15, 16])
def test_press_with_either_hand_and_require_release(base_index):
    analyzer = RamuneAnalyzer()
    landmarks = points(base_index)
    prepare(analyzer, landmarks)
    landmarks[31 - base_index].y = 0.61
    assert analyzer.update(landmarks, 0.4)
    for now in (0.7, 1.0):
        assert analyzer.update(landmarks, now)
    for now in (1.3, 1.6):
        assert not analyzer.update(landmarks, now)
    landmarks[31 - base_index].y = 0.45
    for now in (1.7, 1.8, 2.1):
        assert not analyzer.update(landmarks, now)
    landmarks[31 - base_index].y = 0.61
    assert analyzer.update(landmarks, 2.2)


@pytest.mark.parametrize("failure", ["both_down", "sideways", "lost", "gap", "up", "timeout"])
def test_invalid_press(failure):
    analyzer = RamuneAnalyzer()
    landmarks = points()
    prepare(analyzer, landmarks)
    now = 0.4
    landmarks[16].y = 0.61
    if failure == "both_down":
        landmarks[15].y += 0.16
    elif failure == "sideways":
        landmarks[16].x += 0.3
    elif failure == "lost":
        landmarks[15].visibility = 0.0
    elif failure == "gap":
        now = 1.0
    elif failure == "up":
        landmarks[16].y = 0.0  # Above even the post-preparation windup gap.
    elif failure == "timeout":
        landmarks[16].y = 0.45
        deadline = 0.3 + RAMUNE_PRESS_TIMEOUT
        t = 0.55
        while t < deadline:
            assert not analyzer.update(landmarks, t)
            t += 0.25
        landmarks[16].y = 0.61
        now = deadline + 0.1
    assert not analyzer.update(landmarks, now)
    assert analyzer.state == ("READY" if failure in {"sideways", "both_down"} else "IDLE")


def test_contact_without_preparation_does_not_open():
    analyzer = RamuneAnalyzer()
    landmarks = points()
    landmarks[16].y = 0.64
    for now in (0.0, 0.1, 0.4):
        assert not analyzer.update(landmarks, now)


def test_press_before_dwell_does_not_open():
    analyzer = RamuneAnalyzer()
    landmarks = points()
    analyzer.update(landmarks, 0.0)
    landmarks[16].y = 0.61
    assert not analyzer.update(landmarks, 0.1)


def test_missing_pose_resets_preparation():
    analyzer = RamuneAnalyzer()
    prepare(analyzer, points())
    assert not analyzer.update([], 0.4)
    assert analyzer.state == "IDLE"


@pytest.mark.parametrize("base_index", [15, 16])
@pytest.mark.parametrize("drift_during_preparation", [False, True])
def test_hand_landmark_drift_and_offset_contact_are_allowed(base_index, drift_during_preparation):
    analyzer = RamuneAnalyzer()
    landmarks = points(base_index)
    upper_index = 31 - base_index
    assert not analyzer.update(landmarks, 0.0)
    if drift_during_preparation:
        landmarks[base_index].x += 0.14
        landmarks[base_index].y += 0.08
        landmarks[upper_index].x -= 0.04
    for now in (0.1, 0.3):
        assert not analyzer.update(landmarks, now)
    assert analyzer.state == "READY"
    landmarks[base_index].x = 0.64
    landmarks[base_index].y = 0.73
    landmarks[upper_index].x = 0.46
    # Hands need not coincide: the final vertical offset is 0.25 shoulder widths.
    landmarks[upper_index].y = 0.63 if drift_during_preparation else 0.66
    assert analyzer.update(landmarks, 0.4)


@pytest.mark.parametrize("base_index", [15, 16])
def test_nearly_shared_downward_motion_does_not_count_as_press(base_index):
    analyzer = RamuneAnalyzer()
    landmarks = points(base_index)
    upper_index = 31 - base_index
    landmarks[upper_index].y = 0.526
    prepare(analyzer, landmarks)
    # Both move within the relaxed base tolerance and finish near each other.
    # The upper hand descends far enough, but hardly closes the relative gap.
    landmarks[base_index].y += 0.104
    landmarks[upper_index].y += 0.124
    assert not analyzer.update(landmarks, 0.4)
    assert analyzer.state == "READY"


def test_lower_hand_rising_without_upper_hand_press_does_not_open():
    analyzer = RamuneAnalyzer()
    landmarks = points()
    prepare(analyzer, landmarks)
    landmarks[15].y -= 0.11
    assert not analyzer.update(landmarks, 0.4)
    assert analyzer.state == "READY"


@pytest.mark.parametrize("analyzer_type", [RamuneAnalyzer, FollowingRamuneAnalyzer])
@pytest.mark.parametrize("base_index", [15, 16])
@pytest.mark.parametrize("direction", [-1, 1])
def test_wider_upper_hand_preparation_requires_alignment_before_opening(
    analyzer_type, base_index, direction
):
    analyzer = analyzer_type()
    landmarks = points(base_index)
    upper_index = 31 - base_index
    # 0.9 shoulder widths is outside the old preparation band of 0.6.
    landmarks[upper_index].x += direction * 0.36
    prepare(analyzer, landmarks)
    assert not analyzer.update(landmarks, 0.4)
    assert analyzer.state == "READY"
    landmarks[upper_index].y = 0.61
    assert not analyzer.update(landmarks, 0.5)
    assert analyzer.state == "READY"
    landmarks[upper_index].x = landmarks[base_index].x
    assert analyzer.update(landmarks, 0.6)


@pytest.mark.parametrize("analyzer_type", [RamuneAnalyzer, FollowingRamuneAnalyzer])
def test_preparation_outside_wider_band_is_rejected(analyzer_type):
    analyzer = analyzer_type()
    landmarks = points()
    landmarks[16].x += 0.41  # More than one shoulder width.
    for now in (0.0, 0.1, 0.3):
        assert not analyzer.update(landmarks, now)
    assert analyzer.state == "IDLE"


def test_multicam_reference_follows_raised_hand_inside_wider_preparation_band():
    analyzer = FollowingRamuneAnalyzer()
    landmarks = points()
    landmarks[16].x += 0.36
    prepare(analyzer, landmarks)
    landmarks[16].y -= 0.05
    assert not analyzer.update(landmarks, 0.4)
    assert analyzer.upper_y == pytest.approx(landmarks[16].y)
    landmarks[16].x = landmarks[15].x
    landmarks[16].y = 0.61
    assert analyzer.update(landmarks, 0.5)


@pytest.mark.parametrize("analyzer_type", [RamuneAnalyzer, FollowingRamuneAnalyzer])
@pytest.mark.parametrize("offset,opens", [(-0.5, True), (0.0, True), (0.1, False)])
def test_press_can_wait_until_configured_deadline(analyzer_type, offset, opens):
    analyzer = analyzer_type()
    landmarks = points()
    prepare(analyzer, landmarks)
    press_at = 0.3 + RAMUNE_PRESS_TIMEOUT + offset
    now = 0.55
    # Keep tracking continuously: a long missing-frame gap must still reset.
    while now < press_at:
        assert not analyzer.update(landmarks, now)
        assert analyzer.state == "READY"
        now += 0.25
    landmarks[16].y = 0.61
    assert analyzer.update(landmarks, press_at) is opens
    assert analyzer.state == ("OPENED" if opens else "IDLE")


@pytest.mark.parametrize("analyzer_type", [RamuneAnalyzer, FollowingRamuneAnalyzer])
def test_gradual_raise_keeps_preparation_and_allows_delayed_press(analyzer_type):
    analyzer = analyzer_type()
    landmarks = points()
    prepare(analyzer, landmarks)
    for now, upper_y in ((0.4, 0.40), (0.5, 0.35), (0.6, 0.30)):
        landmarks[16].y = upper_y
        assert not analyzer.update(landmarks, now)
        assert analyzer.state == "READY"
    assert analyzer.upper_y == pytest.approx(0.30)
    assert analyzer.since == pytest.approx(0.6)
    assert analyzer.setup_started_at == 0.0
    press_at = 0.6 + RAMUNE_PRESS_TIMEOUT - 0.1
    now = 0.85
    while now < press_at:
        assert not analyzer.update(landmarks, now)
        assert analyzer.state == "READY"
        now += 0.25
    landmarks[16].y = 0.61
    assert analyzer.update(landmarks, press_at)


@pytest.mark.parametrize("analyzer_type", [RamuneAnalyzer, FollowingRamuneAnalyzer])
def test_raising_after_deadline_does_not_revive_expired_preparation(analyzer_type):
    analyzer = analyzer_type()
    landmarks = points()
    prepare(analyzer, landmarks)
    deadline = 0.3 + RAMUNE_PRESS_TIMEOUT
    now = 0.55
    while now < deadline:
        assert not analyzer.update(landmarks, now)
        now += 0.25
    landmarks[16].y = 0.40
    assert not analyzer.update(landmarks, deadline + 0.1)
    assert analyzer.state == "IDLE"


@pytest.mark.parametrize("analyzer_type", [RamuneAnalyzer, FollowingRamuneAnalyzer])
@pytest.mark.parametrize("base_index", [15, 16])
@pytest.mark.parametrize("direction", [-1, 1])
@pytest.mark.parametrize("vertical", [-0.14, 0.16])
def test_lower_hand_drift_preserves_preparation_and_allows_relative_press(
    analyzer_type, base_index, direction, vertical
):
    analyzer = analyzer_type()
    landmarks = points(base_index)
    upper_index = 31 - base_index
    landmarks[upper_index].y = 0.30
    prepare(analyzer, landmarks)
    landmarks[base_index].x += direction * 0.26
    landmarks[base_index].y += vertical
    assert not analyzer.update(landmarks, 0.4)
    assert analyzer.state == "READY"
    landmarks[upper_index].x = landmarks[base_index].x
    landmarks[upper_index].y = landmarks[base_index].y - 0.04
    assert analyzer.update(landmarks, 0.5)


@pytest.mark.parametrize("analyzer_type", [RamuneAnalyzer, FollowingRamuneAnalyzer])
def test_lower_hand_drift_during_forming_is_allowed(analyzer_type):
    analyzer = analyzer_type()
    landmarks = points()
    assert not analyzer.update(landmarks, 0.0)
    for index in (15, 16):
        landmarks[index].x += 0.26
        landmarks[index].y += 0.16
    for now in (0.1, 0.3):
        assert not analyzer.update(landmarks, now)
    assert analyzer.state == "READY"
    landmarks[16].y = landmarks[15].y - 0.04
    assert analyzer.update(landmarks, 0.4)


@pytest.mark.parametrize("analyzer_type", [RamuneAnalyzer, FollowingRamuneAnalyzer])
def test_wider_lower_hand_allowance_does_not_turn_common_motion_into_press(analyzer_type):
    analyzer = analyzer_type()
    landmarks = points()
    landmarks[16].y = 0.526
    prepare(analyzer, landmarks)
    # The lower hand exceeds the old vertical tolerance. Both hands descend,
    # but their relative separation barely changes.
    landmarks[15].y += 0.16
    landmarks[16].y += 0.18
    assert not analyzer.update(landmarks, 0.4)
    assert analyzer.state == "READY"


@pytest.mark.parametrize("axis,displacement", [("x", 0.31), ("y", -0.21)])
def test_lower_hand_still_resets_outside_bounded_drift(axis, displacement):
    analyzer = RamuneAnalyzer()
    landmarks = points()
    prepare(analyzer, landmarks)
    setattr(landmarks[15], axis, getattr(landmarks[15], axis) + displacement)
    assert not analyzer.update(landmarks, 0.4)
    assert analyzer.state == "IDLE"


@pytest.mark.parametrize("analyzer_type", [RamuneAnalyzer, FollowingRamuneAnalyzer])
@pytest.mark.parametrize("base_index", [15, 16])
@pytest.mark.parametrize("duration,opens", [(0.8, True), (1.0, True), (1.1, False)])
def test_one_second_high_windup_then_press(analyzer_type, base_index, duration, opens):
    analyzer = analyzer_type()
    landmarks = points(base_index)
    prepare(analyzer, landmarks)
    upper_index = 31 - base_index
    landmarks[upper_index].y = 0.20  # 1.125 shoulder widths above the lower hand.
    assert not analyzer.update(landmarks, 0.4)
    assert analyzer.state == "READY"
    assert analyzer.windup_since == pytest.approx(0.4)
    press_at = 0.4 + duration
    now = 0.65
    while now < press_at:
        landmarks[upper_index].y = 0.15  # Continue the raise; do not restart its clock.
        assert not analyzer.update(landmarks, now)
        assert analyzer.state == "READY"
        assert analyzer.windup_since == pytest.approx(0.4)
        now += 0.25
    landmarks[upper_index].y = 0.61
    assert analyzer.update(landmarks, press_at) is opens
    assert analyzer.state == ("OPENED" if opens else "IDLE")


@pytest.mark.parametrize("analyzer_type", [RamuneAnalyzer, FollowingRamuneAnalyzer])
def test_high_hand_requires_initial_preparation(analyzer_type):
    analyzer = analyzer_type()
    landmarks = points()
    landmarks[16].y = 0.15
    for now in (0.0, 0.1, 0.3):
        assert not analyzer.update(landmarks, now)
        assert analyzer.state == "IDLE"
    landmarks[16].y = 0.61
    assert not analyzer.update(landmarks, 0.4)


def test_windup_does_not_accept_both_hands_descending_or_pause_indefinitely():
    analyzer = RamuneAnalyzer()
    landmarks = points()
    prepare(analyzer, landmarks)
    landmarks[16].y = 0.20
    assert not analyzer.update(landmarks, 0.4)
    landmarks[15].y += 0.15
    landmarks[16].y += 0.15
    assert not analyzer.update(landmarks, 0.5)
    assert analyzer.windup_since == pytest.approx(0.4)
    for now in (0.8, 1.1, 1.4):
        assert not analyzer.update(landmarks, now)
    assert not analyzer.update(landmarks, 1.5)
    assert analyzer.state == "IDLE"


def test_windup_can_transition_to_press_before_contact():
    analyzer = RamuneAnalyzer()
    landmarks = points()
    prepare(analyzer, landmarks)
    landmarks[16].y = 0.15
    assert not analyzer.update(landmarks, 0.4)
    assert not analyzer.update(landmarks, 0.7)
    landmarks[16].y = 0.30
    assert not analyzer.update(landmarks, 1.0)
    assert analyzer.state == "READY"
    assert analyzer.windup_since is None
    assert not analyzer.update(landmarks, 1.3)
    landmarks[16].y = 0.61
    assert analyzer.update(landmarks, 1.6)


@pytest.mark.parametrize("failure", ["excessive_raise", "tracking_gap", "lost_hand"])
def test_windup_still_requires_bounded_height_and_tracking(failure):
    analyzer = RamuneAnalyzer()
    landmarks = points()
    prepare(analyzer, landmarks)
    landmarks[16].y = 0.15
    assert not analyzer.update(landmarks, 0.4)
    now = 0.5
    if failure == "excessive_raise":
        landmarks[16].y = 0.04  # Just beyond 1.5 shoulder widths.
    elif failure == "tracking_gap":
        now = 1.0
    else:
        landmarks[16].visibility = 0.0
    assert not analyzer.update(landmarks, now)
    assert analyzer.state == "IDLE"
    assert analyzer.windup_since is None
