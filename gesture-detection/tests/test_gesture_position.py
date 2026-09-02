import unittest
from types import SimpleNamespace

from gesture_detection.gesture_position import (
    is_uchimizu_ready_motion,
    normalized_wrist_distances,
)


def make_landmarks(wrist):
    landmarks = [SimpleNamespace(x=0.0, y=0.0) for _ in range(33)]
    positions = {
        0: (0.5, 0.2),
        11: (0.4, 0.4),
        12: (0.6, 0.4),
        16: wrist,
        23: (0.43, 0.7),
        24: (0.57, 0.7),
    }
    for index, (x, y) in positions.items():
        landmarks[index] = SimpleNamespace(x=x, y=y)
    return landmarks


class WristPositionTests(unittest.TestCase):
    def test_face_position_is_closer_to_face_than_torso(self):
        face_distance, torso_distance = normalized_wrist_distances(
            make_landmarks((0.52, 0.22))
        )

        self.assertLess(face_distance, torso_distance)

    def test_torso_position_is_closer_to_torso_than_face(self):
        face_distance, torso_distance = normalized_wrist_distances(
            make_landmarks((0.65, 0.55))
        )

        self.assertLess(torso_distance, face_distance)


class UchimizuStateTests(unittest.TestCase):
    def test_motion_near_face_does_not_enter_ready(self):
        self.assertFalse(is_uchimizu_ready_motion(0.05, 0.02, 0.5, 0.8))

    def test_motion_near_torso_enters_ready(self):
        self.assertTrue(is_uchimizu_ready_motion(0.05, 0.02, 1.2, 0.8))


if __name__ == "__main__":
    unittest.main()
