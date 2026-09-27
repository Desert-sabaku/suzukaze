from scripts.evaluate_multicam import score, summarize


def test_event_scoring_rejects_hold_and_counts_duplicate_pulses():
    intervals = [
        dict(track="action", label="RAMUNE", start_frame=2, end_frame=8),
        dict(track="ramune_phase", label="OPENED", start_frame=5, end_frame=6),
    ]
    predictions = [dict(frame=i, gesture="RAMUNE", events=[]) for i in range(10)]
    assert not score(intervals, predictions, 10)["trials"][0]["detected"]
    for i in (2, 5, 9):
        predictions[i]["events"] = ["RAMUNE"]
    result = score(intervals, predictions, 10)
    trial = result["trials"][0]
    assert trial["detected"] and trial["opened_phase_hit"]
    assert trial["first_response_seconds"] == 0
    assert trial["extra_events"] == 1
    assert result["unmatched_events"] == {"RAMUNE": 1}
    assert result["unlabelled_output_seconds"] == {"RAMUNE": 0.3}


def test_pair_summary_excludes_missing_annotation():
    rows = []
    for take, c1, c2 in [("paired", False, True), ("unlabelled", None, True)]:
        for camera, detected in [(1, c1), (2, c2)]:
            trials = (
                []
                if detected is None
                else [dict(label="FANNING", detected=detected, opened_phase_hit=None)]
            )
            rows.append(
                dict(take=take, camera=camera, profile="rules_full", metrics=dict(trials=trials))
            )
    counts = summarize(rows)["rules_full"]["counts"]["FANNING"]
    assert counts["trials"] == 1
    assert counts["camera1"] == 0
    assert counts["either"] == counts["camera2_rescues"] == 1
