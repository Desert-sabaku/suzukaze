from pathlib import Path

import pytest
from scripts.evaluate_action_intervals import aggregate, parse_clip_name


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
