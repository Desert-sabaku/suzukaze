"""Orient decoded camera frames before inference and rendering."""

from typing import Any, cast

import cv2
import numpy.typing as npt

ROTATIONS = ("none", "clockwise", "counterclockwise", "180")
_CODES = {
    "clockwise": cv2.ROTATE_90_CLOCKWISE,
    "counterclockwise": cv2.ROTATE_90_COUNTERCLOCKWISE,
    "180": cv2.ROTATE_180,
}


def rotate_frame(frame: npt.NDArray[Any], rotation: str) -> npt.NDArray[Any]:
    if rotation == "none":
        return frame
    return cast(npt.NDArray[Any], cv2.rotate(frame, _CODES[rotation]))
