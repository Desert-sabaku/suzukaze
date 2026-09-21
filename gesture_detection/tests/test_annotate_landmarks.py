import cv2
import numpy as np
import pytest
from scripts.annotate_landmarks import (
    annotate,
    load_rows,
    original_point,
    prepare,
    sample_indices,
    save_rows,
)


def test_sampling_and_coordinate_mapping():
    assert sample_indices(11, 3) == [0, 5, 10]
    assert sample_indices(2, 8) == [0, 1]
    with pytest.raises(ValueError):
        sample_indices(0, 8)
    assert original_point(640, 360, 1920, 1080, 1280, 720) == (960, 540)
    assert original_point(5, 720, 1920, 1080, 1280, 720) is None
    assert original_point(-1, 0, 1920, 1080, 1280, 720) is None


def test_extract_save_resume_without_model_or_camera(tmp_path, monkeypatch):
    video = tmp_path / "source.avi"
    writer = cv2.VideoWriter(str(video), cv2.VideoWriter.fourcc(*"MJPG"), 10, (64, 48))
    assert writer.isOpened()
    try:
        for index in range(11):
            writer.write(np.full((48, 64, 3), index * 20, dtype=np.uint8))
    finally:
        writer.release()
    directory = tmp_path / "session"
    prepare(video, directory, 3, None)
    rows = load_rows(directory)
    assert len(rows) == 18
    assert [rows[i]["frame_id"] for i in (0, 6, 12)] == ["0", "5", "10"]
    assert float(rows[6]["timestamp"]) == pytest.approx(0.5)
    image = cv2.imread(str(directory / "frame_000005.png"))
    if image is None:
        raise AssertionError("Failed to read frame image")
    assert image.mean() == pytest.approx(100, abs=2)
    rows[0].update(x_px="10", y_px="20", status="marked")
    rows[1].update(status="uncertain")
    save_rows(directory, rows)
    assert load_rows(directory) == rows
    with pytest.raises(ValueError, match="already exists"):
        prepare(video, directory, 3, None)
    assert load_rows(directory) == rows
    with pytest.raises(ValueError, match="Frame IDs"):
        prepare(video, tmp_path / "invalid", 3, [11])
    assert not (tmp_path / "invalid").exists()

    # Exercise GUI event handling without needing a desktop: click, skip,
    # select a point, clear it, change frame and close.
    callbacks = {}
    monkeypatch.setattr(cv2, "namedWindow", lambda *args: None)
    monkeypatch.setattr(cv2, "setMouseCallback", lambda name, cb: callbacks.update(click=cb))
    monkeypatch.setattr(cv2, "imshow", lambda *args: None)
    monkeypatch.setattr(cv2, "destroyAllWindows", lambda: None)
    monkeypatch.setattr(cv2, "getWindowProperty", lambda *args: 1)
    events = iter([-1, ord("u"), ord("3"), ord("c"), ord("n"), ord("q")])

    def wait_key(delay):
        key = next(events)
        if key == -1:
            callbacks["click"](cv2.EVENT_LBUTTONDOWN, 16, 12, 0, None)
        return key

    monkeypatch.setattr(cv2, "waitKey", wait_key)
    annotate(directory, 32, 24)
    updated = load_rows(directory)
    assert updated[2]["status"] == "pending"
    assert updated[3]["status"] == "uncertain"
    assert updated[0] == rows[0]

    # Bulk absence must clear existing coordinates, affect only this frame,
    # persist through reload, and stay on the current frame on repeated A.
    events = iter([ord("a"), ord("a"), ord("q")])
    annotate(directory, 32, 24)
    absent = load_rows(directory)
    assert all(row["status"] == "absent" for row in absent[:6])
    assert all(row["x_px"] == row["y_px"] == "" for row in absent[:6])
    assert absent[6:] == updated[6:]

    # Resume skips completed absent points; P returns to that frame and R
    # makes every point editable again without modifying neighbouring frames.
    events = iter([ord("p"), ord("r"), ord("q")])
    annotate(directory, 32, 24)
    reset = load_rows(directory)
    assert all(row["status"] == "pending" for row in reset[:6])
    assert all(row["x_px"] == row["y_px"] == "" for row in reset[:6])
    assert reset[6:] == absent[6:]
