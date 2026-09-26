"""Rearming selection must consider the next opening, not only silence."""

import numpy as np
from scripts.evaluate_opening_rearm import score_config, tune_rearm
from scripts.evaluate_opening_temporal import TemporalConfig


def sample():
    phase = np.array([1] * 4 + [3] * 3 + [4] * 5 + [0] * 10)
    action = np.array([1] * 12 + [0] * 10)
    points = np.ones((len(phase), 33, 3))
    points[:, 11, 0], points[:, 12, 0] = 0.4, 0.6
    points[:, 15, 0], points[:, 16, 0] = 0.45, 0.55
    clip = dict(
        name="trial",
        fps=10.0,
        phase=phase,
        action=action,
        points=points,
        opening_intervals=[(4, 6)],
        ramune_intervals=[(0, 11)],
    )
    return clip, phase, action


def test_blocking_second_opening_is_penalized_despite_perfect_single_result():
    row = sample()
    previous = score_config([row], TemporalConfig(0.1, 0.3, 0.15, "hands", True))
    candidate = score_config([row], TemporalConfig(0.1, 0.3, 0.15, "context", True))
    assert previous["single"]["intervals_hit"] == candidate["single"]["intervals_hit"] == 1
    assert previous["repeated"]["intervals_hit"] == 1
    assert candidate["repeated"]["intervals_hit"] == 2
    assert candidate["score"] > previous["score"]


def test_tuning_can_choose_rearming_over_permanent_lockout():
    cfg, trials = tune_rearm([sample()], 0.1)
    assert cfg.release_mode == "context"
    assert len(trials) == 18
    assert score_config([sample()], cfg)["repeated"]["intervals_hit"] == 2


def test_missing_observation_is_not_positive_release_evidence():
    clip, phase, action = sample()
    clip["points"][12:] = 0
    result = score_config([(clip, phase, action)], TemporalConfig(0.1, 0.3, 0.15, "context", True))
    assert result["single"]["intervals_hit"] == 1
    assert result["repeated"]["intervals_hit"] == 1
