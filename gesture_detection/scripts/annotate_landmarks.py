"""Extract reference frames and annotate six body landmarks without inference."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path

import cv2
import numpy as np

LANDMARKS = (
    "left_shoulder",
    "right_shoulder",
    "left_wrist",
    "right_wrist",
    "left_hip",
    "right_hip",
)
FIELDS: tuple[str, ...] = ("video", "frame_id", "timestamp", "landmark", "x_px", "y_px", "status")
WINDOW = "Reference landmarks"


def sample_indices(total: int, count: int) -> list[int]:
    if total < 1 or count < 1:
        raise ValueError("Video and sample count must be non-empty")
    return np.linspace(0, total - 1, min(total, count), dtype=int).tolist()


def prepare(video: Path, directory: Path, count: int, frames: list[int] | None) -> None:
    """Decode sequentially; count actual frames rather than trusting container metadata."""
    if directory.exists():
        raise ValueError(f"Output already exists; use --resume: {directory}")
    capture = cv2.VideoCapture(str(video))
    try:
        if not capture.isOpened():
            raise ValueError(f"Cannot open video: {video}")
        total = 0
        while capture.grab():
            total += 1
        selected = sample_indices(total, count) if frames is None else sorted(set(frames))
        if not selected or selected[0] < 0 or selected[-1] >= total:
            raise ValueError(f"Frame IDs must be between 0 and {total - 1}")
        fps = capture.get(cv2.CAP_PROP_FPS)
        if not math.isfinite(fps) or fps <= 0:
            raise ValueError("Video has no valid FPS for timestamp fallback")
    finally:
        capture.release()
    directory.mkdir(parents=True)
    capture = cv2.VideoCapture(str(video))
    rows: list[dict[str, str]] = []
    selected_set = set(selected)
    previous = -1.0
    try:
        for index in range(selected[-1] + 1):
            ok, frame = capture.read()
            if not ok:
                raise ValueError(f"Decode failed at frame {index}; incomplete output: {directory}")
            timestamp = capture.get(cv2.CAP_PROP_POS_MSEC) / 1000
            if not math.isfinite(timestamp) or timestamp < 0 or timestamp <= previous:
                timestamp = 0.0 if index == 0 else previous + 1 / fps
            previous = timestamp
            if index not in selected_set:
                continue
            if not cv2.imwrite(str(directory / f"frame_{index:06d}.png"), frame):
                raise OSError("Unable to save extracted frame")
            for landmark in LANDMARKS:
                rows.append(
                    dict(
                        zip(
                            FIELDS,
                            (video.name, str(index), repr(timestamp), landmark, "", "", "pending"),
                            strict=True,
                        )
                    )
                )
    finally:
        capture.release()
    with video.open("rb") as source:
        digest = hashlib.file_digest(source, "sha256").hexdigest()
    (directory / "source.json").write_text(
        json.dumps(
            {
                "video": str(video.resolve()),
                "sha256": digest,
                "frames": selected,
                "total_frames": total,
                "fps": fps,
                "coordinates": "original image pixels; subject anatomical left/right",
                "sampling": "uniform" if frames is None else "explicit frame IDs",
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    save_rows(directory, rows)


def save_rows(directory: Path, rows: list[dict[str, str]]) -> None:
    temporary = directory / "annotations.csv.tmp"
    with temporary.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(directory / "annotations.csv")


def load_rows(directory: Path) -> list[dict[str, str]]:
    with (directory / "annotations.csv").open(encoding="utf-8", newline="") as source:
        reader = csv.DictReader(source)
        if reader.fieldnames != list(FIELDS):
            raise ValueError("Unexpected annotation CSV columns")
        rows = list(reader)
    metadata = json.loads((directory / "source.json").read_text(encoding="utf-8"))
    expected = [(str(frame), landmark) for frame in metadata["frames"] for landmark in LANDMARKS]
    if [(row["frame_id"], row["landmark"]) for row in rows] != expected:
        raise ValueError("CSV does not match session frames/landmarks")
    for row in rows:
        if row["status"] not in {"pending", "marked", "uncertain"}:
            raise ValueError("Invalid annotation status")
        if row["status"] == "marked":
            if not all(math.isfinite(float(row[key])) for key in ("x_px", "y_px")):
                raise ValueError("Invalid landmark coordinates")
    return rows


def original_point(
    x: int, y: int, width: int, height: int, display_width: int, display_height: int
) -> tuple[int, int] | None:
    if not (0 <= x < display_width and 0 <= y < display_height):
        return None
    return min(width - 1, round(x * width / display_width)), min(
        height - 1, round(y * height / display_height)
    )


def annotate(directory: Path, max_width: int, max_height: int) -> None:
    rows = load_rows(directory)
    cursor = next((i for i, row in enumerate(rows) if row["status"] == "pending"), 0)
    image = None
    loaded_id = None
    display_width = display_height = 0

    def record(status: str, point: tuple[int, int] | None = None) -> None:
        nonlocal cursor
        rows[cursor].update(
            status=status, x_px=str(point[0]) if point else "", y_px=str(point[1]) if point else ""
        )
        save_rows(directory, rows)
        # Stay on the same frame so a double click cannot label the next image.
        if status != "pending" and cursor % 6 < 5:
            cursor += 1

    def click(event: int, x: int, y: int, flags: int, userdata: object) -> None:
        if event != cv2.EVENT_LBUTTONDOWN or image is None:
            return
        point = original_point(x, y, image.shape[1], image.shape[0], display_width, display_height)
        if point is not None:
            record("marked", point)

    cv2.namedWindow(WINDOW, cv2.WINDOW_AUTOSIZE)
    cv2.setMouseCallback(WINDOW, click)
    try:
        while True:
            row = rows[cursor]
            if loaded_id != row["frame_id"]:
                image = cv2.imread(str(directory / f"frame_{int(row['frame_id']):06d}.png"))
                if image is None:
                    raise ValueError(f"Missing extracted image: {row['frame_id']}")
                loaded_id = row["frame_id"]
                scale = min(1.0, max_width / image.shape[1], max_height / image.shape[0])
                display_width = max(1, round(image.shape[1] * scale))
                display_height = max(1, round(image.shape[0] * scale))
            assert image is not None
            canvas = cv2.resize(image, (display_width, display_height))
            start = cursor // 6 * 6
            for offset, item in enumerate(rows[start : start + 6]):
                if item["status"] == "marked":
                    point = (
                        round(float(item["x_px"]) * display_width / image.shape[1]),
                        round(float(item["y_px"]) * display_height / image.shape[0]),
                    )
                    cv2.circle(canvas, point, 5, (0, 255, 255), -1)
                    cv2.putText(
                        canvas,
                        str(offset + 1),
                        point,
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.6,
                        (0, 0, 255),
                        2,
                    )
            canvas = cv2.copyMakeBorder(
                canvas, 0, 115, 0, max(0, 850 - display_width), cv2.BORDER_CONSTANT
            )
            pending = sum(item["status"] == "pending" for item in rows)
            lines = [
                f"Frame {cursor // 6 + 1}/{len(rows) // 6} | ID {loaded_id} | "
                f"{float(row['timestamp']):.3f}s | pending points: {pending}",
                f"{cursor % 6 + 1}: {row['landmark']} [{row['status']}] | subject's left/right",
                "Click: mark | U: uncertain | 1-6: select point | C: clear | Z: previous point",
                "N/P: next/previous frame | Q/Esc: quit | Every edit is saved automatically",
            ]
            for index, line in enumerate(lines):
                cv2.putText(
                    canvas,
                    line,
                    (8, display_height + 22 + index * 26),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.5,
                    (255, 255, 255),
                    1,
                )
            cv2.imshow(WINDOW, canvas)
            key = cv2.waitKey(30) & 0xFF
            if key in (27, ord("q")) or cv2.getWindowProperty(WINDOW, cv2.WND_PROP_VISIBLE) < 1:
                break
            if ord("1") <= key <= ord("6"):
                cursor = start + key - ord("1")
            elif key == ord("u"):
                record("uncertain")
            elif key == ord("c"):
                record("pending")
            elif key == ord("z"):
                cursor = max(0, cursor - 1)
            elif key == ord("n"):
                cursor = min(len(rows) - 6, start + 6)
            elif key == ord("p"):
                cursor = max(0, start - 6)
    finally:
        cv2.destroyAllWindows()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video", type=Path, nargs="?")
    parser.add_argument(
        "--output",
        type=Path,
        help="New session directory (default: project output/annotations/<video stem>)",
    )
    parser.add_argument("--resume", type=Path, help="Resume an existing session")
    parser.add_argument("--count", type=int, default=8)
    parser.add_argument("--frames", type=int, nargs="+", help="Explicit zero-based frame IDs")
    parser.add_argument("--extract-only", action="store_true")
    parser.add_argument("--max-width", type=int, default=1280)
    parser.add_argument("--max-height", type=int, default=720)
    args = parser.parse_args()
    if min(args.count, args.max_width, args.max_height) < 1:
        parser.error("Count and display dimensions must be positive")
    if args.resume:
        if args.video or args.output or args.frames:
            parser.error("--resume cannot be combined with video, --output or --frames")
        directory = args.resume
    else:
        if not args.video:
            parser.error("Provide video, or --resume")
        directory = args.output or (
            Path(__file__).resolve().parents[1] / "output" / "annotations" / args.video.stem
        )
        prepare(args.video, directory, args.count, args.frames)
    if not args.extract_only:
        annotate(directory, args.max_width, args.max_height)
    print(f"Annotations: {directory / 'annotations.csv'}")


if __name__ == "__main__":
    main()
