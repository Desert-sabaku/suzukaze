"""Causal display holding and genuine rearming, without annotation access."""

import numpy as np
import pytest
from scripts.evaluate_opening_temporal import TemporalConfig, aggregate, apply_temporal


def inputs(phase):
    phase = np.asarray(phase)
    points = np.ones((len(phase), 33, 3))
    points[:, 11, 0], points[:, 12, 0] = 0.4, 0.6
    points[:, 15, 0], points[:, 16, 0] = 0.45, 0.55
    return phase, np.ones(len(phase), dtype=int), points


def test_hold_bridges_short_gap_but_expires_and_does_not_backfill():
    phase, action, points = inputs([0, 3, 0, 3, 0, 0, 3])
    out, events = apply_temporal(phase, action, points, 10, TemporalConfig(0.1))
    assert out.tolist() == [0, 3, 3, 3, 3, 0, 3]
    assert events == [1, 6]


def test_lockout_suppresses_reappearance_without_release():
    phase, action, points = inputs([3, 0, 3, 0, 0, 3])
    out, events = apply_temporal(
        phase, action, points, 10, TemporalConfig(0.1, 0.2, 0.1, "context")
    )
    assert out.tolist() == [3, 3, 3, 3, 0, 0]
    assert events == [0]


def test_genuine_release_and_new_setup_can_produce_second_opening():
    phase, action, points = inputs([3, 0, 0, 0, 0, 0, 1, 2, 3])
    action[1:6] = 0
    points[1:6, 15, 0], points[1:6, 16, 0] = 0.2, 0.8
    out, events = apply_temporal(phase, action, points, 10, TemporalConfig(0, 0.2, 0.1, "hands"))
    assert events == [0, 8]
    assert out[8] == 3


def test_tracking_loss_is_not_release_and_cannot_rearm():
    phase, action, points = inputs([3, 0, 0, 0, 0, 0, 1, 2, 3])
    action[1:6] = 0
    points[1:6] = 0
    _, events = apply_temporal(phase, action, points, 10, TemporalConfig(0, 0.2, 0.1, "context"))
    assert events == [0]


def test_hands_mode_requires_visible_separation():
    phase, action, points = inputs([3, 0, 0, 0, 0, 0, 1, 2, 3])
    action[1:6] = 0
    _, events = apply_temporal(phase, action, points, 10, TemporalConfig(0, 0.2, 0.1, "hands"))
    assert events == [0]


def test_long_continuous_opening_is_not_truncated():
    phase, action, points = inputs([3] * 100)
    out, events = apply_temporal(phase, action, points, 10, TemporalConfig(0.1, 0.3, 0.15, "hands"))
    assert np.all(out == 3)
    assert events == [0]


def test_changing_future_does_not_change_prefix():
    phase, action, points = inputs([0, 3, 0, 0, 3, 0, 0, 1, 2, 3])
    config = TemporalConfig(0.25, 0.3, 0.15, "context")
    expected, _ = apply_temporal(phase, action, points, 10, config)
    phase[5:], action[5:], points[5:] = 3, 0, 0
    actual, _ = apply_temporal(phase, action, points, 10, config)
    np.testing.assert_array_equal(expected[:5], actual[:5])


def test_scoring_penalizes_duplicate_runs_not_matched_duration():
    row = dict(
        intervals=1,
        intervals_hit=1,
        predicted_runs=3,
        reappearance_runs=2,
        openings_with_reappearance=1,
        occurrence_restarts=2,
        occurrences_with_multiple_runs=1,
        notifications=3,
        active_seconds=10.0,
        outside_action_seconds=3.0,
        unanchored_runs=[],
    )
    assert aggregate([row])["run_f1"] == 0.5
    row["active_seconds"] = 100.0
    assert aggregate([row])["run_f1"] == 0.5


def test_invalid_durations_are_rejected():
    phase, action, points = inputs([3])
    with pytest.raises(ValueError, match="Durations"):
        apply_temporal(phase, action, points, 10, TemporalConfig(-1))


def test_initial_setup_gate_rejects_startup_spike_but_accepts_prepared_opening():
    phase, action, points = inputs([3, 0, 1, 2, 3])
    _, events = apply_temporal(
        phase, action, points, 10, TemporalConfig(0.1, 0.3, 0.1, "hands", True)
    )
    assert events == [4]


def test_outer_test_videos_never_enter_temporal_tuning(monkeypatch):
    from scripts import evaluate_opening_temporal as experiment

    clips = []
    for group in (0, 1, 2, 3):
        phase, action, points = inputs([1, 3, 4, 0])
        action[-1] = 0
        clips.append(
            dict(name=str(group), group=group, phase=phase, action=action, points=points, fps=10)
        )
    permitted = set()

    def choose(train, target):
        permitted.clear()
        permitted.update(c["group"] for c in train)
        assert 0 not in permitted
        return (0.25, 0.1, "linear")

    def predict(train, test, target, *params):
        assert {c["group"] for c in train} <= permitted
        assert {c["group"] for c in train}.isdisjoint(c["group"] for c in test)
        return [c[target].copy() for c in test]

    def tune(validation, family, options=None):
        assert {c["group"] for c, _, _ in validation} <= permitted
        return (experiment.candidates(family) if options is None else options)[0], []

    monkeypatch.setattr(experiment, "choose", choose)
    monkeypatch.setattr(experiment, "fit_predict", predict)
    monkeypatch.setattr(experiment, "tune", tune)
    report, _ = experiment.run(clips)
    assert len(report["families"]["hold"]["clips"]) == 4
