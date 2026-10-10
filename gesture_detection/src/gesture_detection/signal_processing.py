from collections.abc import Iterable

import numpy as np


def count_reversals(values: Iterable[float], distance: float) -> int:
    """Count direction changes that each move at least distance from the last extreme."""
    extreme: float | None = None
    direction = 0
    reversals = 0
    for value in values:
        if extreme is None:
            extreme = value
            continue
        delta = value - extreme
        if direction == 0:
            if abs(delta) >= distance:
                direction = 1 if delta > 0 else -1
                extreme = value
        elif delta * direction >= 0:
            extreme = value
        elif abs(delta) >= distance:
            reversals += 1
            direction *= -1
            extreme = value
    return reversals


def resample_time_window(
    values: np.ndarray,
    timestamps: np.ndarray,
    window_seconds: float,
) -> tuple[np.ndarray, np.ndarray]:
    """Return the latest time window sampled on a uniform time grid."""
    values = np.asarray(values, dtype=np.float32)
    timestamps = np.asarray(timestamps, dtype=np.float64)
    if len(values) != len(timestamps):
        raise ValueError("values and timestamps must have the same length")
    if len(values) < 2 or window_seconds <= 0:
        return np.array([], dtype=np.float32), np.array([], dtype=np.float64)

    # time.monotonic() should be strictly increasing, but discard duplicate or
    # out-of-order entries so np.interp always receives a valid time axis.
    valid = np.concatenate(([True], np.diff(timestamps) > 0))
    values = values[valid]
    timestamps = timestamps[valid]
    if len(values) < 2:
        return np.array([], dtype=np.float32), np.array([], dtype=np.float64)

    window_start = max(timestamps[0], timestamps[-1] - window_seconds)
    in_window = timestamps >= window_start
    sample_count = int(np.count_nonzero(in_window))
    if sample_count < 2:
        return np.array([], dtype=np.float32), np.array([], dtype=np.float64)

    uniform_timestamps = np.linspace(
        window_start,
        timestamps[-1],
        sample_count,
        dtype=np.float64,
    )
    uniform_values = np.interp(uniform_timestamps, timestamps, values).astype(np.float32)
    return uniform_values, uniform_timestamps
