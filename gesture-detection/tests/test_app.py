import unittest
from unittest.mock import MagicMock, call, patch

import cv2
from gesture_detection.app import BottleState, GestureApplication, Landmark, PoseResult
from gesture_detection.config import CAMERA_BACKEND, CAMERA_FOURCC


class OpenCaptureTest(unittest.TestCase):
    @patch("gesture_detection.app.VIDEO_SOURCE", "/tmp/sample.mp4")
    @patch("gesture_detection.app.cv2.VideoCapture")
    def test_uses_configured_video_source(self, video_capture):
        configured = MagicMock()
        configured.isOpened.return_value = True
        video_capture.return_value = configured

        result = GestureApplication()._open_capture()

        self.assertIs(result, configured)
        video_capture.assert_called_once_with("/tmp/sample.mp4")

    @patch("gesture_detection.app.VIDEO_SOURCE", "/tmp/missing.mp4")
    @patch("gesture_detection.app.cv2.VideoCapture")
    def test_raises_when_configured_video_source_cannot_be_opened(self, video_capture):
        configured = MagicMock()
        configured.isOpened.return_value = False
        video_capture.return_value = configured

        with self.assertRaisesRegex(RuntimeError, "Unable to open video file /tmp/missing.mp4"):
            GestureApplication()._open_capture()

        configured.release.assert_called_once_with()

    @patch("gesture_detection.app.cv2.VideoCapture")
    def test_uses_configured_camera_settings(self, video_capture):
        configured = MagicMock()
        configured.isOpened.return_value = True
        configured.set.return_value = True
        video_capture.return_value = configured

        result = GestureApplication(camera_index=2)._open_capture()

        self.assertIs(result, configured)
        video_capture.assert_called_once_with(2, CAMERA_BACKEND)
        configured.set.assert_called_once_with(
            cv2.CAP_PROP_FOURCC,
            cv2.VideoWriter.fourcc(*CAMERA_FOURCC),
        )

    @patch("gesture_detection.app.cv2.VideoCapture")
    def test_falls_back_to_default_settings(self, video_capture):
        configured = MagicMock()
        configured.isOpened.return_value = True
        configured.set.return_value = False
        default = MagicMock()
        default.isOpened.return_value = True
        video_capture.side_effect = [configured, default]

        result = GestureApplication(camera_index=1)._open_capture()

        self.assertIs(result, default)
        self.assertEqual(
            video_capture.call_args_list,
            [call(1, CAMERA_BACKEND), call(1)],
        )
        configured.release.assert_called_once_with()

    @patch("gesture_detection.app.cv2.VideoCapture")
    def test_raises_when_configured_and_default_settings_fail(self, video_capture):
        configured = MagicMock()
        configured.isOpened.return_value = False
        default = MagicMock()
        default.isOpened.return_value = False
        video_capture.side_effect = [configured, default]

        with self.assertRaisesRegex(RuntimeError, "Unable to open camera 3"):
            GestureApplication(camera_index=3)._open_capture()

        configured.release.assert_called_once_with()
        default.release.assert_called_once_with()


class BothHandsRamuneTests(unittest.TestCase):
    def test_either_visible_hand_can_touch_bottle(self):
        import numpy as np

        for index in (15, 16):
            with self.subTest(wrist_index=index):
                landmarks: list[Landmark] = [(0.0, 0.0, 0.0)] * 33
                landmarks[index] = (0.5, 0.5, 1.0)
                pose: PoseResult = {
                    "landmarks": landmarks,
                    "messages": [],
                    "selected_action": "NONE",
                    "relaxing_state": False,
                }
                bottle_state: BottleState = {
                    "box": None,
                    "confidence": 0.0,
                    "last_seen": 0.0,
                }
                with (
                    patch.object(
                        GestureApplication,
                        "_active_bottle_box",
                        return_value=(40, 40, 60, 60),
                    ),
                    patch.object(GestureApplication, "_draw_bottle"),
                    patch.object(GestureApplication, "_draw_action") as draw_action,
                ):
                    GestureApplication._annotate_frame(
                        np.zeros((100, 100, 3), dtype=np.uint8),
                        pose,
                        bottle_state,
                    )
                self.assertEqual(draw_action.call_args.args[1], "RAMUNE")
