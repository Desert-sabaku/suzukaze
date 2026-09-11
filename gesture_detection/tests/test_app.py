import unittest
from unittest.mock import MagicMock, call, patch

import cv2
from modules.app import BottleState, GestureApplication, Landmark, PoseResult
from modules.config import CAMERA_BACKEND, CAMERA_FOURCC


class OpenCaptureTest(unittest.TestCase):
    @patch("modules.app.VIDEO_SOURCE", "/tmp/sample.mp4")
    @patch("modules.app.cv2.VideoCapture")
    def test_uses_configured_video_source(self, video_capture):
        configured = MagicMock()
        configured.isOpened.return_value = True
        video_capture.return_value = configured

        result = GestureApplication()._open_capture()

        self.assertIs(result, configured)
        video_capture.assert_called_once_with("/tmp/sample.mp4")

    @patch("modules.app.VIDEO_SOURCE", "/tmp/missing.mp4")
    @patch("modules.app.cv2.VideoCapture")
    def test_raises_when_configured_video_source_cannot_be_opened(self, video_capture):
        configured = MagicMock()
        configured.isOpened.return_value = False
        video_capture.return_value = configured

        with self.assertRaisesRegex(RuntimeError, "Unable to open video file /tmp/missing.mp4"):
            GestureApplication()._open_capture()

        configured.release.assert_called_once_with()

    @patch("modules.app.cv2.VideoCapture")
    @patch("modules.app.VIDEO_SOURCE", None)
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

    @patch("modules.app.cv2.VideoCapture")
    @patch("modules.app.VIDEO_SOURCE", None)
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

    @patch("modules.app.cv2.VideoCapture")
    @patch("modules.app.VIDEO_SOURCE", None)
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

    @patch("modules.app.VIDEO_SOURCE", "/tmp/sample.mp4")
    @patch("modules.app.VIDEO_OUTPUT_PATH", "/tmp/output.mp4")
    @patch("modules.app.cv2.VideoWriter")
    def test_opens_output_for_video_source(self, video_writer):
        capture = MagicMock()
        capture.get.side_effect = {
            cv2.CAP_PROP_FRAME_WIDTH: 640,
            cv2.CAP_PROP_FRAME_HEIGHT: 480,
            cv2.CAP_PROP_FPS: 30,
        }.get
        output = MagicMock()
        output.isOpened.return_value = True
        video_writer.return_value = output

        result = GestureApplication._open_output(capture)

        self.assertIs(result, output)
        video_writer.assert_called_once_with(
            "/tmp/output.mp4",
            cv2.VideoWriter.fourcc(*"mp4v"),
            30,
            (640, 480),
        )

    @patch("modules.app.VIDEO_SOURCE", None)
    @patch("modules.app.cv2.VideoWriter")
    def test_does_not_open_output_for_camera_source(self, video_writer):
        self.assertIsNone(GestureApplication._open_output(MagicMock()))
        video_writer.assert_not_called()


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


class RunLifecycleTests(unittest.TestCase):
    def test_escape_flushes_output_and_stops_workers(self):
        import numpy as np

        app = GestureApplication()
        capture = MagicMock()
        capture.read.return_value = (True, np.zeros((4, 5, 3), dtype=np.uint8))
        app.pose_process = MagicMock()
        app.yolo_process = MagicMock()
        with (
            patch.object(app, "_open_capture", return_value=capture),
            patch.object(app, "_open_output", return_value=MagicMock()),
            patch.object(app, "_start_workers"),
            patch.object(app, "_stop_workers") as stop,
            patch("modules.app.AsyncVideoWriter") as writer,
            patch("modules.app.cv2.imshow"),
            patch("modules.app.cv2.waitKey", return_value=27),
            patch("modules.app.cv2.destroyAllWindows"),
        ):
            app.run()
        writer.return_value.write.assert_called_once()
        writer.return_value.release.assert_called_once()
        capture.release.assert_called_once()
        stop.assert_called_once()
        app.pose_result_queue.close()
        app.yolo_result_queue.close()

    def test_partial_worker_start_failure_cleans_up(self):
        import numpy as np

        app = GestureApplication()
        capture = MagicMock()
        capture.read.return_value = (True, np.zeros((4, 5, 3), dtype=np.uint8))
        with (
            patch.object(app, "_open_capture", return_value=capture),
            patch.object(app, "_start_workers", side_effect=RuntimeError("start failed")),
            patch.object(app, "_stop_workers") as stop,
            patch("modules.app.cv2.destroyAllWindows"),
        ):
            with self.assertRaisesRegex(RuntimeError, "start failed"):
                app.run()
        capture.release.assert_called_once()
        stop.assert_called_once()
        app.pose_result_queue.close()
        app.yolo_result_queue.close()
