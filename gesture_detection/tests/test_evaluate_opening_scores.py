"""Score inspection must preserve predictions and distinguish missing evidence."""

from typing import Any

import numpy as np
import pytest
from scripts.evaluate_opening_scores import (
    audit_clip,
    distribution,
    phase_runs,
    score_diagnostics,
    summarize_window,
)
from scripts.evaluate_timeline import fit_predict, fit_scores, predict_from_scores


@pytest.mark.parametrize("classifier", ["linear", "rbf"])
def test_score_api_preserves_predictions_and_does_not_read_test_labels(classifier):
    rng = np.random.default_rng(924)
    x = rng.normal(size=(40, 8))
    train = [dict(features={0.25: x}, phase=np.arange(40) % 5)]
    test: dict[str, Any] = dict(features={0.25: x[:8]}, points=np.ones((8, 33, 3)), phase=np.zeros(8, dtype=int))
    test["points"][0] = 0
    scores = fit_scores(train, [test], "phase", 0.25, 0.1, classifier)[0]
    expected = fit_predict(train, [test], "phase", 0.25, 0.1, classifier)[0]
    np.testing.assert_array_equal(predict_from_scores(scores, test["points"]), expected)
    assert expected[0] == 0
    test["phase"][:] = 4
    np.testing.assert_array_equal(
        scores, fit_scores(train, [test], "phase", 0.25, 0.1, classifier)[0]
    )


def test_untrained_classes_cannot_win_and_have_no_margin_statistics():
    x = np.arange(10).reshape(5, 2).astype(float)
    train = [dict(features={0.25: x}, phase=np.array([0, 0, 1, 1, 1]))]
    test: dict[str, Any] = dict(features={0.25: x}, points=np.ones((5, 33, 3)))
    scores = fit_scores(train, [test], "phase", 0.25, 0.1)[0]
    assert np.all(np.isneginf(scores[:, 2:]))
    assert np.all(predict_from_scores(scores, test["points"]) < 2)
    diagnostics = score_diagnostics(scores, np.ones(5, dtype=bool))
    assert all(distribution(values)["count"] == 0 for values in diagnostics.values())


def test_ranking_ties_follow_argmax_and_missing_pose_is_excluded():
    scores = np.array([[0, 0, 1, 1, 1], [0, 0, 0.1, 0.7, 0.8], [0, 0, 0, 20, 0]])
    result = score_diagnostics(scores, np.array([True, True, False]))
    np.testing.assert_equal(result["opened_rank"], [2, 2, np.nan])
    np.testing.assert_allclose(result["opened_minus_best_other"][:2], [0, -0.1])
    assert all(np.isnan(values[-1]) for values in result.values())
    assert distribution(result["opened_score"])["max"] == 1


def test_summary_separates_unobserved_frames_and_blocked_opened():
    scores = np.array([[0, 0, 0, 1, 0]] * 4)
    observed = np.array([True, True, True, False])
    trace = [dict(state_before=state) for state in ("WAIT_SETUP", "LOCKED", "ARMED", "WAIT_SETUP")]
    result = summarize_window(
        np.ones(4, dtype=bool),
        observed,
        score_diagnostics(scores, observed),
        np.full(4, 3),
        np.array([0, 0, 3, 0]),
        trace,
    )
    assert result["missing_pose_frames"] == 1 and result["observed_frames"] == 3
    assert result["blocked_opened_frames"] == 2
    assert result["blocked_by_state"]["WAIT_SETUP"] == 1
    assert result["blocked_by_state"]["LOCKED"] == 1


def test_future_features_do_not_change_prior_scores():
    rng = np.random.default_rng(26)
    x = rng.normal(size=(30, 5))
    train = [dict(features={0.25: x}, phase=np.arange(30) % 5)]
    test: dict[str, Any] = dict(features={0.25: x.copy()}, points=np.ones((30, 33, 3)))
    expected = fit_scores(train, [test], "phase", 0.25, 0.1)[0]
    test["features"][0.25][15:] = 100
    actual = fit_scores(train, [test], "phase", 0.25, 0.1)[0]
    np.testing.assert_array_equal(actual[:15], expected[:15])


def test_unknown_phase_training_does_not_affect_scores():
    x = np.arange(30).reshape(10, 3).astype(float)
    y = np.arange(10) % 5
    y[0] = -1
    test = dict(features={0.25: x}, points=np.ones((10, 33, 3)))
    a = fit_scores([dict(features={0.25: x}, phase=y)], [test], "phase", 0.25, 0.1)[0]
    b = fit_scores([dict(features={0.25: x[1:]}, phase=y[1:])], [test], "phase", 0.25, 0.1)[0]
    np.testing.assert_array_equal(a, b)


def test_phase_runs_include_none_and_preserve_inclusive_boundaries():
    assert phase_runs(np.array([0, 2, 2, 4, 3, 0])) == [
        dict(frames=[0, 0], phase="NONE"),
        dict(frames=[1, 2], phase="READY"),
        dict(frames=[3, 3], phase="WAIT_RELEASE"),
        dict(frames=[4, 4], phase="OPENED"),
        dict(frames=[5, 5], phase="NONE"),
    ]


def test_audit_windows_allow_empty_before_and_after_and_keep_unknown_labels():
    phase = np.array([3, 2, 2, 2, 2, 2, 3])
    scores = np.eye(5)[phase]
    clip: dict[str, Any] = dict(
        name="edge",
        group=1,
        fps=10,
        points=np.ones((7, 33, 3)),
        aspect=1,
        phase=phase.copy(),
        action=np.ones(7, dtype=int),
        opening_intervals=[(0, 0), (6, 6)],
        ramune_intervals=[(0, 0), (1, 6)],
    )
    clip["phase"][3] = -1
    audit, _, arrays = audit_clip(clip, scores, clip["action"])
    assert audit["intervals"][0]["windows"]["before_1s"]["frames"] == 0
    assert audit["intervals"][1]["windows"]["after_1s"]["frames"] == 0
    assert audit["summaries"]["unknown_phase"]["frames"] == 1
    np.testing.assert_array_equal(arrays["scores"], scores)
    assert clip["phase"][3] == -1
