from pathlib import Path

import pytest
from scripts.evaluate_action_intervals import (
    RamunePoseCandidate,
    RelaxingPoseCandidate,
    aggregate,
    parse_clip_name,
    ramune_geometry,
)


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("aogi1_2-6.mp4", ("FANNING", 1, 2.0, 6.0)),
        ("ramune3_6-7.mp4", ("RAMUNE", 3, 6.0, 7.0)),
        ("uchimizu2_3-4.mp4", ("SPRINKLING", 2, 3.0, 4.0)),
        ("utimizu2_2-4.mp4", ("SPRINKLING", 2, 2.0, 4.0)),
        ("yusuzumi1_2-16.mp4", ("RELAXING", 1, 2.0, 16.0)),
    ],
)
def test_parses_action_interval_names(name, expected):
    assert parse_clip_name(Path(name)) == expected


def test_rejects_unlabelled_clip_name():
    with pytest.raises(ValueError, match="action interval"):
        parse_clip_name(Path("sample.mp4"))


def test_aggregates_frame_and_clip_metrics():
    clips = [
        {
            "environment": "behind",
            "expected_action": "RAMUNE",
            "interval_frames": 4,
            "pose_interval_frames": 2,
            "expected_action_frames": 1,
            "outside_frames": 6,
            "outside_actions": {"NONE": 5, "FANNING": 1},
            "pose_interval_ratio": 0.5,
            "clip_detected": True,
            "occurrence_detected": True,
        },
        {
            "environment": "behind",
            "expected_action": "RAMUNE",
            "interval_frames": 6,
            "pose_interval_frames": 3,
            "expected_action_frames": 0,
            "outside_frames": 4,
            "outside_actions": {"NONE": 4},
            "pose_interval_ratio": 0.5,
            "clip_detected": False,
            "occurrence_detected": False,
        },
    ]

    [result] = aggregate(clips)

    assert result["clip_recall"] == 0.5
    assert result["occurrence_recall"] == 0.5
    assert result["pose_interval_ratio"] == 0.5
    assert result["expected_action_frame_ratio"] == 0.1
    assert result["outside_action_ratio"] == 0.1


def test_ramune_geometry_reports_ready_hands():
    landmarks = [(0.0, 0.0, 1.0)] * 25
    landmarks[11] = (0.4, 0.3, 1.0)
    landmarks[12] = (0.6, 0.3, 1.0)
    landmarks[15] = (0.49, 0.4, 1.0)
    landmarks[16] = (0.51, 0.5, 1.0)
    landmarks[23] = (0.4, 0.7, 1.0)
    landmarks[24] = (0.6, 0.7, 1.0)

    result = ramune_geometry(landmarks)

    assert result is not None
    assert result["gap"] == pytest.approx(0.5)
    assert result["alignment"] == pytest.approx(0.1)
    assert result["ready"] == 1


def test_ramune_pose_candidate_emits_once_per_sustained_setup():
    landmarks = [(0.0, 0.0, 1.0)] * 25
    landmarks[11] = (0.4, 0.3, 1.0)
    landmarks[12] = (0.6, 0.3, 1.0)
    landmarks[15] = (0.49, 0.4, 1.0)
    landmarks[16] = (0.51, 0.5, 1.0)
    landmarks[23] = (0.4, 0.7, 1.0)
    landmarks[24] = (0.6, 0.7, 1.0)
    candidate = RamunePoseCandidate(0.5, 1.0, dwell=0.25)

    assert not candidate.update(landmarks, 0.0)
    assert candidate.update(landmarks, 0.25)
    assert not candidate.update(landmarks, 0.5)


def test_relaxing_pose_candidate_accepts_smoothed_stillness():
    landmarks = [(0.0, 0.0, 1.0)] * 25
    for index, point in {
        11: (0.4, 0.3, 1.0),
        12: (0.6, 0.3, 1.0),
        15: (0.4, 0.5, 1.0),
        16: (0.6, 0.5, 1.0),
        23: (0.4, 0.7, 1.0),
        24: (0.6, 0.7, 1.0),
    }.items():
        landmarks[index] = point
    candidate = RelaxingPoseCandidate(ema_alpha=0.35, max_speed=0.3, max_drift=0.08)

    assert not candidate.update(landmarks, 0.0, 1.0)
    for timestamp in (0.2, 0.4, 0.6, 0.8):
        assert not candidate.update(landmarks, timestamp, 1.0)
    assert candidate.update(landmarks, 1.0, 1.0)
