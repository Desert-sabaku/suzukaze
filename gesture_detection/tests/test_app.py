import unittest
from unittest.mock import MagicMock, call, patch

import cv2

from gesture_detection.app import GestureApplication, PoseResult
from gesture_detection.config import CAMERA_BACKEND, CAMERA_FOURCC, WINDOW_TITLE


def test_delivery_is_disabled_for_video_even_when_enabled():
    with patch("gesture_detection.app.mp.Process") as process:
        for source, enabled, expected in [
            (None, True, True),
            (None, False, False),
            ("movie.mp4", True, False),
        ]:
            with (
                patch("gesture_detection.app.VIDEO_SOURCE", source),
                patch("gesture_detection.app.GESTURE_DELIVERY_ENABLED", enabled),
                patch("gesture_detection.app.mp.Queue"),
            ):
                app = GestureApplication()
                app._start_workers()
                assert process.call_args.kwargs["args"][2] is expected


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
    @patch("gesture_detection.app.VIDEO_SOURCE", None)
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
    @patch("gesture_detection.app.VIDEO_SOURCE", None)
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
    @patch("gesture_detection.app.VIDEO_SOURCE", None)
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

    @patch("gesture_detection.app.VIDEO_SOURCE", "/tmp/sample.mp4")
    @patch("gesture_detection.app.VIDEO_OUTPUT_PATH", "/tmp/output.mp4")
    @patch("gesture_detection.app.cv2.VideoWriter")
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

    @patch("gesture_detection.app.VIDEO_SOURCE", None)
    @patch("gesture_detection.app.cv2.VideoWriter")
    def test_does_not_open_output_for_camera_source(self, video_writer):
        self.assertIsNone(GestureApplication._open_output(MagicMock()))
        video_writer.assert_not_called()


class RamuneActionTests(unittest.TestCase):
    def test_ramune_uses_pose_result_without_bottle(self):
        import numpy as np

        pose: PoseResult = {
            "landmarks": [],
            "selected_action": "RAMUNE",
            "relaxing_state": False,
            "ramune_state": "OPENED",
        }
        with (
            patch.object(GestureApplication, "_draw_action") as draw,
            patch("gesture_detection.app.draw_ramune_guide") as guide,
        ):
            GestureApplication._annotate_frame(np.zeros((480, 640, 3), dtype=np.uint8), pose)
        self.assertEqual(draw.call_args.args[1], "RAMUNE")
        guide.assert_called_once()
        self.assertEqual(guide.call_args.args[1], "OPENED")

    def test_no_motion_does_not_select_ramune(self):
        pose: PoseResult = {
            "landmarks": [],
            "selected_action": "NONE",
            "relaxing_state": False,
        }
        self.assertEqual(GestureApplication._primary_action(pose), "NONE")


