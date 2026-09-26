from pathlib import Path
from types import SimpleNamespace

import numpy as np
import torch
from scripts.evaluate_landmark_annotations import AnnotatedFrame, Annotation
from scripts.evaluate_yolo_annotations import foreground_candidates, select_candidate


def result_with_boxes():
    return SimpleNamespace(
        boxes=SimpleNamespace(
            xyxy=torch.tensor([[0, 0, 50, 100], [35, 20, 75, 80]], dtype=torch.float32)
        ),
        keypoints=SimpleNamespace(
            xy=torch.zeros((2, 17, 2), dtype=torch.float32),
            conf=torch.ones((2, 17), dtype=torch.float32),
        ),
        orig_shape=(100, 100),
    )


def annotated_frame():
    return AnnotatedFrame(
        session="ramune1_3-4",
        frame_id=1,
        timestamp=1.0,
        image=Path("unused.png"),
        annotations=(Annotation("left_shoulder", "marked", 60, 50),),
    )


def test_filters_small_boxes_and_selects_largest():
    result = result_with_boxes()
    candidates = foreground_candidates(result, 0.1)

    assert candidates.tolist() == [0, 1]
    assert select_candidate(result, candidates, "largest", annotated_frame(), 0.5) == 0


def test_selects_box_nearest_image_center():
    result = result_with_boxes()
    candidates = foreground_candidates(result, 0.1)

    assert select_candidate(result, candidates, "center", annotated_frame(), 0.5) == 1


def test_oracle_selects_candidate_nearest_annotation():
    result = result_with_boxes()
    result.keypoints.xy[0, 5] = torch.tensor([10, 50])
    result.keypoints.xy[1, 5] = torch.tensor([59, 50])
    candidates = np.asarray([0, 1])

    assert select_candidate(result, candidates, "oracle", annotated_frame(), 0.5) == 1
