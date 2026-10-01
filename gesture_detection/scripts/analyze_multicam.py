"""Summarize the cached multicamera replay without rerunning pose inference."""

import json
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from gesture_detection import config
from gesture_detection.relaxing import RelaxingAnalyzer

from .evaluate_multicam import PROFILES, ROOT, digest


def main() -> None:
    report_path = ROOT / "shared/results/0928-multicam-results.json"
    report = json.loads(report_path.read_text())
    totals = {}
    details = []
    boundaries = {}
    for profile in PROFILES:
        for camera in (1, 2):
            rows = [
                r
                for r in report["rows"]
                if r["profile"] == profile
                and r["camera"] == camera
                and r["metrics"]["trials"]
            ]
            frames = sum(r["frames"] for r in rows)
            wrong, outside, events = Counter(), Counter(), Counter()
            for row in rows:
                wrong.update(row["metrics"]["wrong_label_seconds"])
                outside.update(row["metrics"]["unlabelled_output_seconds"])
                events.update(row["metrics"]["unmatched_events"])
                predictions = json.loads((ROOT / row["predictions"]).read_text())
                with np.load(ROOT / row["cache"]) as cache:
                    points = cache["points"]
                    container = cache["container_seconds"]
                for trial in row["metrics"]["trials"]:
                    start, end = trial["start_frame"], trial["end_frame"]
                    active = points[start : end + 1]
                    visible = active[:, [11, 12, 15, 16, 23, 24], 2] > 0.5
                    torso = active[:, [11, 12, 23, 24], :2]
                    present = np.any(active, axis=(1, 2))
                    detail = dict(
                        take=row["take"],
                        camera=camera,
                        profile=profile,
                        label=trial["label"],
                        pose_fraction=float(np.any(active, axis=(1, 2)).mean()),
                        required_six_visible=float(visible.all(axis=1).mean()),
                        torso_inside_image=float(
                            (
                                ((torso >= 0) & (torso <= 1)).all(axis=(1, 2)) & present
                            ).mean()
                        ),
                        ramune_states=dict(
                            Counter(
                                p["ramune_state"] for p in predictions[start : end + 1]
                            )
                        ),
                        gesture_seconds={
                            k: v / row["effective_fps"]
                            for k, v in Counter(
                                p["gesture"] for p in predictions[start : end + 1]
                            ).items()
                        },
                        event_seconds=[
                            dict(seconds=p["seconds"], events=p["events"])
                            for p in predictions
                            if p["events"]
                        ],
                        container_last_seconds=float(container[-1]),
                    )
                    if trial["label"] == "RELAXING":
                        detector = RelaxingAnalyzer()
                        still, speeds = [], []
                        for i, frame in enumerate(points[: end + 1]):
                            if frame.any():
                                detector.update(
                                    [
                                        SimpleNamespace(x=p[0], y=p[1], visibility=p[2])
                                        for p in frame
                                    ],
                                    i / row["effective_fps"],
                                    1280 / 720,
                                )
                            else:
                                detector.reset()
                            if i >= start:
                                still.append(detector.still_seconds)
                                if detector.motion_speed is not None:
                                    speeds.append(detector.motion_speed)
                        detail["max_still_seconds"] = max(still)
                        detail["speed_exceeds_threshold_fraction"] = (
                            float((np.array(speeds) > config.RELAXING_MAX_SPEED).mean())
                            if speeds
                            else None
                        )
                    details.append(detail)
                    if profile == "rules_full":
                        boundaries.setdefault(row["take"], {})[camera] = (
                            np.array([start, end + 1]) / row["effective_fps"]
                        )
            totals[f"{profile}/camera{camera}"] = dict(
                frames=frames,
                pose_fraction=sum(r["pose_fraction"] * r["frames"] for r in rows)
                / frames,
                wrong_label_seconds=dict(wrong),
                unlabelled_output_seconds=dict(outside),
                unmatched_events=dict(events),
            )
    alignment = [
        dict(
            take=take,
            start_delta_seconds=float(b[2][0] - b[1][0]),
            end_delta_seconds=float(b[2][1] - b[1][1]),
        )
        for take, b in boundaries.items()
        if set(b) == {1, 2}
    ]
    output = dict(
        source_sha256=digest(report_path),
        script_sha256=digest(Path(__file__)),
        totals=totals,
        details=details,
        annotation_boundary_deltas=alignment,
        configuration={
            k: str(v) if isinstance(v, Path) else v
            for k, v in vars(config).items()
            if k.isupper() and isinstance(v, (str, int, float, bool, tuple, Path))
        },
        note="Boundary deltas mix annotation ambiguity and capture timing; not a synchronization measurement.",
    )
    (ROOT / "shared/results/0928-multicam-diagnostics.json").write_text(
        json.dumps(output, indent=2) + "\n"
    )
    print(json.dumps(totals, indent=2))
    print(json.dumps(alignment, indent=2))
    for detail in details:
        if detail["label"] in ("RAMUNE", "RELAXING"):
            print(json.dumps(detail))


if __name__ == "__main__":
    main()
