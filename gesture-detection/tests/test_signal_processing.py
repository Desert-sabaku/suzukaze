import unittest

import numpy as np
from gesture_detection.signal_processing import resample_time_window


class ResampleTimeWindowTests(unittest.TestCase):
    def test_trims_by_elapsed_time_and_interpolates_uniformly(self):
        timestamps = np.array([0.0, 0.1, 0.23, 0.31, 0.5, 0.71, 0.94, 1.2, 1.45])
        values = (timestamps * 2.0 + 1.0).astype(np.float32)

        sampled_values, sampled_timestamps = resample_time_window(
            values, timestamps, window_seconds=1.0
        )

        self.assertEqual(len(sampled_values), 5)
        self.assertAlmostEqual(sampled_timestamps[0], 0.45)
        self.assertAlmostEqual(sampled_timestamps[-1], 1.45)
        np.testing.assert_allclose(
            np.diff(sampled_timestamps), np.full(4, 0.25), rtol=0, atol=1e-12
        )
        np.testing.assert_allclose(
            sampled_values, sampled_timestamps * 2.0 + 1.0, rtol=0, atol=1e-6
        )

    def test_uses_available_duration_when_history_is_shorter_than_window(self):
        timestamps = np.array([3.0, 3.12, 3.25, 3.4])
        values = np.array([0.0, 1.0, 0.0, -1.0], dtype=np.float32)

        _, sampled_timestamps = resample_time_window(values, timestamps, window_seconds=1.0)

        self.assertEqual(len(sampled_timestamps), len(timestamps))
        self.assertEqual(sampled_timestamps[0], timestamps[0])
        np.testing.assert_allclose(
            np.diff(sampled_timestamps),
            np.full(3, (timestamps[-1] - timestamps[0]) / 3),
        )


if __name__ == "__main__":
    unittest.main()
