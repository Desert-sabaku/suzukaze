import pytest
from scripts.compare_pose_results import rescore
from scripts.evaluate_timeline import landmark_errors, match_events, summarize, summarize_landmarks


def test_partial_annotations_do_not_hide_missing_or_low_confidence_predictions():
    annotations = {
        "left_wrist": {"status": "marked", "x_px": 40, "y_px": 30},
        "right_wrist": {"status": "uncertain"},
    }
    missing = landmark_errors(annotations, [], 200, 100)
    assert summarize_landmarks(missing)["pck_20px"] == 0
    points = [[0.0, 0.0, 0.01]] * 33
    errors = landmark_errors(annotations, points, 200, 100)
    assert errors[0]["error_px"] == pytest.approx(50)
    assert summarize_landmarks(errors)["estimated_points"] == 1
    assert summarize_landmarks(errors)["pck_20px"] == 0


def test_event_matching_counts_duplicates_and_misses():
    assert match_events([10, 30, 50], [8, 11, 31, 70], 2) == {
        "tp": 2,
        "fp": 2,
        "fn": 1,
        "signed_error_frames": [-2, 1],
    }


def test_action_end_is_inclusive_and_unlabelled_events_are_not_negatives():
    data = {
        "source": {"fps": 30},
        "intervals": [{"track": "action", "label": "RAMUNE", "start_frame": 1, "end_frame": 2}],
        "events": [],
    }
    rows = [
        {
            "frame_id": i,
            "current": {"gesture": "RAMUNE", "tracking": True},
            "occurrences": ["RAMUNE"] if i == 2 else [],
            "landmark_errors": [],
        }
        for i in range(4)
    ]
    result = summarize(data, rows, 0.5)
    assert result["actions"][0]["frames"] == 2
    assert result["actions"][0]["occurrences"] == {"RAMUNE": 1}
    assert result["events"] == {}
    assert result["outside_action_predictions"] == {"RAMUNE": 2}


def test_rescore_uses_new_annotations_without_mutating_cached_predictions():
    data = {
        "source": {"fps": 30, "total_frames": 1, "width": 200, "height": 100},
        "landmarks": [
            {"frame_id": 0, "points": {"nose": {"status": "marked", "x_px": 100, "y_px": 50}}}
        ],
    }
    rows = [
        {"frame_id": 0, "timestamp": 0.0, "landmarks": [[0.5, 0.5, 0.1]], "landmark_errors": []}
    ]
    scored = rescore(data, rows)
    assert scored[0]["landmark_errors"][0]["error_px"] == 0
    assert rows[0]["landmark_errors"] == []


@pytest.mark.parametrize(
    "rows",
    [
        [],
        [{"frame_id": 1, "timestamp": 0}],
        [{"frame_id": 0, "timestamp": 1}],
        [{"frame_id": 0, "timestamp": float("nan")}],
    ],
)
def test_rescore_rejects_missing_reordered_or_retimed_frames(rows):
    data = {"source": {"fps": 30, "total_frames": 1}, "landmarks": []}
    with pytest.raises(ValueError, match="Cached frame"):
        rescore(data, rows)
