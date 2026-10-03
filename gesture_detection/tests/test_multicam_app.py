import json
from pathlib import Path
from unittest.mock import Mock, patch

import numpy as np
import pytest

from gesture_detection import app, config
from gesture_detection.multicam_app import MultiCameraApplication, compose_preview
from gesture_detection.multicam_input import RecordedView
from gesture_detection.recognition_types import PoseResult


def empty_result(_frame, timestamp: float, frame_id: int) -> PoseResult:
    return {
        "landmarks": [],
        "current": {"gesture": "NONE", "tracking": False},
        "selected_action": "NONE",
        "relaxing_state": False,
        "occurrences": (),
        "timestamp": timestamp,
        "frame_id": frame_id,
    }


def test_replay_drains_both_inputs_and_never_delivers_to_unity(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CAMERA_INDICES", (1, 2))
    monkeypatch.setattr(config, "MULTICAM_VIDEO_SESSION", tmp_path / "session.json")
    monkeypatch.setattr(config, "MULTICAM_HEADLESS", True)
    monkeypatch.setattr(config, "MULTICAM_TRACE_PATH", tmp_path / "trace.jsonl")
    monkeypatch.setattr(config, "VIDEO_OUTPUT_PATH", tmp_path / "out.mp4")
    # Native 60fps and 10fps; the final 60fps frame is after the last regular
    # 30Hz output tick, so the EOF tick is necessary to process it.
    views = (
        RecordedView(1, Path("a.mp4"), 6, 8, 6, 0.1),
        RecordedView(2, Path("b.mp4"), 1, 8, 6, 0.1),
    )
    frame = np.zeros((6, 8, 3), dtype=np.uint8)
    sources = [Mock(), Mock()]
    sources[0].read.side_effect = [(frame, i / 60, i) for i in range(6)] + [None]
    sources[1].read.side_effect = [(frame, 0.0, 0), None]
    analyzers = [Mock(), Mock()]
    for analyzer in analyzers:
        analyzer.process.side_effect = empty_result
    writer, asynchronous = Mock(), Mock()
    with (
        patch("gesture_detection.multicam_app.load_session", return_value=views),
        patch("gesture_detection.multicam_app.RecordedInput", side_effect=sources),
        patch("gesture_detection.multicam_app.PoseAnalyzer", side_effect=analyzers),
        patch("gesture_detection.multicam_app.cv2.VideoWriter", return_value=writer),
        patch("gesture_detection.multicam_app.AsyncVideoWriter", return_value=asynchronous),
        patch("gesture_detection.multicam_app.cv2.imshow") as show,
    ):
        samples = Mock()
        MultiCameraApplication(samples).run()
    samples.put.assert_not_called()
    show.assert_not_called()
    assert analyzers[0].process.call_count == 6
    assert analyzers[1].process.call_count == 1
    for source, analyzer in zip(sources, analyzers, strict=True):
        source.close.assert_called_once()
        analyzer.close.assert_called_once()
    asynchronous.release.assert_called_once()
    trace = [json.loads(line) for line in (tmp_path / "trace.jsonl").read_text().splitlines()]
    assert trace[-1]["views"]["0"]["frame_id"] == 5
    assert trace[-1]["fused"]["timestamp"] == 0.1


def test_second_analyzer_failure_closes_first_and_both_captures(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CAMERA_INDICES", (1, 2))
    monkeypatch.setattr(config, "MULTICAM_VIDEO_SESSION", tmp_path / "session.json")
    monkeypatch.setattr(config, "MULTICAM_HEADLESS", True)
    views = (
        RecordedView(1, Path("a.mp4"), 2, 8, 6, 0.1),
        RecordedView(2, Path("b.mp4"), 1, 8, 6, 0.1),
    )
    sources, first = [Mock(), Mock()], Mock()
    with (
        patch("gesture_detection.multicam_app.load_session", return_value=views),
        patch("gesture_detection.multicam_app.RecordedInput", side_effect=sources),
        patch(
            "gesture_detection.multicam_app.PoseAnalyzer",
            side_effect=[first, RuntimeError("model failure")],
        ),
    ):
        with pytest.raises(RuntimeError, match="model failure"):
            MultiCameraApplication().run()
    first.close.assert_called_once()
    for source in sources:
        source.close.assert_called_once()


def test_replay_uses_session_camera_order_when_indices_unspecified(tmp_path, monkeypatch):
    session = tmp_path / "session.json"
    session.write_text(json.dumps({"cameras": [{"camera_index": 4}, {"camera_index": 2}]}))
    monkeypatch.setattr(config, "MULTICAM_VIDEO_SESSION", session)
    monkeypatch.setattr(config, "CAMERA_INDICES", None)
    with patch(
        "gesture_detection.multicam_app.load_session", side_effect=ValueError("checked")
    ) as load:
        with pytest.raises(ValueError, match="checked"):
            MultiCameraApplication().run()
    load.assert_called_once_with(session, (4, 2))


def test_main_routes_opt_in_to_multicam(monkeypatch):
    monkeypatch.setattr(app, "MULTICAM_ENABLED", True)
    monkeypatch.setattr(config, "CAMERA_INDICES", (1, 2))
    with patch("gesture_detection.multicam_app.MultiCameraApplication") as factory:
        app.main()
    factory.return_value.run.assert_called_once()


def test_main_selects_multicam_roles_in_order(monkeypatch):
    monkeypatch.setattr(app, "MULTICAM_ENABLED", True)
    monkeypatch.setattr(config, "MULTICAM_VIDEO_SESSION", None)
    monkeypatch.setattr(config, "MULTICAM_HEADLESS", False)
    monkeypatch.setattr(config, "CAMERA_INDICES", None)
    with (
        patch(
            "gesture_detection.camera_selection.select_camera_indices", return_value=(4, 1)
        ) as select,
        patch("gesture_detection.multicam_app.MultiCameraApplication") as factory,
    ):
        app.main()
    select.assert_called_once_with(2, None)
    assert factory.call_args.args == (None, None, (4, 1))


def test_headless_live_requires_explicit_camera_indices(monkeypatch):
    monkeypatch.setattr(app, "MULTICAM_ENABLED", True)
    monkeypatch.setattr(config, "MULTICAM_VIDEO_SESSION", None)
    monkeypatch.setattr(config, "MULTICAM_HEADLESS", True)
    monkeypatch.setattr(config, "CAMERA_INDICES", None)
    with pytest.raises(ValueError, match="CAMERA_INDICES"):
        app.main()


def test_live_failure_closes_workers(monkeypatch):
    monkeypatch.setattr(config, "MULTICAM_VIDEO_SESSION", None)
    monkeypatch.setattr(config, "MULTICAM_TRACE_PATH", None)
    monkeypatch.setattr(config, "MULTICAM_HEADLESS", True)
    monkeypatch.setattr(config, "CAMERA_INDICES", (1, 2))
    inputs = Mock()
    inputs.poll.side_effect = RuntimeError("camera disconnected")
    with patch("gesture_detection.multicam_app.LiveInputs", return_value=inputs):
        with pytest.raises(RuntimeError, match="camera disconnected"):
            MultiCameraApplication(Mock()).run()
    inputs.close.assert_called_once()


def test_live_recording_writes_composed_frame_and_releases_on_stop(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "MULTICAM_VIDEO_SESSION", None)
    monkeypatch.setattr(config, "MULTICAM_TRACE_PATH", None)
    monkeypatch.setattr(config, "MULTICAM_HEADLESS", True)
    monkeypatch.setattr(config, "RECORD_LIVE_VIDEO", True)
    monkeypatch.setattr(config, "VIDEO_OUTPUT_PATH", tmp_path / "live.mp4")
    inputs = Mock()
    inputs.poll.return_value = []
    inputs.latest_previews.return_value = {}
    writer, asynchronous = Mock(), Mock()
    with (
        patch("gesture_detection.multicam_app.LiveInputs", return_value=inputs),
        patch("gesture_detection.multicam_app.cv2.VideoWriter", return_value=writer),
        patch("gesture_detection.multicam_app.AsyncVideoWriter", return_value=asynchronous),
        patch.object(MultiCameraApplication, "_exit_requested", return_value=True),
    ):
        MultiCameraApplication(camera_indices=(3, 1)).run()
    assert asynchronous.write.call_count == 1
    assert asynchronous.write.call_args.args[0].shape == (432, 1280, 3)
    asynchronous.release.assert_called_once()
    inputs.close.assert_called_once()


def test_stop_event_requests_exit_even_when_headless(monkeypatch):
    monkeypatch.setattr(config, "MULTICAM_HEADLESS", True)
    stop = Mock()
    stop.is_set.return_value = True
    assert MultiCameraApplication(stop=stop)._exit_requested()


@pytest.mark.parametrize("collision", ["video", "session", "trace"])
def test_replay_cannot_overwrite_inputs_or_mix_outputs(tmp_path, monkeypatch, collision):
    monkeypatch.setattr(config, "CAMERA_INDICES", (1, 2))
    session_path = tmp_path / "session.json"
    first_path = tmp_path / "a.mp4"
    monkeypatch.setattr(config, "MULTICAM_VIDEO_SESSION", session_path)
    monkeypatch.setattr(config, "MULTICAM_HEADLESS", True)
    monkeypatch.setattr(
        config, "VIDEO_OUTPUT_PATH", first_path if collision == "video" else tmp_path / "out.mp4"
    )
    monkeypatch.setattr(
        config,
        "MULTICAM_TRACE_PATH",
        session_path
        if collision == "session"
        else config.VIDEO_OUTPUT_PATH
        if collision == "trace"
        else None,
    )
    views = (
        RecordedView(1, first_path, 2, 8, 6, 0.1),
        RecordedView(2, tmp_path / "b.mp4", 1, 8, 6, 0.1),
    )
    with (
        patch("gesture_detection.multicam_app.load_session", return_value=views),
        patch("gesture_detection.multicam_app.RecordedInput") as capture,
    ):
        with pytest.raises(ValueError, match="distinct"):
            MultiCameraApplication().run()
    capture.assert_not_called()


def test_live_sends_each_occurrence_once(monkeypatch):
    monkeypatch.setattr(config, "MULTICAM_VIDEO_SESSION", None)
    monkeypatch.setattr(config, "MULTICAM_TRACE_PATH", None)
    monkeypatch.setattr(config, "MULTICAM_HEADLESS", True)
    monkeypatch.setattr(config, "CAMERA_INDICES", (1, 2))
    result = empty_result(None, 9.9, 0)
    result["current"] = {"gesture": "UCHIMIZU", "tracking": True}
    result["occurrences"] = ("UCHIMIZU",)
    result["occurrence_evidence"] = {"UCHIMIZU": {"wrist_index": 16, "setup_timestamp": 9.5}}
    inputs = Mock()
    inputs.poll.side_effect = [[(0, result)], []]
    inputs.latest_previews.return_value = {}
    with (
        patch("gesture_detection.multicam_app.LiveInputs", return_value=inputs),
        patch("gesture_detection.multicam_app.time.monotonic", side_effect=[10.0, 10.0, 10.1]),
        patch.object(MultiCameraApplication, "_exit_requested", side_effect=[False, True]),
    ):
        samples = Mock()
        MultiCameraApplication(samples).run()
    sent = [entry.args[0] for entry in samples.put.call_args_list]
    assert len(sent) == 2
    assert sent[0].occurrences == (("UCHIMIZU", 9.9),)
    assert sent[1].occurrences == ()
    assert sent[0].observed_at == 9.9
    inputs.close.assert_called_once()


def test_multicam_keeps_overlays_but_only_draws_text_in_header():
    frame = np.zeros((360, 640, 3), dtype=np.uint8)
    raw = empty_result(frame, 0, 0)
    raw["display_landmarks"] = [(0.5, 0.5, 1.0)]
    raw["subject_state"] = "TRACKING"
    raw["ramune_state"] = "WAIT_RELEASE"
    fused: PoseResult = {
        "landmarks": [],
        "selected_action": "NONE",
        "relaxing_state": False,
        "current": {"gesture": "NONE", "tracking": True},
        "locked_events": ("RAMUNE",),
        "release_pending": ("RAMUNE",),
    }
    with patch("gesture_detection.multicam_app.cv2.putText") as text:
        image = compose_preview({0: (frame, raw)}, fused)
    assert image.shape == (432, 1280, 3)
    labels = [entry.args[1] for entry in text.call_args_list]
    assert len(labels) == 3
    assert labels[0].startswith("Camera 0")
    assert labels[1].startswith("Camera 1")
    assert labels[2] == "Combined: NONE | event locks: RAMUNE"
    assert all(entry.args[2][1] < 72 for entry in text.call_args_list)
    # Landmark and subject rectangle remain in the camera image, without modifying input.
    assert tuple(image[72 + 180, 320]) == (0, 0, 255)
    assert tuple(image[72 + 54, 224]) == (80, 180, 80)
    assert not frame.any()