@patch("gesture_detection.app.VIDEO_SOURCE", None)
class RunLifecycleTests(unittest.TestCase):
    def test_escape_flushes_output_and_stops_workers(self):
        import numpy as np

        app = GestureApplication()
        capture = MagicMock()
        capture.read.return_value = (True, np.zeros((4, 5, 3), dtype=np.uint8))
        app.pose_process = MagicMock()
        with (
            patch.object(app, "_open_capture", return_value=capture),
            patch.object(app, "_open_output", return_value=MagicMock()),
            patch.object(app, "_start_workers"),
            patch.object(app, "_stop_workers") as stop,
            patch("gesture_detection.app.AsyncVideoWriter") as writer,
            patch("gesture_detection.app.cv2.imshow"),
            patch("gesture_detection.app.cv2.waitKey", return_value=27),
            patch("gesture_detection.app.cv2.destroyAllWindows"),
        ):
            app.run()
        writer.return_value.write.assert_called_once()
        writer.return_value.release.assert_called_once()
        capture.release.assert_called_once()
        stop.assert_called_once()
        app.pose_result_queue.close()

    def test_window_close_stops_workers(self):
        import numpy as np

        app = GestureApplication()
        capture = MagicMock()
        capture.read.return_value = (True, np.zeros((4, 5, 3), dtype=np.uint8))
        app.pose_process = MagicMock()
        with (
            patch.object(app, "_open_capture", return_value=capture),
            patch.object(app, "_open_output", return_value=None),
            patch.object(app, "_start_workers"),
            patch.object(app, "_stop_workers") as stop,
            patch("gesture_detection.app.cv2.imshow"),
            patch("gesture_detection.app.cv2.waitKey", return_value=-1),
            patch("gesture_detection.app.cv2.getWindowProperty", return_value=0) as visibility,
            patch("gesture_detection.app.cv2.destroyAllWindows"),
        ):
            app.run()
        visibility.assert_called_once_with(WINDOW_TITLE, cv2.WND_PROP_VISIBLE)
        capture.release.assert_called_once()
        stop.assert_called_once()
        app.pose_result_queue.close()

    def test_missing_closed_window_is_treated_as_close(self):
        app = GestureApplication()
        app._window_created = True
        with (
            patch("gesture_detection.app.cv2.waitKey", return_value=-1),
            patch("gesture_detection.app.cv2.getWindowProperty", side_effect=cv2.error),
        ):
            self.assertTrue(app._exit_requested())
        app.pose_result_queue.close()

    def test_partial_worker_start_failure_cleans_up(self):
        import numpy as np

        app = GestureApplication()
        capture = MagicMock()
        capture.read.return_value = (True, np.zeros((4, 5, 3), dtype=np.uint8))
        with (
            patch.object(app, "_open_capture", return_value=capture),
            patch.object(app, "_start_workers", side_effect=RuntimeError("start failed")),
            patch.object(app, "_stop_workers") as stop,
            patch("gesture_detection.app.cv2.destroyAllWindows"),
        ):
            with self.assertRaisesRegex(RuntimeError, "start failed"):
                app.run()
        capture.release.assert_called_once()
        stop.assert_called_once()
        app.pose_result_queue.close()


class FrameClockTests(unittest.TestCase):
    def test_video_positions_and_fallback(self):
        import numpy as np

        from gesture_detection.app import FrameClock

        capture = MagicMock()
        positions = iter([0.0, 40.0, 40.0, float("nan"), -1.0, 240.0])
        capture.get.side_effect = lambda prop: (
            next(positions) if prop == cv2.CAP_PROP_POS_MSEC else 25.0
        )
        clock = FrameClock(is_video=True)
        with patch("gesture_detection.app.time.monotonic", side_effect=AssertionError):
            actual = [clock.timestamp(capture) for _ in range(6)]
        np.testing.assert_allclose(actual, [0.0, 0.04, 0.08, 0.12, 0.16, 0.24])

    def test_invalid_fps(self):
        from gesture_detection.app import FPS, FrameClock

        for fps in (0.0, -1.0, float("nan"), float("inf")):
            capture = MagicMock()
            capture.get.side_effect = lambda prop, fps=fps: (
                float("nan") if prop == cv2.CAP_PROP_POS_MSEC else fps
            )
            clock = FrameClock(is_video=True)
            self.assertEqual(clock.timestamp(capture), 0.0)
            self.assertAlmostEqual(clock.timestamp(capture), 1 / FPS)

    def test_camera_capture_time(self):
        from gesture_detection.app import FrameClock

        capture = MagicMock()
        with patch("gesture_detection.app.time.monotonic", return_value=123.45):
            self.assertEqual(FrameClock(is_video=False).timestamp(capture), 123.45)
        capture.get.assert_not_called()


