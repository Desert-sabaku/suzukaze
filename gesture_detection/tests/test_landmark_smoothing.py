import pytest

from gesture_detection.landmark_smoothing import LandmarkSmoother


def test_reduces_stationary_alternating_noise_without_mutating_input():
    smoother = LandmarkSmoother()
    values = []
    for frame in range(60):
        points = [(0.5 + (-1) ** frame * 0.02, 0.5, 0.9)]
        values.append(smoother.update(points, frame / 30)[0][0])
        assert points[0][0] == 0.5 + (-1) ** frame * 0.02
    assert max(values[30:]) - min(values[30:]) < 0.015


@pytest.mark.parametrize("gap", [0.0, -0.1, 0.3])
def test_resets_on_discontinuity(gap):
    smoother = LandmarkSmoother()
    smoother.update([(0.1, 0.1, 1.0)], 1.0)
    assert smoother.update([(0.9, 0.9, 1.0)], 1.0 + gap) == [(0.9, 0.9, 1.0)]


def test_does_not_bridge_missing_pose_or_hidden_points():
    smoother = LandmarkSmoother()
    smoother.update([(0.1, 0.1, 1.0)], 0.0)
    assert smoother.update([], 0.03) == []
    assert smoother.update([(0.9, 0.9, 1.0)], 0.06) == [(0.9, 0.9, 1.0)]
    assert smoother.update([(0.2, 0.2, 0.1)], 0.09) == [(0.2, 0.2, 0.1)]
    assert smoother.update([(0.8, 0.8, 1.0)], 0.12) == [(0.8, 0.8, 1.0)]


def test_same_elapsed_time_has_same_step_response_at_different_rates():
    def response(fps):
        smoother = LandmarkSmoother()
        result = smoother.update([(0.0, 0.0, 1.0)], 0.0)
        for frame in range(1, fps + 1):
            result = smoother.update([(1.0, 1.0, 1.0)], frame / fps)
        return result[0][0]

    assert response(15) == pytest.approx(response(60))
