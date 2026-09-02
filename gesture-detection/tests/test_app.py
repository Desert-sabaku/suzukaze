import unittest
from unittest.mock import MagicMock, call, patch

import cv2

from gesture_detection.app import GestureApplication
from gesture_detection.config import CAMERA_BACKEND, CAMERA_FOURCC


class OpenCaptureTest(unittest.TestCase):
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
    def test_raises_when_configured_and_default_settings_fail(
        self, video_capture
    ):
        configured = MagicMock()
        configured.isOpened.return_value = False
        default = MagicMock()
        default.isOpened.return_value = False
        video_capture.side_effect = [configured, default]

        with self.assertRaisesRegex(RuntimeError, "Unable to open camera 3"):
            GestureApplication(camera_index=3)._open_capture()

        configured.release.assert_called_once_with()
        default.release.assert_called_once_with()
