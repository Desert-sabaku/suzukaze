import threading
from unittest.mock import MagicMock

import pytest
from modules.video_output import AsyncVideoWriter


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
