from scripts.evaluate_bow import geometry, labels_at, summarize

from gesture_detection.recognition_types import PoseResult


def test_summary_distinguishes_hold_detection_suppression_and_false_positives():
    rows = [
        {
            "frame_id": frame,
            "action": action,
            "phase": phase,
            "gesture": gesture,
            "raw_bow": raw,
            "tracking": True,
        }
        for frame, action, phase, gesture, raw in (
            (0, "NONE", "NONE", "BOW", True),
            (1, "BOW", "BENDING", "NONE", False),
            (2, "BOW", "HOLD", "FANNING", True),
            (3, "BOW", "HOLD", "BOW", True),
            (4, "BOW", "RETURNING", "BOW", True),
            (5, "NONE", "NONE", "NONE", False),
        )
    ]
    result = summarize(rows, 10)
    assert result["detected_action"]
    assert result["action_coverage"] == 0.5
    assert result["precision"] == 2 / 3
    assert result["false_positive_frames"] == 1
    assert result["first_detection_from_hold_seconds"] == 0.1
    assert result["bow_runs"] == [[0, 0], [3, 4]]
    assert result["raw_bow_suppressed_frames"] == 1
    assert result["phases"]["HOLD"]["bow_frames"] == 1
    assert result["phases"]["HOLD"]["raw_bow_frames"] == 2


def test_missed_bow_has_no_detection_time_or_precision():
    result = summarize(
        [
            {
                "frame_id": 0,
                "action": "BOW",
                "phase": "HOLD",
                "gesture": "NONE",
                "raw_bow": False,
                "tracking": False,
            },
        ],
        30,
    )
    assert not result["detected_action"]
    assert result["first_detection_from_hold_seconds"] is None
    assert result["precision"] is None
    assert result["phases"]["HOLD"]["tracking_frames"] == 0


def test_geometry_reports_out_of_frame_hips_before_angle_calculation():
    points = [(0.5, 0.3, 1.0)] * 33
    points[0] = (0.4, 0.5, 1.0)
    points[23] = (0.5, 1.1, 0.9)
    points[24] = (0.6, 1.2, 0.9)
    result: PoseResult = {"landmarks": points, "selected_action": "NONE", "relaxing_state": False}
    measured = geometry(result)
    assert measured["invalid_bow_points"] == "23,24"
    assert measured["head_above_shoulders"] is False


def test_labels_use_inclusive_annotation_boundaries_and_leave_gaps_empty():
    data = {
        "intervals": [
            {"track": "action", "label": "BOW", "start_frame": 1, "end_frame": 5},
            {"track": "bow_phase", "label": "HOLD", "start_frame": 2, "end_frame": 3},
        ]
    }
    assert labels_at(data, 0) == ("NONE", "NONE")
    assert labels_at(data, 1) == ("BOW", "NONE")
    assert labels_at(data, 3) == ("BOW", "HOLD")
    assert labels_at(data, 5) == ("BOW", "NONE")
    assert labels_at(data, 6) == ("NONE", "NONE")
