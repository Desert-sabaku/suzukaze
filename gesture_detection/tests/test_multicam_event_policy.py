from dataclasses import dataclass

import numpy as np
import pytest
from scripts.evaluate_multicam_events import shared_latch
from scripts.multicam_event_policy import AnchoredUchimizu, EventLatch, apply_gesture_policy
from scripts.multicam_temporal_metrics import temporal_score

from gesture_detection.uchimizu import UchimizuAnalyzer


@dataclass
class Point:
    x: float = 0.5
    y: float = 0.5
    visibility: float = 1.0


def pose(wrist_y: float = 0.75, body_shift: float = 0) -> list[Point]:
    points = [Point() for _ in range(33)]
    points[0].y = 0.1
    for index, x, y in ((11, 0.4, 0.4), (12, 0.6, 0.4), (23, 0.43, 0.7), (24, 0.57, 0.7)):
        points[index].x, points[index].y = x, y + body_shift
    points[15].y = points[16].y = wrist_y
    return points


def array(wrist_y=0.75):
    return np.array([(p.x, p.y, p.visibility) for p in pose(wrist_y)])


def test_anchored_scoop_rejects_torso_jitter_without_wrist_motion():
    existing = UchimizuAnalyzer(16)
    anchored = AnchoredUchimizu(16)
    old, new = [], []
    for i, shift in enumerate((0, 0.1, 0)):
        points = pose(0.7, shift)
        old.append(existing.update(points, i * 0.2))
        new.append(anchored.update(points, i * 0.2))
    assert any(old)
    assert not any(new)


@pytest.mark.parametrize("fps", [10, 30])
def test_anchored_scoop_accepts_raise_pause_release(fps):
    detector = AnchoredUchimizu(16)
    emitted = []
    for i in range(int(1.2 * fps)):
        now = i / fps
        y = 0.75 - 0.2 * min(now / 0.3, 1) if now < 0.6 else 0.55 + 0.2 * min((now - 0.6) / 0.3, 1)
        previous = detector.completed_at
        if detector.update(pose(y), now) and detector.completed_at != previous:
            emitted.append(now)
    assert len(emitted) == 1
    assert 0.6 <= emitted[0] <= 0.9


def sample(t, label="NONE", event=False):
    return dict(frame=round(t * 10), seconds=t, gesture=label, events=[label] if event else [])


@pytest.mark.parametrize("label", ["UCHIMIZU", "RAMUNE"])
def test_latch_requires_observed_release_and_accepts_second_action(label):
    gate = EventLatch()
    assert gate.update(sample(0, label, True), array(0.5))["events"] == [label]
    assert gate.update(sample(0.1), np.zeros((33, 3)))["gesture"] == label
    assert gate.update(sample(0.9, label, True), np.zeros((33, 3)))["events"] == []
    assert gate.update(sample(0.95, label), array(0.5))["gesture"] == "NONE"
    for t in (1.0, 1.1, 1.2, 1.3):
        gate.update(sample(t), array(0.75))
    assert gate.update(sample(1.4, label, True), array(0.5))["events"] == [label]


def test_large_observation_gap_does_not_count_as_neutral_duration():
    gate = EventLatch()
    gate.update(sample(0, "RAMUNE", True), array(0.5))
    gate.update(sample(1), array(0.75))
    gate.update(sample(2), array(0.75))
    assert gate.update(sample(2.1, "RAMUNE", True), array(0.5))["events"] == []


@pytest.mark.parametrize("label", ["FANNING", "RELAXING", "UCHIMIZU", "RAMUNE"])
def test_only_event_gestures_are_penalized_for_reappearance(label):
    predictions = [
        dict(
            frame=i,
            gesture=label if i in (1, 3) else "NONE",
            events=[label] if i == 1 and label in ("UCHIMIZU", "RAMUNE") else [],
        )
        for i in range(5)
    ]
    intervals = [dict(track="action", label=label, start_frame=0, end_frame=4)]
    trial = apply_gesture_policy(temporal_score(intervals, predictions, 10))["trials"][0]
    assert trial["detected"]
    assert trial["accepted"] == (label in ("FANNING", "RELAXING"))


def test_state_gestures_are_not_latched():
    gate = EventLatch()
    rows = [sample(0, "RELAXING"), sample(0.1), sample(0.2, "RELAXING")]
    assert [gate.update(row, array(0.75)) for row in rows] == rows


@pytest.mark.parametrize("label", ["UCHIMIZU", "RAMUNE"])
def test_active_hand_can_rearm_when_inactive_hand_is_occluded(label):
    gate = EventLatch(active_hand_release=True)
    gate.update(sample(0, label, True), array(0.5), {label: 16})
    neutral = array(0.75)
    neutral[15, 2] = 0
    for t in (1.0, 1.1, 1.2, 1.3):
        gate.update(sample(t), neutral)
    assert gate.update(sample(1.4, label, True), array(0.5), {label: 16})["events"] == [label]


def test_lowering_only_inactive_hand_does_not_rearm():
    gate = EventLatch(active_hand_release=True)
    gate.update(sample(0, "RAMUNE", True), array(0.5), {"RAMUNE": 16})
    neutral = array(0.5)
    neutral[15, 1] = 0.75
    for t in (1.0, 1.1, 1.2, 1.3):
        gate.update(sample(t), neutral)
    assert gate.update(sample(1.4, "RAMUNE", True), array(0.5), {"RAMUNE": 16})["events"] == []


def test_shared_release_can_use_other_view_without_future_frames():
    first_view = np.stack([array(0.5) for _ in range(30)])
    first_view[10:15] = array(0.75)
    absent = np.zeros_like(first_view)
    predictions = [
        dict(
            frame=i,
            seconds=i / 30,
            gesture="RAMUNE" if i in (0, 24, 60) else "NONE",
            events=["RAMUNE"] if i in (0, 24, 60) else [],
        )
        for i in range(90)
    ]
    evidence = [[], [dict(seconds=i / 30, wrists={"RAMUNE": 16}) for i in (0, 24, 60)]]
    result, _ = shared_latch(predictions, [(first_view, 10), (absent, 10)], evidence)
    assert [p["frame"] for p in result if p["events"]] == [0, 60]


def test_fresh_setup_rejects_late_report_of_old_action_after_release():
    gate = EventLatch(active_hand_release=True, require_new_setup=True)
    gate.update(
        sample(0, "UCHIMIZU", True), array(0.5), {"UCHIMIZU": 16}, event_setups={"UCHIMIZU": -0.2}
    )
    for t in (0.5, 0.6, 0.7, 0.8):
        gate.update(sample(t), array(0.75))
    late = gate.update(
        sample(0.9, "UCHIMIZU", True), array(0.5), {"UCHIMIZU": 16}, event_setups={"UCHIMIZU": -0.1}
    )
    assert late["events"] == []
    fresh = gate.update(
        sample(1.4, "UCHIMIZU", True), array(0.5), {"UCHIMIZU": 16}, event_setups={"UCHIMIZU": 1.0}
    )
    assert fresh["events"] == ["UCHIMIZU"]
