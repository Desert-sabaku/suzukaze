"""Relative feature geometry, causal validity, and grouped model selection."""

import json

import numpy as np
import pytest
from scripts import evaluate_opening_features as experiment
from scripts import evaluate_timeline as timeline


def clip(n=20):
    points = np.zeros((n, 33, 3))
    points[:, :, 2] = 1.0
    points[:, 11, :2] = (0.4, 0.3)
    points[:, 12, :2] = (0.6, 0.3)
    points[:, 15, :2] = (0.35, 0.4)
    points[:, 16, :2] = (0.65, 0.5)
    points[:, 23, :2] = (0.4, 0.6)
    points[:, 24, :2] = (0.6, 0.6)
    return dict(points=points, aspect=1.0, fps=20.0)


def test_geometry_is_translation_and_scale_invariant():
    source = clip()
    source["aspect"] = 16 / 9
    expected, flags = experiment.relative_geometry(source)
    transformed = dict(source, points=source["points"].copy())
    transformed["points"][:, :, :2] = transformed["points"][:, :, :2] * 1.7 + [0.2, -0.1]
    actual, actual_flags = experiment.relative_geometry(transformed)
    np.testing.assert_allclose(actual, expected, atol=1e-12)
    np.testing.assert_array_equal(actual_flags, flags)


def test_geometry_corrects_aspect_and_preserves_vertical_direction():
    source = clip()
    source["aspect"] = 2.0
    values, valid = experiment.relative_geometry(source)
    assert valid.all()
    np.testing.assert_allclose(values[0, [0, 1, 3, 4, 5, 6]], [1.5, 0.25, -0.75, 0.25, 0.75, 0.5])
    assert values[0, 2] == pytest.approx(np.hypot(1.5, 0.25))


def test_invalid_wrist_does_not_invalidate_other_wrist_but_shoulders_do():
    source = clip()
    source["points"][0, 15, 2] = 0.5
    source["points"][1, 11, 2] = 0.49
    source["points"][2, 15, 0] = np.nan
    source["points"][3, 12, :2] = source["points"][3, 11, :2]
    values, flags = experiment.relative_geometry(source)
    assert not flags[0, :5].any() and flags[0, 5:].all()
    assert not flags[1].any() and not flags[3].any()
    assert not flags[2, :5].any() and flags[2, 5:].all()
    assert np.isfinite(values).all() and np.all(values[~flags] == 0)


def test_velocity_is_per_second_and_startup_is_invalid():
    source = clip()
    source["points"][:, 15, 0] += np.arange(20) * 0.005
    values, flags = experiment.relative_geometry(source)
    motion = experiment.motion_features(values, flags, source["fps"])
    assert np.all(motion[:2, :14] == 0) and np.all(motion[:4, 14:] == 0)
    np.testing.assert_allclose(motion[4:, 3], 0.5, atol=1e-12)
    np.testing.assert_allclose(motion[4:, 17], 0.5, atol=1e-12)
    assert np.all(motion[4:, 7:14] == 1) and np.all(motion[4:, 21:] == 1)


def test_missing_endpoint_never_creates_velocity_from_zero_padding():
    source = clip()
    source["points"][4, 15, 2] = 0
    values, flags = experiment.relative_geometry(source)
    motion = experiment.motion_features(values, flags, source["fps"])
    for frame in (4, 6):
        assert np.all(motion[frame, :5] == 0)
        assert np.all(motion[frame, 7:12] == 0)
    assert np.all(motion[8, 14:19] == 0) and np.all(motion[8, 21:26] == 0)
    assert motion[6, 12] == 1  # Right wrist remains valid.


def test_features_preserve_baseline_and_do_not_use_future_or_labels():
    source = clip()
    before = experiment.feature_sets(source)
    for history in (0.25, 0.75):
        np.testing.assert_array_equal(before["baseline"][history], timeline.features(source, history))
        assert [before[key][history].shape[1] for key in experiment.FAMILIES] == [96, 110, 138]
    source["points"][10:] = np.random.default_rng(26).random((10, 33, 3))
    source["phase"], source["action"] = np.ones(20), np.ones(20)
    after = experiment.feature_sets(source)
    for family in experiment.FAMILIES:
        for history in (0.25, 0.75):
            np.testing.assert_array_equal(before[family][history][:10], after[family][history][:10])


def test_nested_selection_excludes_outer_test_and_without_screen(monkeypatch):
    samples = []
    for group in (0, 1, 2, 3):
        samples.append(dict(
            name=str(group), group=group, phase=np.array([0, 1, 3]),
            feature_sets={"baseline": {0.25: np.ones((3, 2)), 0.75: np.ones((3, 2))}},
        ))
    allowed = set()
    calls = []
    original_choose = timeline.choose

    def choose(train, target, *, audit):
        allowed.clear()
        allowed.update(c["group"] for c in train)
        assert 0 not in allowed
        return original_choose(train, target, audit=audit)

    def fit(train, test, target, *params):
        train_groups = {c["group"] for c in train}
        test_groups = {c["group"] for c in test}
        assert train_groups <= allowed
        assert train_groups.isdisjoint(test_groups)
        if train_groups != allowed:  # Inner fold.
            assert test_groups <= allowed
        calls.append((train_groups, test_groups))
        return [c[target].copy() for c in test]

    monkeypatch.setattr(experiment, "choose", choose)
    monkeypatch.setattr(experiment, "fit_predict", fit)
    monkeypatch.setattr(timeline, "fit_predict", fit)
    predictions, selections = experiment.phase_predictions(samples, "baseline")
    assert set(predictions) == {"0", "1", "2", "3"}
    assert len(calls) == 3 * (24 + 1) + 36 + 1
    assert all(len(s["trials"]) == 12 for s in selections)


def test_unknown_phase_is_excluded_from_training_and_test_labels_are_unused():
    rng = np.random.default_rng(26)
    x = rng.normal(size=(21, 4))
    y = np.arange(21) % 5
    y[0] = -1
    train = dict(features={0.25: x}, phase=y)
    trimmed = dict(features={0.25: x[1:]}, phase=y[1:])
    test = dict(features={0.25: x[:4]}, points=np.ones((4, 33, 3)))
    expected = timeline.fit_predict([trimmed], [test], "phase", 0.25, 0.1)[0]
    actual = timeline.fit_predict([train], [dict(test, phase=np.full(4, -1))], "phase", 0.25, 0.1)[0]
    np.testing.assert_array_equal(actual, expected)


def test_cache_only_does_not_start_inference_or_create_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(timeline, "ROOT", tmp_path)
    video = tmp_path / "shared/videos/0924/both1_behind_the_screen.mp4"
    video.parent.mkdir(parents=True)
    video.write_bytes(b"not a video; inference must never run")
    model = tmp_path / "pose.task"
    model.write_bytes(b"model")
    monkeypatch.setattr(timeline.config, "POSE_MODEL_PATH", model)
    path = tmp_path / "both1_behind_the_screen/timeline.json"
    path.parent.mkdir()
    path.write_text(json.dumps(dict(source=dict(sha256=timeline.digest(video)))))

    def forbidden(*args, **kwargs):
        raise AssertionError("Inference unexpectedly started")

    monkeypatch.setattr(timeline, "PoseAnalyzer", forbidden)
    monkeypatch.setattr(timeline.cv2, "VideoCapture", forbidden)
    cache = tmp_path / "cache"
    with pytest.raises(FileNotFoundError, match="Required pose cache"):
        timeline.extract(path, cache, cache_only=True)
    assert not cache.exists()
