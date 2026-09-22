import csv

import cv2
import numpy as np
from scripts.evaluate_landmark_annotations import (
    AnnotatedFrame,
    Annotation,
    background_preprocess,
    build_session_backgrounds,
    load_frames,
    normalized_status,
    reference_scale,
)


def test_legacy_absent_statuses_are_normalized():
    assert normalized_status("aogi1_2-6", "uncertain") == "absent"
    assert normalized_status("aogi1_2-6", "pending") == "absent"
    assert normalized_status("aogi2_2-5", "pending") == "absent"
    assert normalized_status("ramune1_3-4", "uncertain") == "uncertain"


def test_loads_only_named_experiment_sessions(tmp_path):
    session = tmp_path / "ramune1_3-4"
    session.mkdir()
    cv2.imwrite(str(session / "frame_000001.png"), np.zeros((20, 30, 3), dtype=np.uint8))
    with (session / "annotations.csv").open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(
            output,
            fieldnames=("video", "frame_id", "timestamp", "landmark", "x_px", "y_px", "status"),
        )
        writer.writeheader()
        writer.writerow(
            {
                "video": "clip.mp4",
                "frame_id": 1,
                "timestamp": 0.5,
                "landmark": "left_wrist",
                "x_px": 10,
                "y_px": 12,
                "status": "marked",
            }
        )
    ignored = tmp_path / "uchimizu-btn"
    ignored.mkdir()

    frames = load_frames(tmp_path)

    assert len(frames) == 1
    assert frames[0].session == "ramune1_3-4"
    assert frames[0].annotations[0].x_px == 10


def test_reference_scale_prefers_shoulder_width():
    annotations = (
        Annotation("left_shoulder", "marked", 10, 10),
        Annotation("right_shoulder", "marked", 40, 10),
    )

    assert reference_scale(annotations, 100, 100) == 30


def test_builds_background_from_absent_frames(tmp_path):
    first = tmp_path / "first.png"
    second = tmp_path / "second.png"
    cv2.imwrite(str(first), np.full((4, 5, 3), 10, dtype=np.uint8))
    cv2.imwrite(str(second), np.full((4, 5, 3), 30, dtype=np.uint8))
    absent = (Annotation("left_wrist", "absent", None, None),)
    frames = [
        AnnotatedFrame("aogi1_2-6", 0, 0.0, first, absent),
        AnnotatedFrame("aogi1_2-6", 1, 1.0, second, absent),
    ]

    backgrounds = build_session_backgrounds(frames)

    assert np.all(backgrounds["aogi1_2-6"] == 20)


def test_background_difference_preserves_changed_region():
    background = np.zeros((20, 20, 3), dtype=np.uint8)
    image = background.copy()
    image[5:15, 5:15] = 200

    result = background_preprocess(image, background, "background_difference")

    assert result.shape == image.shape
    assert result[10, 10, 0] > result[0, 0, 0]
