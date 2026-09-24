from types import SimpleNamespace

import numpy as np
import torch
from scripts.evaluate_yolo_pose import select_primary_person


def result_with_boxes(boxes):
    return SimpleNamespace(
        boxes=SimpleNamespace(xyxy=torch.tensor(boxes, dtype=torch.float32)),
        orig_shape=(100, 100),
    )


def test_select_primary_person_uses_largest_foreground_box():
    result = result_with_boxes([[0, 0, 10, 10], [20, 20, 50, 60], [0, 0, 5, 5]])
    assert select_primary_person(result) == 1


def test_select_primary_person_handles_missing_detections():
    assert select_primary_person(SimpleNamespace(boxes=None)) is None
    assert select_primary_person(result_with_boxes(np.empty((0, 4)))) is None


def test_select_primary_person_rejects_background_people():
    result = result_with_boxes([[0, 0, 10, 10], [20, 20, 40, 40]])
    assert select_primary_person(result) is None
