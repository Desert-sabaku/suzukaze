"""Action continuity and tolerant phase timing, kept separate from inference."""

from collections import Counter

import numpy as np


def runs(mask: list[bool]) -> list[tuple[int, int]]:
    edges = np.diff(np.r_[0, np.asarray(mask, dtype=int), 0])
    return list(
        zip(np.flatnonzero(edges == 1).tolist(), np.flatnonzero(edges == -1).tolist(), strict=True)
    )


def temporal_score(
    intervals: list[dict], predictions: list[dict], fps: float, tolerance: float = 1.0
) -> dict:
    """Phase windows expand by tolerance, but remain inside their parent action.

    Each pulse is matched at most once and each action accepts at most one pulse.
    State output fragmentation is measured without using phase boundaries.
    """
    actions = sorted(
        (x for x in intervals if x["track"] == "action"), key=lambda x: x["start_frame"]
    )
    pulses = [(p["frame"], label) for p in predictions for label in p["events"]]
    matched = set()
    trials = []
    for action in actions:
        label, start, end = action["label"], action["start_frame"], action["end_frame"]
        spans = runs([p["gesture"] == label for p in predictions[start : end + 1]])
        lengths = [b - a for a, b in spans]
        local_pulses = [
            (i, f) for i, (f, g) in enumerate(pulses) if g == label and start <= f <= end
        ]
        phases = (
            [
                x
                for x in intervals
                if x["track"] == "ramune_phase"
                and x["label"] == "OPENED"
                and start <= x["start_frame"] <= x["end_frame"] <= end
            ]
            if label == "RAMUNE"
            else []
        )
        eligible = [
            (i, f)
            for i, f in local_pulses
            if i not in matched
            and (
                not phases
                or any(
                    x["start_frame"] - tolerance * fps <= f <= x["end_frame"] + tolerance * fps
                    for x in phases
                )
            )
        ]
        event_gesture = label in ("RAMUNE", "UCHIMIZU")
        if event_gesture and eligible:
            matched.add(eligible[0][0])
        tail = 0
        if end < len(predictions) and predictions[end]["gesture"] == label:
            while (
                end + tail + 1 < len(predictions)
                and predictions[end + tail + 1]["gesture"] == label
            ):
                tail += 1
        trials.append(
            dict(
                label=label,
                start_frame=start,
                end_frame=end,
                detected=bool(eligible) if event_gesture else bool(spans),
                phase_timing_checked=bool(phases),
                phase_tolerance_seconds=tolerance if phases else None,
                events_inside_action=len(local_pulses),
                extra_events=max(0, len(local_pulses) - 1),
                matched_event_frame=eligible[0][1] if event_gesture and eligible else None,
                output_runs=len(spans),
                reappearances=max(0, len(spans) - 1),
                output_seconds=sum(lengths) / fps,
                coverage=sum(lengths) / (end - start + 1),
                longest_seconds=max(lengths, default=0) / fps,
                first_response_seconds=(spans[0][0] / fps if spans else None),
                tail_overrun_seconds=tail / fps,
                tail_right_censored=bool(tail and end + tail == len(predictions) - 1),
            )
        )
    wrong, unlabelled = Counter(), Counter()
    for p in predictions:
        truth = {x["label"] for x in actions if x["start_frame"] <= p["frame"] <= x["end_frame"]}
        if p["gesture"] != "NONE" and p["gesture"] not in truth:
            (wrong if truth else unlabelled)[p["gesture"]] += 1
    return dict(
        trials=trials,
        unmatched_events=dict(Counter(g for i, (_, g) in enumerate(pulses) if i not in matched)),
        wrong_label_seconds={g: n / fps for g, n in wrong.items()},
        unlabelled_output_seconds={g: n / fps for g, n in unlabelled.items()},
    )
