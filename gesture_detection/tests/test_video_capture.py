import csv
import json
from unittest.mock import Mock

import cv2
import numpy as np
import pytest
from scripts import video_capture as recorder


def frames(value=0, count=3):
    return [np.full((48, 64, 3), value, dtype=np.uint8) for _ in range(count)]


@pytest.mark.parametrize(
    "argv",
    [
        ["--cameras"],
        ["--cameras", "0", "0", "2"],
        ["--cameras", "-1", "1", "2"],
        ["--fps", "0"],
        ["--duration", "nan"],
        ["--countdown", "-1"],
        ["--width", "0"],
        ["--duration", "inf"],
    ],
)
def test_invalid_arguments(argv):
    with pytest.raises(SystemExit):
        recorder.parse_args(argv)


@pytest.mark.parametrize("count", [1, 2, 3, 5])
def test_recording_common_timeline_and_metadata(tmp_path, count):
    ids = list(range(0, count * 2, 2))
    args = recorder.parse_args(["--codec", "MJPG", "--fps", "10", "--cameras", *map(str, ids)])
    assert args.cameras == ids
    take = recorder.Take(tmp_path / "take", args, frames(count=count), 100.0)
    take.write(frames(20, count), [100.01] * count, 100.02)
    take.write(frames(30, count), [100.03] * count, 100.03)  # Same output slot: skip.
    take.write(frames(100, count), [100.35] * count, 100.35)  # Fill slots 1 and 2.
    take.marker(100.36)
    take.close("stopped")
    metadata = json.loads((take.path / "metadata.json").read_text())
    assert metadata["camera_ids"] == ids
    assert len(list(take.path.glob("*.avi"))) == count
    assert metadata["frames"] == 4
    assert metadata["repeated_batches"] == 2
    assert metadata["skipped_batches"] == 1
    assert metadata["markers"][0]["elapsed_seconds"] == pytest.approx(0.36)
    with (take.path / "frames.csv").open() as stream:
        rows = list(csv.DictReader(stream))
    assert [row["repeated"] for row in rows] == ["0", "1", "1", "0"]
    assert rows[2]["camera_0_grab_seconds"] == "0.010000"
    for camera_id in args.cameras:
        video = cv2.VideoCapture(str(take.path / f"camera_{camera_id}.avi"))
        try:
            decoded = []
            while True:
                ok, frame = video.read()
                if not ok:
                    break
                decoded.append(frame.mean())
            assert len(decoded) == 4
            assert decoded == pytest.approx([20, 20, 20, 100], abs=3)
        finally:
            video.release()


def test_grab_all_before_retrieve(monkeypatch):
    calls = []
    cameras = []
    for i in range(3):
        camera = Mock()
        camera.grab.side_effect = lambda i=i: calls.append(("grab", i)) or True
        camera.retrieve.side_effect = lambda i=i: (
            calls.append(("retrieve", i)) or True,
            frames()[i],
        )
        cameras.append(camera)
    result, stamps = recorder.capture_frames(cameras)
    assert len(result) == len(stamps) == 3
    assert calls == [("grab", i) for i in range(3)] + [("retrieve", i) for i in range(3)]
    cameras[1].grab.side_effect = lambda: False
    with pytest.raises(RuntimeError, match="slot 2"):
        recorder.capture_frames(cameras)


def test_camera_open_failure_releases_all(monkeypatch):
    cameras = [Mock(), Mock()]
    cameras[0].isOpened.return_value = True
    cameras[1].isOpened.return_value = False
    monkeypatch.setattr(recorder.cv2, "VideoCapture", Mock(side_effect=cameras))
    with pytest.raises(RuntimeError, match="camera 1"):
        recorder.open_cameras(recorder.parse_args([]))
    for camera in cameras:
        camera.release.assert_called_once()


def test_writer_open_failure_releases_all(monkeypatch, tmp_path):
    writers = [Mock(), Mock()]
    writers[0].isOpened.return_value = True
    writers[1].isOpened.return_value = False
    monkeypatch.setattr(recorder.cv2, "VideoWriter", Mock(side_effect=writers))
    with pytest.raises(RuntimeError, match="Cannot create video"):
        recorder.Take(tmp_path / "take", recorder.parse_args([]), frames(), 0)
    for writer in writers:
        writer.release.assert_called_once()
    assert (
        json.loads((tmp_path / "take/metadata.json").read_text())["status"]
        == "initialization_error"
    )


