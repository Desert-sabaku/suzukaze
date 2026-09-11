import multiprocessing as mp

import numpy as np
from modules.ipc import SharedLatestFrame


def consume_frames(channel, result):
    frame = channel.get()
    result.send(frame.tolist())
    result.send(channel.get())
    result.close()


def test_latest_frame_is_a_snapshot():
    channel = SharedLatestFrame((4, 5, 3))
    frame = np.zeros(channel.shape, dtype=np.uint8)
    channel.publish(frame)
    frame.fill(17)
    channel.publish(frame)
    frame.fill(99)
    received = channel.get()
    assert np.all(received == 17)
    channel.publish(frame)
    assert np.all(received == 17)
    assert np.all(channel.get() == 99)
    channel.close()
    assert channel.get() is None


def test_busy_reader_does_not_block_publisher():
    channel = SharedLatestFrame((2, 2, 3))
    with channel._lock:
        assert not channel.publish(np.zeros(channel.shape, dtype=np.uint8))
    channel.close()


def test_shared_frame_crosses_process_boundary_and_close_wakes_reader():
    channel = SharedLatestFrame((2, 2, 3))
    receiver, sender = mp.Pipe(duplex=False)
    process = mp.Process(target=consume_frames, args=(channel, sender))
    process.start()
    try:
        channel.publish(np.full(channel.shape, 42, dtype=np.uint8))
        assert receiver.poll(10)
        assert np.all(np.asarray(receiver.recv()) == 42)
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
