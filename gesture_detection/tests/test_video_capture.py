import csv
import json
import threading
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


def test_capture_samples_latest_without_waiting_for_next_frame():
    cameras = [Mock(), Mock()]
    cameras[0].latest.return_value = (frames(10, 1)[0], 10.0)
    cameras[1].latest.return_value = (frames(20, 1)[0], 10.1)
    result, stamps = recorder.capture_frames(cameras)
    assert stamps == [10.0, 10.1]
    assert [image.mean() for image in result] == [10, 20]


def test_reader_discards_backlog_and_owns_frame_buffer():
    camera = Mock()
    drained = threading.Event()
    unblock = threading.Event()
    reused = frames(10, 1)[0]
    calls = [0]

    def read():
        calls[0] += 1
        if calls[0] <= 2:
            reused.fill(calls[0] * 10)
            return True, reused
        drained.set()
        assert unblock.wait(2)
        return False, None

    camera.read.side_effect = read
    reader = recorder.CameraReader(camera, 7)
    try:
        assert drained.wait(2)
        reused.fill(99)
        image, stamp = reader.latest()
        assert np.all(image == 20)
        assert stamp > 0
        assert reader.latest()[0] is image
    finally:
        reader._stop.set()
        unblock.set()
        reader.release()
    camera.release.assert_called_once()


def test_reader_reports_capture_failure():
    camera = Mock()
    camera.read.return_value = (False, None)
    reader = recorder.CameraReader(camera, 4)
    try:
        with pytest.raises(RuntimeError, match="Camera 4: read failed"):
            reader.latest()
    finally:
        reader.release()
    camera.release.assert_called_once()


def test_reader_timeout_and_stale_frames(monkeypatch):
    camera = Mock()
    unblock = threading.Event()
    camera.read.side_effect = lambda: (unblock.wait(2) and False, None)
    reader = recorder.CameraReader(camera, 3)
    try:
        with pytest.raises(RuntimeError, match="first frame"):
            reader.latest(timeout=0.01)
        with reader._lock:
            reader._latest = (frames(1, 1)[0], 1.0)
        reader._ready.set()
        monkeypatch.setattr(recorder.time, "monotonic", lambda: 10.0)
        with pytest.raises(RuntimeError, match="no new frames"):
            reader.latest()
    finally:
        reader._stop.set()
        unblock.set()
        reader.release()


def test_camera_open_failure_releases_all(monkeypatch):
    cameras = [Mock(), Mock()]
    cameras[0].get.return_value = 0
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


@pytest.mark.parametrize("qt_save_error", [False, True])
def test_interactive_multiple_takes_markers_and_snapshots(monkeypatch, tmp_path, qt_save_error):
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
    window_mock = Mock()
    monkeypatch.setattr(recorder.cv2, "namedWindow", window_mock)
    for name in ("imshow", "destroyAllWindows"):
        monkeypatch.setattr(recorder.cv2, name, Mock())
    monkeypatch.setattr(recorder.cv2, "getWindowProperty", lambda *args: 1)
    keys: list[int | cv2.error] = [
        ord("r"),
        -1,
        ord("m"),
        ord("s"),
        ord("r"),
        ord("r"),
        -1,
        ord("q"),
    ]
    if qt_save_error:
        keys.insert(2, cv2.error("file extension not recognized in function 'saveView'"))
    monkeypatch.setattr(recorder.cv2, "waitKey", Mock(side_effect=keys))
    monkeypatch.setattr(recorder.shutil, "disk_usage", lambda path: Mock(free=1024**3))
    assert recorder.run(args) == 0
    window_mock.assert_called_once_with(recorder.WINDOW, cv2.WINDOW_NORMAL | cv2.WINDOW_GUI_NORMAL)
    takes = sorted(tmp_path.glob("*/take_*/metadata.json"))
    assert len(takes) == 2
    assert len(json.loads(takes[0].read_text())["markers"]) == 1
    assert len(list(tmp_path.glob("*/snapshot_*/*.png"))) == 3
    assert all(json.loads(p.read_text())["status"] == "stopped" for p in takes)
    for camera in cameras:
        camera.release.assert_called_once()


@pytest.mark.parametrize("input_format", ["auto", "MJPG", "YUYV"])
def test_camera_input_mode_and_reader_ownership(monkeypatch, input_format):
    camera = Mock()
    camera.get.return_value = 0
    constructor = Mock(return_value=camera)
    reader = Mock()
    factory = Mock(return_value=reader)
    monkeypatch.setattr(recorder.cv2, "VideoCapture", constructor)
    monkeypatch.setattr(recorder, "CameraReader", factory)
    args = recorder.parse_args(
        ["--cameras", "2", "--input-format", input_format, "--backend", "v4l2"]
    )
    assert recorder.open_cameras(args) == [reader]
    constructor.assert_called_once_with(2, cv2.CAP_V4L2)
    factory.assert_called_once_with(camera, 2)
    format_calls = [
        call for call in camera.set.call_args_list if call.args[0] == cv2.CAP_PROP_FOURCC
    ]
    assert len(format_calls) == (0 if input_format == "auto" else 1)
    camera.release.assert_not_called()


def test_preview_preserves_bottom_of_input_image():
    source = np.full((720, 1280, 3), (30, 100, 200), dtype=np.uint8)
    source[360:] = (220, 100, 30)
    canvas = recorder.preview([source], [0], "READY")
    assert np.all(canvas[60, 240] == (30, 100, 200))
    assert np.all(canvas[290, 240] == (220, 100, 30))


def test_preview_save_error_is_nonfatal(monkeypatch, capsys):
    error = cv2.error("file extension not recognized in function 'saveView'")
    monkeypatch.setattr(recorder.cv2, "waitKey", Mock(side_effect=[error, ord("s")]))
    assert recorder.read_preview_key() == -1
    assert "Recording continues" in capsys.readouterr().err
    assert recorder.read_preview_key() == ord("s")


def test_other_preview_errors_are_not_suppressed(monkeypatch):
    monkeypatch.setattr(recorder.cv2, "waitKey", Mock(side_effect=cv2.error("GUI failure")))
    with pytest.raises(cv2.error, match="GUI failure"):
        recorder.read_preview_key()


def test_default_output_uses_project_shared_videos(monkeypatch, tmp_path):
    from pathlib import Path

    monkeypatch.chdir(tmp_path)
    expected = Path(recorder.__file__).resolve().parents[1] / "shared" / "videos"
    assert recorder.parse_args([]).output == expected
    assert recorder.parse_args(["--output", "custom"]).output == Path("custom")
