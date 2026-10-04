from unittest.mock import Mock, patch

import cv2
import numpy as np

from gesture_detection import config
from gesture_detection.camera_selection import select_camera_indices


def test_selects_two_distinct_cameras_in_role_order(monkeypatch):
    monkeypatch.setattr(config, "CAMERA_SCAN_MAX_INDEX", 2)
    frame = np.zeros((48, 64, 3), dtype=np.uint8)
    cameras = [Mock() for _ in range(3)]
    for camera in cameras:
        camera.isOpened.return_value = True
        camera.read.return_value = True, frame
    with (
        patch("gesture_detection.camera_selection.cv2.VideoCapture", side_effect=cameras),
        patch("gesture_detection.camera_selection.cv2.imshow") as show,
        patch(
            "gesture_detection.camera_selection.cv2.waitKey",
            side_effect=[ord("2"), ord("2"), ord("0")],
        ),
        patch("gesture_detection.camera_selection.cv2.getWindowProperty", return_value=1),
        patch("gesture_detection.camera_selection.cv2.destroyWindow") as destroy,
    ):
        assert select_camera_indices(2) == (2, 0)
    assert show.call_count == 3
    for camera in cameras:
        camera.release.assert_called_once()
    destroy.assert_called_once()


def test_cancel_releases_scanned_cameras(monkeypatch):
    monkeypatch.setattr(config, "CAMERA_SCAN_MAX_INDEX", 0)
    camera = Mock()
    camera.isOpened.return_value = True
    camera.read.return_value = True, np.zeros((4, 4, 3), dtype=np.uint8)
    with (
        patch("gesture_detection.camera_selection.cv2.VideoCapture", return_value=camera),
        patch("gesture_detection.camera_selection.cv2.imshow"),
        patch("gesture_detection.camera_selection.cv2.waitKey", return_value=27),
        patch("gesture_detection.camera_selection.cv2.destroyWindow"),
    ):
        assert select_camera_indices(1) is None
    camera.release.assert_called_once()


def test_closed_selection_window_releases_cameras(monkeypatch):
    monkeypatch.setattr(config, "CAMERA_SCAN_MAX_INDEX", 0)
    camera = Mock()
    camera.isOpened.return_value = True
    camera.read.return_value = True, np.zeros((4, 4, 3), dtype=np.uint8)
    with (
        patch("gesture_detection.camera_selection.cv2.VideoCapture", return_value=camera),
        patch("gesture_detection.camera_selection.cv2.imshow"),
        patch("gesture_detection.camera_selection.cv2.waitKey", return_value=-1),
        patch("gesture_detection.camera_selection.cv2.getWindowProperty", return_value=0),
        patch("gesture_detection.camera_selection.cv2.destroyWindow", side_effect=cv2.error),
    ):
        assert select_camera_indices(1) is None
    camera.release.assert_called_once()
