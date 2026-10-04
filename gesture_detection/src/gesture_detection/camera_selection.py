"""Choose live camera roles from a contact sheet before starting recognition."""

from multiprocessing.synchronize import Event

import cv2
import numpy as np

from . import config

WINDOW = "Select cameras | digit: choose | Esc: cancel"
CELL_WIDTH, CELL_HEIGHT = 320, 240


def select_camera_indices(count: int, stop: Event | None = None) -> tuple[int, ...] | None:
    """Return the chosen IDs in role order, or None when cancelled."""
    captures: dict[int, cv2.VideoCapture] = {}
    window_created = False
    try:
        for index in range(config.CAMERA_SCAN_MAX_INDEX + 1):
            capture = cv2.VideoCapture(index, config.CAMERA_BACKEND)
            if not capture.isOpened():
                capture.release()
                continue
            capture.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter.fourcc(*config.CAMERA_FOURCC))
            ok, frame = capture.read()
            if not ok or frame is None or frame.size == 0:
                capture.release()
                continue
            captures[index] = capture
        if len(captures) < count:
            raise RuntimeError(f"Found {len(captures)} usable cameras; need {count}")

        chosen: list[int] = []
        columns = min(3, len(captures))
        rows = (len(captures) + columns - 1) // columns
        while len(chosen) < count:
            if stop is not None and stop.is_set():
                return None
            canvas = np.zeros((rows * CELL_HEIGHT, columns * CELL_WIDTH, 3), dtype=np.uint8)
            for slot, (index, capture) in enumerate(captures.items()):
                ok, frame = capture.read()
                if ok and frame is not None and frame.size:
                    scale = min(CELL_WIDTH / frame.shape[1], (CELL_HEIGHT - 40) / frame.shape[0])
                    image = cv2.resize(
                        frame, (round(frame.shape[1] * scale), round(frame.shape[0] * scale))
                    )
                    y, x = divmod(slot, columns)
                    canvas[
                        y * CELL_HEIGHT : y * CELL_HEIGHT + image.shape[0],
                        x * CELL_WIDTH : x * CELL_WIDTH + image.shape[1],
                    ] = image
                y, x = divmod(slot, columns)
                label = f"{index}: {'selected' if index in chosen else 'press ' + str(index)}"
                cv2.putText(
                    canvas,
                    label,
                    (x * CELL_WIDTH + 8, (y + 1) * CELL_HEIGHT - 12),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.65,
                    (255, 255, 255),
                    2,
                )
            role = "subject" if count == 2 and not chosen else "full" if count == 2 else "camera"
            cv2.rectangle(canvas, (0, 0), (CELL_WIDTH * columns, 35), (0, 0, 0), -1)
            cv2.putText(
                canvas,
                f"Choose {role} camera ({len(chosen) + 1}/{count})",
                (8, 26),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (255, 255, 255),
                2,
            )
            cv2.imshow(WINDOW, canvas)
            window_created = True
            key = cv2.waitKey(1) & 0xFF
            if key == 27:
                return None
            if ord("0") <= key <= ord("9") and (key - ord("0")) in captures:
                index = key - ord("0")
                if index not in chosen:
                    chosen.append(index)
            try:
                if cv2.getWindowProperty(WINDOW, cv2.WND_PROP_VISIBLE) < 1:
                    return None
            except cv2.error:
                return None
        return tuple(chosen)
    finally:
        for capture in captures.values():
            capture.release()
        if window_created:
            try:
                cv2.destroyWindow(WINDOW)
            except cv2.error:
                # The user may already have closed the native window.
                pass
