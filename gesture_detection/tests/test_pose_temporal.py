import numpy as np
from scripts.evaluate_pose_temporal import choose_person, repair


def test_association_does_not_jump_to_larger_unrelated_box():
    boxes = np.array([[0, 0, 0.4, 1], [0.5, 0, 1, 1]])
    assert choose_person(boxes, boxes[0]) == 0
    assert choose_person(boxes[1:], boxes[0]) is None


def test_repair_only_short_bracketed_same_track_gaps():
    points = np.array([[[0.0, 0.0]], [[np.nan, np.nan]], [[1.0, 1.0]]])
    filled, _, imputed = repair(points, np.array([0.0, 0.03, 0.06]), np.array([0, 0, 0]))
    np.testing.assert_allclose(filled[1, 0], [0.5, 0.5])
    assert imputed.sum() == 1
    for times, segments in [
        (np.array([0.0, 0.1, 0.2]), np.array([0, 0, 0])),
        (np.array([0.0, 0.03, 0.06]), np.array([0, 0, 1])),
    ]:
        filled, _, imputed = repair(points, times, segments)
        assert np.isnan(filled[1]).all()
        assert not imputed.any()


def test_repair_leaves_unbracketed_gaps_missing_and_resets_smoothing():
    points = np.array(
        [[[np.nan, np.nan]], [[0.0, 0.0]], [[np.nan, np.nan]], [[1.0, 1.0]], [[np.nan, np.nan]]]
    )
    filled, smooth, imputed = repair(points, np.arange(5) * 0.2, np.zeros(5))
    assert np.isnan(filled[[0, 2, 4]]).all()
    np.testing.assert_allclose(smooth[3], points[3])
    assert not imputed.any()