class SequentialVideoTests(unittest.TestCase):
    def test_every_frame_is_inferred_and_saved_with_its_own_result(self):
        import queue
        import threading

        import numpy as np

        app = GestureApplication()
        app.pose_result_queue.close()
        results = queue.Queue()
        app.pose_result_queue = MagicMock(wraps=results)
        app.pose_process = MagicMock()
        inferred = []
        saved = []
        timestamps = []
        worker = None
        frames = [np.full((4, 5, 3), index, dtype=np.uint8) for index in range(4)]
        capture = MagicMock()
        reads = 0

        def read():
            nonlocal reads
            # Reading ahead before inference AND saving would violate evaluation order.
            self.assertEqual(len(saved), reads)
            if reads == len(frames):
                return False, None
            frame = frames[reads]
            reads += 1
            return True, frame

        def infer():
            assert app.pose_frame_queue is not None
            while True:
                sample = app.pose_frame_queue.get()
                if sample is None:
                    return
                frame, timestamp, frame_id = sample
                inferred.append(int(frame[0, 0, 0]))
                self.assertEqual(frame_id, inferred[-1])
                timestamps.append(timestamp)
                results.put(
                    {"frame_index": inferred[-1], "frame_id": frame_id, "timestamp": timestamp}
                )

        def start():
            nonlocal worker
            worker = threading.Thread(target=infer, daemon=True)
            worker.start()

        def stop():
            assert app.pose_frame_queue is not None
            assert worker is not None
            app.pose_frame_queue.close()
            worker.join(timeout=5)
            self.assertFalse(worker.is_alive())

        def annotate(frame, result):
            self.assertEqual(int(frame[0, 0, 0]), result["frame_index"])
            return frame.copy()

        capture.read.side_effect = read
        capture.get.side_effect = lambda prop: (reads - 1) * 40.0
        with (
            patch("gesture_detection.app.VIDEO_SOURCE", "/tmp/video.mp4"),
            patch.object(app, "_open_capture", return_value=capture),
            patch.object(app, "_open_output", return_value=MagicMock()),
            patch.object(app, "_start_workers", side_effect=start),
            patch.object(app, "_stop_workers", side_effect=stop),
            patch.object(app, "_annotate_frame", side_effect=annotate),
            patch("gesture_detection.app.AsyncVideoWriter") as writer,
            patch("gesture_detection.app.cv2.putText"),
            patch("gesture_detection.app.cv2.imshow"),
            patch("gesture_detection.app.cv2.waitKey", return_value=-1),
            patch("gesture_detection.app.cv2.getWindowProperty", return_value=1),
            patch("gesture_detection.app.cv2.destroyAllWindows"),
        ):
            writer.return_value.write.side_effect = lambda frame: saved.append(int(frame[0, 0, 0]))
            app.run()
        self.assertEqual(inferred, [0, 1, 2, 3])
        self.assertEqual(saved, inferred)
        np.testing.assert_allclose(timestamps, [0.0, 0.04, 0.08, 0.12])
        writer.return_value.release.assert_called_once()
        capture.release.assert_called_once()

    def make_app(self):
        app = GestureApplication()
        app.pose_result_queue.close()
        app.pose_result_queue = MagicMock()
        app.pose_frame_queue = MagicMock()
        app.pose_process = MagicMock()
        return app, app.pose_frame_queue, app.pose_result_queue, app.pose_process

    def test_busy_mailbox_and_slow_inference_do_not_skip_or_republish(self):
        import queue

        app, frames, results, process = self.make_app()
        frames.publish.side_effect = [False, True]
        expected = {"selected_action": "RAMUNE", "frame_id": 7, "timestamp": 0.25}
        results.get.side_effect = [queue.Empty, expected]
        with patch("gesture_detection.app.cv2.waitKey", return_value=-1):
            self.assertIs(app._process_video_frame(MagicMock(), 0.25, 7), expected)
        self.assertEqual(frames.publish.call_count, 2)
        self.assertEqual(results.get.call_count, 2)

    def test_worker_failure_while_waiting_raises(self):
        import queue

        app, frames, results, process = self.make_app()
        process.is_alive.side_effect = [True, False]
        results.get.side_effect = queue.Empty
        with patch("gesture_detection.app.cv2.waitKey", return_value=-1):
            with self.assertRaisesRegex(RuntimeError, "Pose worker process"):
                app._process_video_frame(MagicMock(), 0.0, 0)

    def test_escape_while_waiting_cancels_pending_frame(self):
        import queue

        app, frames, results, process = self.make_app()
        results.get.side_effect = queue.Empty
        with patch("gesture_detection.app.cv2.waitKey", return_value=27):
            self.assertIsNone(app._process_video_frame(MagicMock(), 0.0, 0))

    def test_video_rejects_result_from_another_frame(self):
        app, frames, results, process = self.make_app()
        for result in (
            {"frame_id": 6, "timestamp": 0.25},
            {"frame_id": 7, "timestamp": 0.2},
        ):
            results.get.return_value = result
            with self.assertRaisesRegex(RuntimeError, "does not match"):
                app._process_video_frame(MagicMock(), 0.25, 7)
