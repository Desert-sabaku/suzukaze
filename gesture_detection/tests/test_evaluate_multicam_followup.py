import numpy as np
from scripts.analyze_multicam_followup import output_runs, smoothed_relaxing
from scripts.evaluate_multicam_followup import ramune_probe, replay

from gesture_detection.ramune import RamuneAnalyzer


def skeleton():
    points = np.tile([0.5, 0.5, 1.0], (33, 1))
    points[11, :2] = [0.3, 0.2]
    points[12, :2] = [0.7, 0.2]
    points[23, :2] = [0.3, 0.8]
    points[24, :2] = [0.7, 0.8]
    return points


def test_probe_reports_base_drift_without_changing_detector():
    detector = RamuneAnalyzer()
    detector.state = "READY"
    detector.base_index = 16
    detector.base = (0.5, 0.5)
    detector.scale = 0.4
    detector.upper_y = 0.3
    detector.ready_gap = 0.5
    points = skeleton()
    points[16, 1] = 0.65
    points[15, 1] = 0.45
    before = vars(detector).copy()
    result = ramune_probe(detector, points, 0.5)
    assert result["reset_conditions"] == ["base_y_drift"]
    assert result["press_enough"]
    assert not result["closing_enough"]
    assert vars(detector) == before


def test_speed_diagnostic_attributes_single_joint_motion():
    points = np.stack([skeleton(), skeleton()])
    points[1, 16, 0] += 0.1
    _, diagnostics = replay(points, fps=10, aspect=2, mode="rules")
    assert diagnostics[0]["fastest_joint"] is None
    assert diagnostics[1]["fastest_joint"] == "right_wrist"
    assert np.isclose(diagnostics[1]["motion_speed"], 0.2 / 0.6 / 0.1)


def test_smoothing_resets_on_missing_pose_and_preserves_other_gestures():
    points = np.stack([skeleton() for _ in range(30)])
    points[12:16] = 0
    predictions = [dict(frame=i, gesture="NONE", events=[]) for i in range(30)]
    predictions[11] = dict(frame=11, gesture="UCHIMIZU", events=["UCHIMIZU"])
    result = smoothed_relaxing(points, predictions, 10, 2)
    assert result[10]["gesture"] == "RELAXING"
    assert result[11] == predictions[11]
    assert all(p["gesture"] == "NONE" for p in result[12:26])
    assert result[29]["gesture"] == "RELAXING"
    assert predictions[10]["gesture"] == "NONE"


def test_output_persistence_distinguishes_flicker_from_sustained_output():
    predictions = [
        dict(gesture=g) for g in ["NONE", "RELAXING", "NONE", "RELAXING", "RELAXING", "NONE"]
    ]
    result = output_runs(predictions, 1, 4, "RELAXING", 10)
    assert result == dict(seconds=0.3, longest_seconds=0.2, coverage=0.75, runs=2)
