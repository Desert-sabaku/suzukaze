import multiprocessing as mp

import numpy as np
from modules.ipc import SharedLatestFrame


def consume_frames(channel, result):
    frame = channel.get()
    result.send([frame[0].tolist(), frame[1], frame[2]])
    result.send(channel.get())
    result.close()


def test_latest_frame_is_a_snapshot():
    channel = SharedLatestFrame((4, 5, 3))
    frame = np.zeros(channel.shape, dtype=np.uint8)
    channel.publish(frame, 1.25, 10)
    frame.fill(17)
    channel.publish(frame, 2.5, 11)
    frame.fill(99)
    sample = channel.get()
    assert sample is not None
    received, timestamp, frame_id = sample
    assert timestamp == 2.5
    assert frame_id == 11
    assert np.all(received == 17)
    channel.publish(frame, 3.75, 12)
    assert np.all(received == 17)
    sample = channel.get()
    assert sample is not None
    assert np.all(sample[0] == 99)
    assert sample[1:] == (3.75, 12)
    channel.close()
    assert channel.get() is None


def test_busy_reader_does_not_block_publisher():
    channel = SharedLatestFrame((2, 2, 3))
    with channel._lock:
        assert not channel.publish(np.zeros(channel.shape, dtype=np.uint8), 0.0, 0)
    channel.close()


def test_shared_frame_crosses_process_boundary_and_close_wakes_reader():
    channel = SharedLatestFrame((2, 2, 3))
    receiver, sender = mp.Pipe(duplex=False)
    process = mp.Process(target=consume_frames, args=(channel, sender))
    process.start()
    try:
        channel.publish(np.full(channel.shape, 42, dtype=np.uint8), 2.5, 42)
        assert receiver.poll(10)
        pixels, timestamp, frame_id = receiver.recv()
        assert np.all(np.asarray(pixels) == 42)
        assert timestamp == 2.5
        assert frame_id == 42
        channel.close()
        assert receiver.poll(10)
        assert receiver.recv() is None
        process.join(10)
        assert process.exitcode == 0
    finally:
        channel.close()
        if process.is_alive():
            process.terminate()
            process.join()
        receiver.close()
        sender.close()
