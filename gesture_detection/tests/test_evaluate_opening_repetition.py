"""Synthetic sequence assembly preserves labels and does not reset the latch."""

import numpy as np
from scripts.evaluate_opening_repetition import repeat_clip, summarize
from scripts.evaluate_opening_temporal import TemporalConfig, apply_temporal


def source():
    return dict(
        name="example",
        fps=10.0,
        phase=np.array([1, 2, 3, 4, 0]),
        action=np.array([1, 1, 1, 1, 0]),
        points=np.ones((5, 33, 3)),
        ramune_intervals=[(0, 3)],
        opening_intervals=[(2, 2)],
    )


def test_repeat_offsets_anchors_and_marks_inserted_gap_unknown():
    clip = source()
    repeated, phase, action, offset = repeat_clip(clip, clip["phase"], clip["action"], 0.3)
    assert offset == 8
    assert repeated["ramune_intervals"] == [(0, 3), (8, 11)]
    assert repeated["opening_intervals"] == [(2, 2), (10, 10)]
    assert repeated["phase"][5:8].tolist() == [-1, -1, -1]
    assert phase[5:8].tolist() == [0, 0, 0]
    assert action[5:8].tolist() == [0, 0, 0]
    assert not repeated["points"][5:8].any()
    assert clip["opening_intervals"] == [(2, 2)]


def test_missing_gap_does_not_unlock_or_reset_state():
    clip = source()
    repeated, phase, action, offset = repeat_clip(clip, clip["phase"], clip["action"], 2.0)
    config = TemporalConfig(0.0, 0.3, 0.1, "context", True)
    out, events = apply_temporal(phase, action, repeated["points"], 10, config)
    assert events == [2]
    assert not out[offset:].any()


def test_second_hit_is_conditioned_on_first_not_counted_as_new_independent_data():
    rows = [
        dict(
            anchors_per_copy=1,
            first_hit=True,
            second_hit=False,
            diagnostics={"reappearance_runs": 0},
        ),
        dict(
            anchors_per_copy=1,
            first_hit=True,
            second_hit=True,
            diagnostics={"reappearance_runs": 0},
        ),
        dict(
            anchors_per_copy=0,
            first_hit=False,
            second_hit=False,
            diagnostics={"reappearance_runs": 0},
        ),
    ]
    result = summarize(rows)
    assert result["clips"] == 2
    assert result["first_hits"] == 2
    assert result["second_hits_given_first"] == 1
    assert result["both_hit_fraction"] == 0.5
