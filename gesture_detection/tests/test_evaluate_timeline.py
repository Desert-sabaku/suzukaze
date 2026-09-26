"""Validation boundaries and causal inputs for the offline pilot."""

from typing import Any

import numpy as np
import pytest
from scripts.evaluate_timeline import ACTIONS, features, labels, metrics


def document(intervals):
    return {"source": {"total_frames": 6}, "intervals": intervals}


def interval(track, label, start, end):
    return dict(track=track, label=label, start_frame=start, end_frame=end)


def test_labels_preserve_unknown_phases_and_inclusive_endpoints():
    action, phase = labels(
        document(
            [
                interval("action", "RAMUNE", 1, 4),
                interval("ramune_phase", "READY", 2, 3),
            ]
        )
    )
    assert action.tolist() == [0, 1, 1, 1, 1, 0]
    assert phase.tolist() == [0, -1, 2, 2, -1, 0]


def test_invalid_overlap_and_phase_parent():
    with pytest.raises(ValueError, match="Overlapping"):
        labels(document([interval("action", "RAMUNE", 1, 3), interval("action", "RELAXING", 3, 4)]))
    with pytest.raises(ValueError, match="outside"):
        labels(document([interval("ramune_phase", "READY", 1, 2)]))


def test_features_do_not_use_future_frames():
    rng = np.random.default_rng(0)
    points = rng.random((20, 33, 3))
    clip: dict[str, Any] = dict(points=points.copy(), aspect=16 / 9, fps=30)
    before = features(clip, 0.25)
    clip["points"][10:] = rng.random((10, 33, 3))
    np.testing.assert_array_equal(before[:10], features(clip, 0.25)[:10])


def test_metrics_include_false_positives_and_ignore_unknown():
    result = metrics(np.array([0, 1, 1, -1]), np.array([1, 1, 0, 4]), ACTIONS)
    assert result["frames"] == 3
    assert result["per_class"]["RAMUNE"]["precision"] == 0.5
    assert result["per_class"]["RAMUNE"]["recall"] == 0.5
    assert result["per_class"]["RAMUNE"]["f1"] == 0.5


def test_inner_selection_never_trains_on_validation_take(monkeypatch):
    from scripts import evaluate_timeline as evaluation

    clips = [dict(group=g, action=np.array([0, 1, 2])) for g in (1, 2)]
    calls = []

    def predict(train, test, target, history, regularization, classifier):
        assert {c["group"] for c in train}.isdisjoint(c["group"] for c in test)
        calls.append((history, regularization))
        return [c[target].copy() for c in test]

    monkeypatch.setattr(evaluation, "fit_predict", predict)
    evaluation.choose(clips, "action")
    assert len(calls) == 24


def test_opening_extension_is_accepted_but_reappearance_is_separate():
    from scripts.evaluate_timeline import opening_diagnostics

    clip = dict(
        action=np.array([0, 1, 1, 1, 1, 0, 0, 0]), phase=np.array([0, 1, 2, 3, 4, 0, 0, 0]), fps=10
    )
    result = opening_diagnostics(clip, np.array([3, 3, 3, 3, 3, 3, 0, 3]))
    assert result["intervals_hit"] == 1
    assert result["reappearance_runs"] == 1
    assert result["unanchored_runs"] == []
    matched = result["details"][0]["matched_run"]
    assert matched["frames"] == [0, 5]
    assert matched["extension_before_seconds"] == 0.3
    assert matched["extension_after_seconds"] == 0.2
    assert result["details"][0]["reappearances"][0]["gap_seconds"] == 0.1


def test_new_ramune_occurrence_is_not_reappearance():
    from scripts.evaluate_timeline import opening_diagnostics

    clip = dict(
        action=np.ones(8, dtype=int),
        phase=np.array([1, 3, 4, 4, 1, 3, 4, 4]),
        ramune_intervals=[(0, 3), (4, 7)],
        opening_intervals=[(1, 1), (5, 5)],
    )
    result = opening_diagnostics(clip, np.array([0, 3, 3, 0, 0, 3, 3, 0]))
    assert result["intervals_hit"] == 2
    assert result["reappearance_runs"] == 0


def test_unanchored_runs_are_not_assumed_correct():
    from scripts.evaluate_timeline import opening_diagnostics

    clip = dict(action=np.array([0, 1, 1, 1, 1]), phase=np.array([0, 1, 2, 3, 4]))
    result = opening_diagnostics(clip, np.array([3, 3, 0, 0, 3]))
    assert result["intervals_hit"] == 0
    assert result["unanchored_runs"] == [[0, 1], [4, 4]]
    assert result["occurrence_restarts"] == 1
    assert result["occurrences_with_multiple_runs"] == 1


def test_one_continuous_run_cannot_count_as_two_openings():
    from scripts.evaluate_timeline import opening_diagnostics

    clip = dict(
        action=np.ones(6, dtype=int),
        phase=np.array([1, 3, 4, 1, 3, 4]),
        ramune_intervals=[(0, 2), (3, 5)],
        opening_intervals=[(1, 1), (4, 4)],
    )
    result = opening_diagnostics(clip, np.full(6, 3))
    assert result["intervals_hit"] == 1
    assert result["reappearance_runs"] == 0


def test_prediction_does_not_read_test_labels():
    from scripts.evaluate_timeline import fit_predict

    rng = np.random.default_rng(24)
    x = rng.normal(size=(30, 8))
    train = [dict(features={0.25: x}, action=np.arange(30) % 3)]
    test: dict[str, Any] = dict(features={0.25: x[:5]}, action=np.zeros(5, dtype=int), points=np.ones((5, 33, 3)))
    expected = fit_predict(train, [test], "action", 0.25, 0.1, "rbf")[0]
    test["action"][:] = 4
    actual = fit_predict(train, [test], "action", 0.25, 0.1, "rbf")[0]
    np.testing.assert_array_equal(expected, actual)
    assert np.all(actual < 3)
