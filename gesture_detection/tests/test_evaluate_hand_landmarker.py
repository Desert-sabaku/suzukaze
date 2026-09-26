from types import SimpleNamespace

import pytest
from scripts.evaluate_hand_landmarker import aggregate, palm_center


def test_palm_center_accounts_for_aspect_ratio():
    hand = [SimpleNamespace(x=0.0, y=0.0) for _ in range(21)]
    for index in (0, 5, 9, 13, 17):
        hand[index] = SimpleNamespace(x=0.25, y=0.5)

    center = palm_center(hand, 2.0)

    assert center.tolist() == pytest.approx([0.5, 0.5])


def test_aggregates_hand_availability():
    clips = [
        {
            "environment": "behind",
            "interval_frames": 4,
            "hand_counts": {"0": 1, "1": 1, "2": 2},
            "two_hand_ratio": 0.5,
        },
        {
            "environment": "behind",
            "interval_frames": 2,
            "hand_counts": {"0": 2},
            "two_hand_ratio": 0.0,
        },
    ]

    [result] = aggregate(clips)

    assert result["any_hand_ratio"] == 0.5
    assert result["two_hand_ratio"] == pytest.approx(1 / 3)
    assert result["clips_with_two_hands"] == 1
