import json
import queue
import threading
from pathlib import Path
from unittest.mock import Mock, patch

import numpy as np
import pytest

from gesture_detection import config
from gesture_detection.multicam_input import (
    LiveInputs,
    RecordedInput,
    RecordedView,
    camera_worker,
    load_session,
)


def session(tmp_path: Path) -> Path:
    cameras = []
    for camera, frames in ((1, 30), (2, 10)):
        name = f"camera_{camera:02}.mp4"
        (tmp_path / name).touch()
        cameras.append(
            dict(camera_index=camera, file=name, frames_written=frames, width=4, height=3)
        )
    path = tmp_path / "session.json"
    path.write_text(json.dumps(dict(duration_seconds=1, cameras=cameras)))
    return path


def test_session_uses_capture_duration_not_nominal_video_fps(tmp_path):
    a, b = load_session(session(tmp_path), (1, 2))
    assert (a.fps, b.fps) == (30, 10)
    capture = Mock()
    capture.get.return_value = 10
    frame = np.zeros((3, 4, 3), dtype=np.uint8)
    capture.read.side_effect = [(True, frame), (True, frame)]
    with patch("gesture_detection.multicam_input.cv2.VideoCapture", return_value=capture):
        source = RecordedInput(b)
        first, second = source.read(), source.read()
        assert first is not None and second is not None
        assert first[1:] == (0, 0)
        assert second[1:] == (0.1, 1)
        source.close()
    capture.release.assert_called_once()


@pytest.mark.parametrize(
    "rotation, expected",
    [
        ("clockwise", [[3, 1], [4, 2]]),
        ("counterclockwise", [[2, 4], [1, 3]]),
        ("180", [[4, 3], [2, 1]]),
    ],
)
def test_recorded_input_rotates_before_returning_frame(tmp_path, rotation, expected):
    view = RecordedView(0, tmp_path / "a.mp4", 1, 2, 2, 1)
    frame = np.repeat(np.array([[1, 2], [3, 4]], dtype=np.uint8)[:, :, None], 3, axis=2)
    capture = Mock()
    capture.get.return_value = 1
    capture.read.return_value = True, frame
    with patch("gesture_detection.multicam_input.cv2.VideoCapture", return_value=capture):
        source = RecordedInput(view, rotation)
        sample = source.read()
        source.close()
    assert sample is not None
    rotated, timestamp, frame_id = sample
    assert rotated[:, :, 0].tolist() == expected
    assert (timestamp, frame_id) == (0.0, 0)


@pytest.mark.parametrize("change", ["duration", "duplicate", "escape", "frames"])
def test_invalid_sessions_are_rejected(tmp_path, change):
    path = session(tmp_path)
    data = json.loads(path.read_text())
    if change == "duration":
        data["duration_seconds"] = float("nan")
    elif change == "duplicate":
        data["cameras"].append(data["cameras"][0])
    elif change == "escape":
        data["cameras"][0]["file"] = "../outside.mp4"
    else:
        data["cameras"][0]["frames_written"] = 1.5
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        load_session(path, (1, 2))


def test_decode_failure_is_not_silently_treated_as_eof(tmp_path):
    view = RecordedView(1, tmp_path / "a.mp4", 2, 4, 3, 0.2)
    capture = Mock()
    capture.get.return_value = 2
    capture.read.return_value = False, None
    with patch("gesture_detection.multicam_input.cv2.VideoCapture", return_value=capture):
        source = RecordedInput(view)
        try:
            with pytest.raises(ValueError, match="Truncated"):
                source.read()
        finally:
            source.close()
    capture.release.assert_called_once()


def test_mismatched_capture_metadata_releases_capture(tmp_path):
    capture = Mock()
    capture.get.return_value = 9
    with patch("gesture_detection.multicam_input.cv2.VideoCapture", return_value=capture):
        with pytest.raises(ValueError, match="matching"):
            RecordedInput(RecordedView(1, tmp_path / "a.mp4", 10, 4, 3, 1))
    capture.release.assert_called_once()


def test_live_worker_retries_full_event_queue_and_closes_resources():
    capture = Mock()
    capture.get.return_value = 30
    capture.read.return_value = True, np.zeros((3, 4, 3), dtype=np.uint8)
    analyzer = Mock()
    pulse = {"occurrences": ("UCHIMIZU",)}
    analyzer.process.return_value = pulse
    results, preview, errors = Mock(), Mock(), Mock()
    stop = threading.Event()
    calls = []

    def put(value, timeout):
        calls.append(value)
        if len(calls) == 1:
            raise queue.Full
        stop.set()

    results.put.side_effect = put
    with (
        patch("gesture_detection.multicam_input.open_camera", return_value=capture),
        patch("gesture_detection.multicam_input.PoseAnalyzer", return_value=analyzer),
    ):
        camera_worker(1, 2, False, results, preview, errors, stop)
    assert calls == [(1, pulse), (1, pulse)]
    analyzer.process.assert_called_once()
    capture.release.assert_called_once()
    analyzer.close.assert_called_once()
    errors.put.assert_not_called()


def test_live_worker_rotates_frame_before_inference_and_preview(monkeypatch):
    monkeypatch.setattr(config, "MULTICAM_ROTATION", ("clockwise", "counterclockwise"))
    frame = np.repeat(np.array([[1, 2]], dtype=np.uint8)[:, :, None], 3, axis=2)
    capture = Mock()
    capture.get.return_value = 30
    capture.read.return_value = True, frame
    analyzer = Mock()
    analyzer.process.return_value = {}
    stop = threading.Event()
    results, preview, errors = Mock(), Mock(), Mock()
    with (
        patch("gesture_detection.multicam_input.open_camera", return_value=capture),
        patch("gesture_detection.multicam_input.PoseAnalyzer", return_value=analyzer),
        patch("gesture_detection.multicam_input.put_latest") as put_latest,
    ):
        put_latest.side_effect = lambda *_args: stop.set()
        camera_worker(1, 2, False, results, preview, errors, stop)
    rotated = analyzer.process.call_args.args[0]
    assert rotated.shape == (2, 1, 3)
    assert rotated[:, :, 0].tolist() == [[2], [1]]
    assert put_latest.call_args.args[1][0] is rotated


def test_partial_worker_start_failure_stops_started_worker_and_closes_queues():
    context = Mock()
    first, second = Mock(pid=100), Mock(pid=None)
    second.start.side_effect = RuntimeError("spawn failure")
    context.Process.side_effect = [first, second]
    channels = [Mock() for _ in range(4)]
    context.Queue.side_effect = channels
    with (
        patch("gesture_detection.multicam_input.mp.get_context", return_value=context),
        patch("gesture_detection.multicam_input.PoseAnalyzer.ensure_model"),
    ):
        inputs = LiveInputs((1, 2), (True, False))
        with pytest.raises(RuntimeError, match="spawn failure"):
            inputs.start()
    context.Event.return_value.set.assert_called_once()
    first.terminate.assert_called_once()
    for channel in channels:
        channel.close.assert_called_once()
