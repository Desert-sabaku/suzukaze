"""Setup diagnostics must not leak labels into runnable gate ablations."""

import numpy as np
import pytest
from scripts.evaluate_opening_setup import (
    CONFIG,
    POLICIES,
    candidate_decision,
    diagnose,
    evaluate_sample,
    longest_evidence,
    predict,
    substitute,
    summarize_family,
)
from scripts.evaluate_opening_temporal import apply_temporal


def sample():
    phase = np.array([1] * 5 + [3] * 2 + [0] * 20 + [2] * 5 + [3] * 2 + [0] * 20)
    action = np.zeros(len(phase), dtype=int)
    action[:7] = action[27:34] = 1
    clip = dict(
        name="two_trials",
        group=1,
        fps=10.0,
        phase=phase.copy(),
        action=action.copy(),
        points=np.ones((len(phase), 33, 3)),
        opening_intervals=[(5, 6), (32, 33)],
        ramune_intervals=[(0, 6), (27, 33)],
    )
    return clip, phase, action


def test_oracle_preserves_unknown_phase_and_does_not_mutate_inputs():
    clip, phase, action = sample()
    clip["phase"][:5] = -1
    phase[5:7] = 4
    action[:] = 0
    p, a = substitute(clip, phase, action, "oracle_both")
    np.testing.assert_array_equal(p[:5], phase[:5])
    assert p[5] == 3 and a[5] == 1
    assert phase[5] == 4 and action[5] == 0


@pytest.mark.parametrize(
    "family, first, second",
    [
        ("baseline", True, True),
        ("initial_phase_only", False, True),
        ("rearm_phase_only", True, False),
        ("both_phase_only", False, False),
    ],
)
def test_first_and_rearm_gates_are_independent(family, first, second):
    clip, phase, action = sample()
    if not first:
        action[:5] = 0
    if not second:
        action[27:32] = 0
    _, events, _ = predict(clip, phase, action, family)
    assert events == [5, 32]
    _, strict_events, _ = predict(clip, phase, action, "baseline")
    if not first:
        assert 5 not in strict_events
    if not second:
        assert 32 not in strict_events


def test_relaxing_first_gate_does_not_relax_rearm_gate():
    clip, phase, action = sample()
    action[:5] = action[27:32] = 0
    assert predict(clip, phase, action, "initial_phase_only")[1] == [5]
    # No first event means the initial gate remains active at the second attempt.
    assert predict(clip, phase, action, "rearm_phase_only")[1] == []


@pytest.mark.parametrize("family", POLICIES)
def test_runtime_ablations_ignore_annotations_and_future(family):
    clip, phase, action = sample()
    out, events, trace = predict(clip, phase, action, family)
    clip["phase"][:] = clip["action"][:] = -1
    actual, pulses, audit = predict(clip, phase, action, family)
    np.testing.assert_array_equal(actual, out)
    assert pulses == events and audit == trace
    phase[20:], action[20:], clip["points"][20:] = 3, 0, 0
    actual, _, audit = predict(clip, phase, action, family)
    np.testing.assert_array_equal(actual[:20], out[:20])
    assert audit[:20] == trace[:20]


def test_trace_is_observational_and_captures_blocked_opening():
    clip, phase, action = sample()
    action[:5] = 0
    out, pulses = apply_temporal(phase, action, clip["points"], clip["fps"], CONFIG)
    actual, events, trace = predict(clip, phase, action, "baseline")
    np.testing.assert_array_equal(out, actual)
    assert pulses == events
    assert trace[5]["blocked_opened"] and trace[5]["state_before"] == "WAIT_SETUP"


def test_phase_only_still_needs_tracking_and_observed_release():
    clip, phase, action = sample()
    clip["points"][:5] = 0
    assert predict(clip, phase, action, "both_phase_only")[1] == [32]
    clip, phase, action = sample()
    clip["points"][7:27] = 0
    assert predict(clip, phase, action, "both_phase_only")[1] == [5]


def test_dwell_uses_timestamp_span_not_frame_coverage():
    assert longest_evidence(np.array([True] * 3), 10) == dict(frames=3, elapsed_seconds=0.2)
    clip, phase, action = sample()
    phase[:2] = 0
    assert 5 not in predict(clip, phase, action, "both_phase_only")[1]


def test_diagnostic_keeps_one_frame_late_as_miss():
    clip, phase, action = sample()
    clip["ramune_intervals"] = [(0, 8), (27, 33)]
    phase[5:7], phase[7] = 2, 3
    out, _, trace = predict(clip, phase, action, "baseline")
    row = diagnose(clip, phase, action, {"baseline": out}, trace)[0]
    assert not row["hits"]["baseline"]
    assert row["first_output_after_anchor_gap_frames"] == 1


def test_oracle_results_do_not_include_synthetic_repetitions():
    clip, phase, action = sample()
    row, _, _ = evaluate_sample(clip, phase, action, "oracle_both")
    assert row["repetitions"] == []


def test_partial_oracle_is_not_an_upper_bound_when_unknown_phase_remains():
    clip, phase, action = sample()
    phase[:25] = 3
    phase[:5] = 1
    action[:25] = 1
    clip["phase"][:20] = 2
    clip["phase"][5] = -1
    clip["phase"][20:22] = 3
    clip["phase"][22:25] = 4
    clip["action"][:25] = 1
    clip["opening_intervals"] = [(20, 21), (32, 33)]
    clip["ramune_intervals"] = [(0, 24), (27, 33)]
    baseline, _, _ = evaluate_sample(clip, phase, action, "baseline")
    oracle, _, trace = evaluate_sample(clip, phase, action, "oracle_phase")
    assert baseline["single"]["details"][0]["matched_run"] is not None
    assert oracle["single"]["details"][0]["matched_run"] is None
    assert trace[20]["state_before"] == "LOCKED"


def test_candidate_needs_improvement_without_false_output_regression():
    clip, phase, action = sample()
    row, _, _ = evaluate_sample(clip, phase, action, "baseline")
    baseline = summarize_family([row])
    assert not candidate_decision(baseline, baseline)["eligible_for_next_validation"]
    import copy

    improved = copy.deepcopy(baseline)
    improved["behind"]["single"]["intervals_hit"] += 1
    assert candidate_decision(baseline, improved)["eligible_for_next_validation"]
    improved["without"]["single"]["unanchored_runs"] += 1
    assert not candidate_decision(baseline, improved)["eligible_for_next_validation"]
