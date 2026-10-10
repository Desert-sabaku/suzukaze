import math
import threading
from unittest.mock import MagicMock, patch

import pytest

from gesture_detection.video_output import AsyncVideoWriter, open_video_writer, usable_fps


def test_release_flushes_all_frames_in_order():
    writer = MagicMock()
    output = AsyncVideoWriter(writer, capacity=2)
    for frame in range(20):
        output.write(frame)
    output.release()
    assert [c.args[0] for c in writer.write.call_args_list] == list(range(20))
    writer.release.assert_called_once()
    output.release()
    writer.release.assert_called_once()
    with pytest.raises(RuntimeError, match="closed"):
        output.write(21)


def test_encoding_runs_on_background_thread():
    producer_thread = threading.get_ident()
    threads = []
    writer = MagicMock()
    writer.write.side_effect = lambda frame: threads.append(threading.get_ident())
    output = AsyncVideoWriter(writer, capacity=2)
    output.write(1)
    output.release()
    assert threads and threads[0] != producer_thread


def test_encoder_failure_is_reported_without_hanging():
    failed = threading.Event()
    writer = MagicMock()

    def fail(frame):
        failed.set()
        raise ValueError("encoder failed")

    writer.write.side_effect = fail
    output = AsyncVideoWriter(writer, capacity=1)
    try:
        try:
            output.write(1)
        except RuntimeError:
            pass
        assert failed.wait(5)
        with pytest.raises(RuntimeError, match="Video encoding failed"):
            output.release()
        writer.release.assert_called_once()
    finally:
        output._thread.join(5)


@pytest.mark.parametrize(
    ("reported", "expected"),
    [(25, 25.0), (29.97, 29.97), (0.0, 30.0), (-1.0, 30.0), (math.nan, 30.0), (True, 30.0)],
)
def test_usable_fps_falls_back_for_missing_or_invalid_rates(reported, expected):
    assert usable_fps(reported, 30.0) == expected


def test_open_video_writer_creates_the_directory(tmp_path):
    path = tmp_path / "nested" / "out.mp4"
    with patch("gesture_detection.video_output.cv2.VideoWriter") as video_writer:
        video_writer.return_value.isOpened.return_value = True
        assert open_video_writer(path, 30.0, (64, 48)) is video_writer.return_value
    assert path.parent.is_dir()
    assert video_writer.call_args.args[0] == str(path)
    assert video_writer.call_args.args[2:] == (30.0, (64, 48))


def test_open_video_writer_releases_a_writer_that_did_not_open(tmp_path):
    with patch("gesture_detection.video_output.cv2.VideoWriter") as video_writer:
        video_writer.return_value.isOpened.return_value = False
        with pytest.raises(RuntimeError, match="Unable to open output video file"):
            open_video_writer(tmp_path / "out.mp4", 30.0, (64, 48))
    video_writer.return_value.release.assert_called_once_with()
