from dataclasses import dataclass

from scripts.evaluate_multicam_fusion import clock_intervals, fuse
from scripts.evaluate_multicam_temporal import FollowingRamune, OutputEnvelope
from scripts.multicam_temporal_metrics import temporal_score


def test_phase_tolerance_accepts_late_event_but_not_duplicates():
    annotations = [
        dict(track="action", label="RAMUNE", start_frame=0, end_frame=39),
        dict(track="ramune_phase", label="OPENED", start_frame=10, end_frame=12),
    ]
    predictions = [dict(frame=i, gesture="NONE", events=[]) for i in range(40)]
    for frame in (16, 20):
        predictions[frame]["events"] = ["RAMUNE"]
    strict = temporal_score(annotations, predictions, 10, tolerance=0)
    tolerant = temporal_score(annotations, predictions, 10)
    assert not strict["trials"][0]["detected"]
    assert tolerant["trials"][0]["detected"]
    assert tolerant["trials"][0]["matched_event_frame"] == 16
    assert tolerant["trials"][0]["extra_events"] == 1
    assert tolerant["unmatched_events"] == {"RAMUNE": 1}


def test_phase_tolerance_does_not_cross_action_boundary():
    annotations = [
        dict(track="action", label="RAMUNE", start_frame=0, end_frame=15),
        dict(track="ramune_phase", label="OPENED", start_frame=10, end_frame=12),
    ]
    predictions = [
        dict(frame=i, gesture="NONE", events=["RAMUNE"] if i == 16 else []) for i in range(20)
    ]
    result = temporal_score(annotations, predictions, 10)
    assert not result["trials"][0]["detected"]
    assert result["unmatched_events"] == {"RAMUNE": 1}


def test_flicker_is_counted_independently_of_phase_tolerance():
    annotations = [dict(track="action", label="FANNING", start_frame=1, end_frame=7)]
    predictions = [
        dict(frame=i, gesture="FANNING" if i in (2, 3, 5, 6, 7, 8) else "NONE", events=[])
        for i in range(10)
    ]
    trial = temporal_score(annotations, predictions, 10)["trials"][0]
    assert trial["output_runs"] == 2
    assert trial["reappearances"] == 1
    assert trial["tail_overrun_seconds"] == 0.1


def test_envelope_holds_short_loss_but_releases_long_loss():
    gate = OutputEnvelope()
    assert gate.update("FANNING", 0, []) == "NONE"
    assert gate.update("FANNING", 0.2, []) == "FANNING"
    assert gate.update("NONE", 0.3, []) == "FANNING"
    assert gate.update("FANNING", 0.4, []) == "FANNING"
    assert gate.update("NONE", 0.8, []) == "FANNING"
    assert gate.update("NONE", 1.0, []) == "NONE"


@dataclass
class Point:
    x: float = 0.5
    y: float = 0.5
    visibility: float = 1.0


def pose(upper: float = 0.35, lower: float = 0.55) -> list[Point]:
    points = [Point() for _ in range(33)]
    points[11].x, points[12].x = 0.3, 0.7
    points[11].y = points[12].y = 0.2
    points[23].y = points[24].y = 0.8
    points[15].y, points[16].y = upper, lower
    return points


def prepared():
    detector = FollowingRamune(wait_in_setup=True)
    for i in range(4):
        assert not detector.update(pose(), i / 10)
    assert detector.state == "READY"
    assert not detector.update(pose(upper=0.25), 0.4)
    for i in range(5, 31):
        assert not detector.update(pose(upper=0.25), i / 10)
        assert detector.state == "READY"
    return detector


def test_following_setup_accepts_raise_hold_then_press():
    detector = prepared()
    assert detector.update(pose(upper=0.50), 3.1)
    assert detector.state == "OPENED"


def test_following_setup_rejects_common_downward_motion():
    detector = prepared()
    assert not detector.update(pose(upper=0.35, lower=0.65), 3.1)
    assert detector.state != "OPENED"


def test_fusion_is_causal_and_deduplicates_without_hiding_later_repetition():
    def pulse(t):
        return dict(seconds=t, gesture="RAMUNE", events=["RAMUNE"])

    output, diagnostics = fuse([[pulse(0.1), pulse(0.9)], [pulse(0.15)]], 1.2)
    events = [p for p in output if p["events"]]
    assert len(events) == 2
    assert events[0]["seconds"] >= 0.1
    assert events[1]["seconds"] >= 0.9
    assert all(p["gesture"] == "NONE" for p in output if p["seconds"] < 0.1)
    assert diagnostics["suppressed_events"] == {"RAMUNE": 1}
    assert output[-1]["gesture"] == "NONE"  # stale observations expire


def test_annotation_clock_preserves_interval_duration():
    converted = clock_intervals(
        [dict(track="action", label="FANNING", start_frame=10, end_frame=19)], 10
    )
    assert converted[0]["start_frame"] == 30
    assert converted[0]["end_frame"] == 59