@pytest.mark.parametrize("failure", [None, "disconnect", "disk", "interrupt"])
def test_headless_cleanup_and_duration(monkeypatch, tmp_path, failure):
    args = recorder.parse_args(
        [
            "--no-preview",
            "--countdown",
            "0",
            "--duration",
            "0.25",
            "--codec",
            "MJPG",
            "--output",
            str(tmp_path),
        ]
    )
    cameras = [Mock() for _ in range(3)]
    monkeypatch.setattr(recorder, "open_cameras", lambda args: cameras)
    clock = [100.0]
    monkeypatch.setattr(recorder.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(recorder.time, "sleep", lambda delay: None)
    calls = [0]

    def capture(cameras):
        calls[0] += 1
        clock[0] += 0.1
        if calls[0] == 3:
            if failure == "disconnect":
                raise RuntimeError("disconnected")
            if failure == "interrupt":
                raise KeyboardInterrupt
            if failure == "disk":
                clock[0] += 2
        return frames(), [clock[0]] * 3

    monkeypatch.setattr(recorder, "capture_frames", capture)
    monkeypatch.setattr(
        recorder.shutil,
        "disk_usage",
        lambda path: Mock(free=0 if failure == "disk" and calls[0] >= 3 else 1024**3),
    )
    assert recorder.run(args) == (1 if failure in ("disconnect", "disk") else 0)
    for camera in cameras:
        camera.release.assert_called_once()
    metadata = json.loads(next(tmp_path.glob("*/take_001/metadata.json")).read_text())
    assert (
        metadata["status"]
        == {
            None: "duration_reached",
            "disconnect": "error",
            "disk": "error",
            "interrupt": "interrupted",
        }[failure]
    )
    assert metadata["frames"] > 0
    if failure is None:
        assert metadata["frames"] == 8  # ceil(0.25 seconds * 30 fps)


@pytest.mark.parametrize(
    "count, shape",
    [
        (1, (340, 480, 3)),
        (2, (340, 960, 3)),
        (3, (340, 1440, 3)),
        (4, (680, 1440, 3)),
        (7, (1020, 1440, 3)),
    ],
)
def test_preview_does_not_modify_recorded_frames(count, shape):
    source = frames(23, count)
    canvas = recorder.preview(source, list(range(count)), "READY")
    assert canvas.shape == shape
    for index in range(count):
        row, column = divmod(index, min(3, count))
        assert np.all(canvas[row * 340 + 100, column * 480 + 240] == 23)
    if count > 3 and count % 3:
        assert np.all(canvas[-340:, (count % 3) * 480 :] == 0)
    assert all(np.all(frame == 23) for frame in source)


def test_snapshot_and_resolution_change(tmp_path):
    recorder.save_snapshot(tmp_path, [0, 2, 4], frames(50))
    assert len(list(tmp_path.glob("snapshot_*/*.png"))) == 3
    take = recorder.Take(tmp_path / "take", recorder.parse_args(["--codec", "MJPG"]), frames(), 0)
    try:
        with pytest.raises(RuntimeError, match="resolution changed"):
            take.write([np.zeros((24, 32, 3), dtype=np.uint8)] * 3, [0] * 3, 0)
    finally:
        take.close("error")


def test_interactive_multiple_takes_markers_and_snapshots(monkeypatch, tmp_path):
    args = recorder.parse_args(
        [
            "--countdown",
            "0",
            "--codec",
            "MJPG",
            "--output",
            str(tmp_path),
        ]
    )
    cameras = [Mock() for _ in range(3)]
    monkeypatch.setattr(recorder, "open_cameras", lambda args: cameras)
    clock = [10.0]

    def capture(cameras):
        clock[0] += 0.1
        return frames(42), [clock[0]] * 3

    monkeypatch.setattr(recorder, "capture_frames", capture)
    monkeypatch.setattr(recorder.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(recorder.time, "sleep", lambda delay: None)
    monkeypatch.setattr(recorder, "configure_qt_fonts", lambda: None)
    for name in ("namedWindow", "imshow", "destroyAllWindows"):
        monkeypatch.setattr(recorder.cv2, name, Mock())
    monkeypatch.setattr(recorder.cv2, "getWindowProperty", lambda *args: 1)
    keys = [ord("r"), -1, ord("m"), ord("s"), ord("r"), ord("r"), -1, ord("q")]
    monkeypatch.setattr(recorder.cv2, "waitKey", Mock(side_effect=keys))
    monkeypatch.setattr(recorder.shutil, "disk_usage", lambda path: Mock(free=1024**3))
    assert recorder.run(args) == 0
    takes = sorted(tmp_path.glob("*/take_*/metadata.json"))
    assert len(takes) == 2
    assert len(json.loads(takes[0].read_text())["markers"]) == 1
    assert len(list(tmp_path.glob("*/snapshot_*/*.png"))) == 3
    assert all(json.loads(p.read_text())["status"] == "stopped" for p in takes)
    for camera in cameras:
        camera.release.assert_called_once()
