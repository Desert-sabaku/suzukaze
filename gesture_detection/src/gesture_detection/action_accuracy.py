"""Motion-criterion scores, independent of classification confidence.

Each measured criterion has equal weight; missing/nonfinite measurements make
the whole evaluation unavailable. See docs/gestures.md for the scoring contract.
"""

import math
from collections.abc import Sequence

from . import config as c


def minimum(value: float, target: float) -> float:
    return max(0.0, min(1.0, value / target)) if math.isfinite(value) else math.nan


def maximum(value: float, limit: float) -> float:
    if not math.isfinite(value):
        return math.nan
    return 1.0 if value <= limit else max(0.0, 2.0 - value / limit)


def interval(value: float, lower: float, upper: float) -> float:
    return min(minimum(value, lower), maximum(value, upper))


def aggregate(*scores: float) -> float | None:
    if not scores or any(not math.isfinite(s) for s in scores):
        return None
    return sum(scores) / len(scores)


def bow_accuracy(
    angle: float | None, deviation: float | None, aligned: bool, hold: float
) -> float | None:
    if angle is None or deviation is None:
        return None
    return aggregate(
        interval(angle, c.BOW_MIN_ANGLE_DEGREES, c.BOW_MAX_ANGLE_DEGREES),
        maximum(deviation, c.BOW_MAX_HEAD_DEVIATION_DEGREES),
        float(aligned),
        minimum(hold, c.BOW_DWELL_SECONDS),
    )


def relaxing_accuracy(speed: float | None, drift: float, hold: float) -> float | None:
    if speed is None:
        return None
    return aggregate(
        maximum(speed, c.RELAXING_MAX_SPEED),
        maximum(drift, c.RELAXING_MAX_DRIFT),
        minimum(hold, c.RELAXING_DWELL_SECONDS),
    )


def fanning_accuracy(history: Sequence[tuple[float, float]]) -> float | None:
    """Score source-time height, excursion and full-cycle frequency over one second."""
    if len(history) < 3 or any(not math.isfinite(v) for item in history for v in item):
        return None
    duration = history[-1][0] - history[0][0]
    if duration < c.ACCURACY_FANNING_MIN_SECONDS:
        return None
    if any(
        not 0 < b[0] - a[0] <= c.ACCURACY_FANNING_MAX_GAP
        for a, b in zip(history, history[1:], strict=False)
    ):
        return None
    extreme = history[0][1]
    direction = 0
    reversals = 0
    for _, height in history:
        delta = height - extreme
        if direction == 0:
            if abs(delta) >= c.FANNING_REVERSAL_DISTANCE:
                direction = 1 if delta > 0 else -1
                extreme = height
        elif delta * direction >= 0:
            extreme = height
        elif abs(delta) >= c.FANNING_REVERSAL_DISTANCE:
            reversals += 1
            direction *= -1
            extreme = height
    heights = [height for _, height in history]
    # Integrate the measured position criterion in source time, not frame count.
    position = (
        sum(
            (b[0] - a[0]) * float(a[1] <= c.FANNING_MAX_TORSO_HEIGHT)
            for a, b in zip(history, history[1:], strict=False)
        )
        / duration
    )
    return aggregate(
        position,
        minimum(max(heights) - min(heights), c.FANNING_REVERSAL_DISTANCE),
        interval(reversals / (2 * duration), c.ACCURACY_FANNING_MIN_HZ, c.ACCURACY_FANNING_MAX_HZ),
        minimum(duration, c.FANNING_POSITION_DWELL_SECONDS),
    )
