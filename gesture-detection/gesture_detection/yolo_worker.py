import multiprocessing as mp
import queue
from typing import Any

from ultralytics import YOLO

from .config import (
    YOLO_BOTTLE_CLASS_ID,
    YOLO_CONFIDENCE_THRESHOLD,
    YOLO_MODEL_PATH,
)


def yolo_worker(frame_queue: mp.Queue[Any], result_queue: mp.Queue[dict[str, Any]]) -> None:
    """Run bottle detection in a separate process."""
    model = YOLO(str(YOLO_MODEL_PATH))
    try:
        while True:
            frame = frame_queue.get()
            if frame is None:
                break

            result_data = {"boxes": []}
            for result in model(frame, verbose=False) or []:
                boxes = getattr(result, "boxes", None)
                if boxes is None:
                    continue
                for box in boxes:
                    class_id = int(box.cls[0])
                    confidence = float(box.conf[0])
                    if class_id == YOLO_BOTTLE_CLASS_ID and confidence > YOLO_CONFIDENCE_THRESHOLD:
                        x1, y1, x2, y2 = box.xyxy[0].tolist()
                        result_data["boxes"].append(
                            (int(x1), int(y1), int(x2), int(y2), confidence)
                        )

            while not result_queue.empty():
                try:
                    result_queue.get_nowait()
                except queue.Empty:
                    break
            result_queue.put(result_data)
    finally:
        del model
