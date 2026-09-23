from pathlib import Path

import cv2
import numpy as np
import pytest
from scripts.annotate_landmarks import (
    annotate,
    default_annotation_directory,
    load_rows,
    original_point,
    prepare,
    resolve_resume_directory,
    sample_indices,
    save_rows,
)


def test_sampling_and_coordinate_mapping():
    assert sample_indices(11, 3) == [0, 5, 10]
    assert original_point(640, 360, 1920, 1080, 1280, 720) == (960, 540)
    assert original_point(-1, 0, 1920, 1080, 1280, 720) is None


def test_annotation_and_resume_paths(tmp_path):
    video = Path("shared/videos/bright-behind-the-screen/aogi1_3-8.mp4")
    expected = tmp_path / "shared" / "annotations" / "bright-behind-the-screen" / "aogi1_3-8"
    assert default_annotation_directory(video, tmp_path) == expected
    assert resolve_resume_directory(video, tmp_path) == expected
    assert resolve_resume_directory(expected / "annotations.csv", tmp_path) == expected
    assert resolve_resume_directory(expected, tmp_path) == expected


def test_extract_resume_and_absent(tmp_path, monkeypatch):
    video = tmp_path / "source.avi"
    writer = cv2.VideoWriter(str(video), cv2.VideoWriter.fourcc(*"MJPG"), 10, (64, 48))
    assert writer.isOpened()
    for index in range(11):
        writer.write(np.full((48, 64, 3), index * 20, dtype=np.uint8))
    writer.release()
    directory = tmp_path / "session"
    prepare(video, directory, 3, None)
    rows = load_rows(directory)
    rows[0].update(x_px="10", y_px="20", status="marked")
    save_rows(directory, rows)

    callbacks = {}
    monkeypatch.setattr(cv2, "namedWindow", lambda *args: None)
    monkeypatch.setattr(cv2, "setMouseCallback", lambda name, cb: callbacks.update(click=cb))
    monkeypatch.setattr(cv2, "imshow", lambda *args: None)
    monkeypatch.setattr(cv2, "destroyAllWindows", lambda: None)
    monkeypatch.setattr(cv2, "getWindowProperty", lambda *args: 1)
    events = iter([ord("a"), ord("q")])
    monkeypatch.setattr(cv2, "waitKey", lambda delay: next(events))
    annotate(directory, 32, 24)
    absent = load_rows(directory)
    assert all(row["status"] == "absent" for row in absent[:6])
    assert all(not row["x_px"] and not row["y_px"] for row in absent[:6])

    events = iter([ord("p"), ord("r"), ord("q")])
    annotate(directory, 32, 24)
    reset = load_rows(directory)
    assert all(row["status"] == "pending" for row in reset[:6])
    assert reset[6:] == absent[6:]

    with pytest.raises(ValueError, match="already exists"):
        prepare(video, directory, 3, None)
