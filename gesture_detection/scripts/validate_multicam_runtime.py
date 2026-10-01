"""Check the production profile against frozen 0928 camera and fusion traces."""

import argparse
import json
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from gesture_detection.config import MULTICAM_FUSION_FPS
from gesture_detection.multicam_fusion import MultiCameraFusion
from gesture_detection.recognition import RecognitionCoordinator

ROOT = Path(__file__).resolve().parents[1]


@dataclass
class Point:
    x: float
    y: float
    visibility: float


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--takes", nargs="*")
    parser.add_argument(
        "--trace",
        nargs=2,
        action="append",
        default=[],
        metavar=("TAKE", "JSONL"),
        help="Also compare actual application replay traces, including the EOF tick",
    )
    args = parser.parse_args()
    baseline = json.loads(
        (ROOT / "shared/results/0928-multicam-results.json").read_text()
    )
    reference = json.loads(
        (ROOT / "shared/results/0928-multicam-events-results.json").read_text()
    )
    takes = sorted({r["take"] for r in baseline["rows"]})
    requested = args.takes or [take for take, _ in args.trace]
    if requested:
        unknown = set(requested) - set(takes)
        if unknown:
            raise ValueError(f"Unknown takes: {sorted(unknown)}")
        takes = [t for t in takes if t in requested]
    total = 0
    for take in takes:
        streams = []
        for camera, profile in ((1, "rules_subject"), (2, "rules_full")):
            source = next(
                r
                for r in baseline["rows"]
                if r["take"] == take
                and r["camera"] == camera
                and r["profile"] == profile
            )
            expected_row = next(
                r
                for r in reference["rows"]
                if r["take"] == take
                and r["reference_camera"] == camera
                and r["profile"] == profile + "/peak_anchor"
            )
            try:
                expected = json.loads((ROOT / expected_row["predictions"]).read_text())
                with np.load(ROOT / source["cache"]) as cache:
                    points = cache["points"]
            except FileNotFoundError as error:
                raise RuntimeError(
                    "Frozen 0928 caches are needed; reproduce the handoff pipeline on the research revision first"
                ) from error
            coordinator = RecognitionCoordinator(
                ramune_detector="rules",
                source_fps=source["effective_fps"],
                profile="multicam",
            )
            output = []
            for i, frame in enumerate(points):
                landmarks = [Point(*p) for p in frame] if frame.any() else []
                result = coordinator.process(
                    landmarks, i / source["effective_fps"], i, aspect_ratio=1280 / 720
                )
                observed = dict(
                    frame=i,
                    seconds=result["timestamp"],
                    gesture=result["current"]["gesture"],
                    events=list(result["occurrences"]),
                    ramune_state=result["ramune_state"],
                )
                if observed != expected[i]:
                    raise AssertionError(
                        f"Camera replay differs: {take}, camera {camera}, frame {i}: {observed} != {expected[i]}"
                    )
                output.append(result)
            streams.append(output)
            total += len(output)
        expected_row = next(
            r
            for r in reference["fusion_rows"]
            if r["take"] == take
            and r["reference_camera"] == 1
            and r["profile"] == "fusion_asymmetric/peak_anchor_fresh_setup"
        )
        expected = json.loads((ROOT / expected_row["predictions"]).read_text())
        fusion = MultiCameraFusion()
        indices = [0, 0]
        session = json.loads(
            (ROOT / "shared/videos/0928" / take / "session.json").read_text()
        )
        for tick in range(math.ceil(session["duration_seconds"] * MULTICAM_FUSION_FPS)):
            now = tick / MULTICAM_FUSION_FPS
            for slot, stream in enumerate(streams):
                while (
                    indices[slot] < len(stream)
                    and stream[indices[slot]]["timestamp"] <= now + 1e-9
                ):
                    fusion.submit(slot, stream[indices[slot]])
                    indices[slot] += 1
            result = fusion.advance(now)
            observed = dict(
                frame=tick,
                seconds=now,
                gesture=result["current"]["gesture"],
                events=list(result["occurrences"]),
            )
            if observed != expected[tick]:
                raise AssertionError(
                    f"Fusion replay differs: {take}, tick {tick}: {observed} != {expected[tick]}"
                )
        print(take, "camera and fused frame parity verified", flush=True)
    print(f"Verified {len(takes)} takes, {total} native camera frames")
    for take, path in args.trace:
        row = next(
            r
            for r in reference["fusion_rows"]
            if r["take"] == take
            and r["reference_camera"] == 1
            and r["profile"] == "fusion_asymmetric/peak_anchor_fresh_setup"
        )
        expected = json.loads((ROOT / row["predictions"]).read_text())
        actual = [json.loads(line) for line in Path(path).read_text().splitlines()]
        if len(actual) != len(expected) + 1:
            raise AssertionError(
                "Application trace must include all grid ticks and the EOF tick"
            )
        for item, target in zip(actual[:-1], expected, strict=True):
            result = item["fused"]
            observed = dict(
                frame=result["frame_id"],
                seconds=result["timestamp"],
                gesture=result["current"]["gesture"],
                events=result["occurrences"],
            )
            if observed != target:
                raise AssertionError(
                    f"Application replay differs: {take}: {observed} != {target}"
                )
        for slot in (0, 1):
            source = next(
                r
                for r in baseline["rows"]
                if r["take"] == take and r["camera"] == slot + 1
            )
            if actual[-1]["views"][str(slot)]["frame_id"] != source["frames"] - 1:
                raise AssertionError(
                    "Application did not consume all native video frames"
                )
        print(take, "actual application trace parity and native EOF verified")


if __name__ == "__main__":
    main()
