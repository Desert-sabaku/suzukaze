"""Multi-camera recorder with a shared software timeline (no hardware genlock)."""

import argparse
import csv
import json
import math
import shutil
import signal
import sys
import tempfile
import threading
import time
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np

from gesture_detection.qt_setup import configure_qt_fonts

WINDOW = "Camera recorder | R/Space: record/stop | S: snapshot | M: marker | Q/Esc: quit"


def positive_int(value: str) -> int:
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("must be positive")
    return number


def nonnegative_float(value: str) -> float:
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise argparse.ArgumentTypeError("must be finite and nonnegative")
    return number


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cameras", nargs="+", type=int, default=[0, 1, 2], metavar="ID")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "shared" / "videos",
        help="output root (default: project shared/videos)",
    )
    parser.add_argument("--width", type=positive_int, default=1280)
    parser.add_argument("--height", type=positive_int, default=720)
    parser.add_argument("--fps", type=positive_int, default=30)
    parser.add_argument(
        "--input-format",
        choices=["MJPG", "YUYV", "auto"],
        default="MJPG",
        help="camera transport format, independent of output --codec",
    )
    parser.add_argument("--backend", choices=["auto", "v4l2", "dshow", "msmf"], default="auto")
    parser.add_argument("--codec", choices=["mp4v", "MJPG"], default="mp4v")
    parser.add_argument("--countdown", type=nonnegative_float, default=3)
    parser.add_argument(
        "--duration",
        type=nonnegative_float,
        default=0,
        help="seconds per take; 0 means unlimited",
    )
    parser.add_argument("--auto-start", action="store_true")
    parser.add_argument("--no-preview", action="store_true", help="auto-start without a GUI")
    parser.add_argument("--min-free-mb", type=positive_int, default=256)
    args = parser.parse_args(argv)
    if min(args.cameras) < 0 or len(set(args.cameras)) != len(args.cameras):
        parser.error("--cameras requires distinct nonnegative camera IDs")
    return args


class CameraReader:
    """One owner per capture; discard old frames instead of queueing them."""

    def __init__(self, camera: cv2.VideoCapture, camera_id: int) -> None:
        self.camera = camera
        self.camera_id = camera_id
        self._lock = threading.Lock()
        self._ready = threading.Event()
        self._stop = threading.Event()
        self._latest: tuple[np.ndarray, float] | None = None
        self._error: str | None = None
        self._thread = threading.Thread(target=self._read, name=f"camera-{camera_id}", daemon=True)
        self._thread.start()

    def _read(self) -> None:
        try:
            while not self._stop.is_set():
                ok, frame = self.camera.read()
                stamp = time.monotonic()
                if not ok or frame is None or not frame.size:
                    raise RuntimeError("read failed (disconnected or unsupported input mode)")
                # Some backends reuse the receive buffer. Publish owned, immutable-by-convention data.
                owned = frame.copy()
                with self._lock:
                    self._latest = (owned, stamp)
                self._ready.set()
        except Exception as error:
            with self._lock:
                self._error = str(error)
            self._ready.set()
        finally:
            # Never release a VideoCapture while another thread is inside read().
            self.camera.release()

    def latest(self, timeout: float = 5.0) -> tuple[np.ndarray, float]:
        if not self._ready.wait(timeout):
            raise RuntimeError(f"Camera {self.camera_id}: timed out waiting for first frame")
        with self._lock:
            if self._error is not None:
                raise RuntimeError(f"Camera {self.camera_id}: {self._error}")
            latest = self._latest
        if latest is None or time.monotonic() - latest[1] > timeout:
            raise RuntimeError(f"Camera {self.camera_id}: no new frames for {timeout:g}s")
        return latest

    def release(self) -> None:
        self._stop.set()
        self._thread.join(timeout=1.0)
        if self._thread.is_alive():
            print(
                f"Camera {self.camera_id}: driver read is still blocked; "
                "capture will close when it returns",
                file=sys.stderr,
            )


def capture_frames(cameras: Sequence[CameraReader]) -> tuple[list[np.ndarray], list[float]]:
    frames, stamps = [], []
    for camera in cameras:
        frame, stamp = camera.latest()
        frames.append(frame)
        stamps.append(stamp)
    return frames, stamps


def open_cameras(args: argparse.Namespace) -> list:
    cameras = []
    readers = []
    try:
        for camera_id in args.cameras:
            backend = {
                "auto": cv2.CAP_ANY,
                "v4l2": cv2.CAP_V4L2,
                "dshow": cv2.CAP_DSHOW,
                "msmf": cv2.CAP_MSMF,
            }[args.backend]
            camera = cv2.VideoCapture(camera_id, backend)
            cameras.append(camera)
            if not camera.isOpened():
                raise RuntimeError(f"Cannot open camera {camera_id}")
            if args.input_format != "auto":
                if not camera.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter.fourcc(*args.input_format)):
                    print(
                        f"Camera {camera_id}: requested input format {args.input_format} "
                        "was not accepted",
                        file=sys.stderr,
                    )
            camera.set(cv2.CAP_PROP_FRAME_WIDTH, args.width)
            camera.set(cv2.CAP_PROP_FRAME_HEIGHT, args.height)
            camera.set(cv2.CAP_PROP_FPS, args.fps)
            buffered = camera.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            fourcc = int(camera.get(cv2.CAP_PROP_FOURCC))
            format_name = "".join(chr((fourcc >> (8 * i)) & 255) for i in range(4)).strip("\x00")
            print(
                f"Camera {camera_id}: backend={camera.getBackendName()} "
                f"input={format_name or 'unknown'} "
                f"{camera.get(cv2.CAP_PROP_FRAME_WIDTH):g}x"
                f"{camera.get(cv2.CAP_PROP_FRAME_HEIGHT):g} "
                f"fps={camera.get(cv2.CAP_PROP_FPS):g} buffer=1 accepted={buffered}",
                flush=True,
            )
        for camera_id, camera in zip(args.cameras, cameras, strict=True):
            readers.append(CameraReader(camera, camera_id))
        return readers
    except BaseException:
        for reader in readers:
            reader.release()
        for camera in cameras[len(readers) :]:
            camera.release()
        raise


class Take:
    """Resample complete camera batches to a common constant-FPS timeline."""

    def __init__(
        self,
        path: Path,
        args: argparse.Namespace,
        frames: list[np.ndarray],
        started: float,
    ) -> None:
        path.mkdir()
        self.path = path
        self.fps = args.fps
        self.started = started
        self.writers = []
        self.csv_file = None
        self.count = 0
        self.duplicates = 0
        self.skipped = 0
        self.previous = None
        self.markers: list[dict] = []
        self.sizes = [(frame.shape[1], frame.shape[0]) for frame in frames]
        self.metadata = {
            "started_at": datetime.now().astimezone().isoformat(),
            "camera_ids": args.cameras,
            "sizes": self.sizes,
            "fps": self.fps,
            "codec": args.codec,
            "timestamp_description": "Host monotonic time after read, relative to take start; "
            "not sensor exposure time. Latest frames sampled independently; identical camera timestamps indicate reused images. Repeated batches fill slow output.",
        }
        try:
            extension = "mp4" if args.codec == "mp4v" else "avi"
            for camera_id, size in zip(args.cameras, self.sizes, strict=True):
                writer = cv2.VideoWriter(
                    str(path / f"camera_{camera_id}.{extension}"),
                    cv2.VideoWriter.fourcc(*args.codec),
                    self.fps,
                    size,
                )
                self.writers.append(writer)
                if not writer.isOpened():
                    raise RuntimeError(
                        f"Cannot create video for camera {camera_id}; try --codec MJPG"
                    )
            self.csv_file = (path / "frames.csv").open("w", newline="", encoding="utf-8")
            self.csv = csv.writer(self.csv_file)
            self.csv.writerow(
                ["frame", "video_seconds", "repeated"]
                + [f"camera_{i}_grab_seconds" for i in args.cameras]
            )
            self.save_metadata("recording")
        except BaseException:
            self.close("initialization_error")
            raise

    def save_metadata(self, reason: str) -> None:
        data = self.metadata | {
            "status": reason,
            "frames": self.count,
            "video_seconds": self.count / self.fps,
            "repeated_batches": self.duplicates,
            "skipped_batches": self.skipped,
            "markers": self.markers,
        }
        temporary = self.path / "metadata.tmp"
        temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(self.path / "metadata.json")

    def _write(self, frames: list[np.ndarray], stamps: list[float], repeated: bool) -> None:
        for writer, frame in zip(self.writers, frames, strict=True):
            writer.write(frame)
        self.csv.writerow(
            [self.count, f"{self.count / self.fps:.6f}", int(repeated)]
            + [f"{stamp - self.started:.6f}" for stamp in stamps]
        )
        self.count += 1
        self.duplicates += int(repeated)

    def write(self, frames: list[np.ndarray], stamps: list[float], now: float) -> None:
        if [(f.shape[1], f.shape[0]) for f in frames] != self.sizes:
            raise RuntimeError("Camera resolution changed during recording")
        target = max(0, int((now - self.started) * self.fps))
        if target < self.count:
            self.skipped += 1
            return
        if self.previous is not None:
            while self.count < target:
                self._write(*self.previous, repeated=True)
        self._write(frames, stamps, repeated=False)
        self.previous = ([frame.copy() for frame in frames], stamps[:])
        assert self.csv_file is not None
        self.csv_file.flush()

    def marker(self, now: float) -> None:
        self.markers.append(
            {
                "number": len(self.markers) + 1,
                "elapsed_seconds": now - self.started,
                "last_written_frame": self.count - 1,
            }
        )
        self.save_metadata("recording")
        print(f"Marker {len(self.markers)} at {now - self.started:.2f}s", flush=True)

    def finish_duration(self, seconds: float) -> None:
        """Fill the final interval when the next capture crosses the time limit."""
        if self.previous is not None:
            while self.count < math.ceil(seconds * self.fps):
                self._write(*self.previous, repeated=True)

    def close(self, reason: str) -> None:
        for writer in self.writers:
            writer.release()
        self.writers.clear()
        if self.csv_file is not None:
            self.csv_file.close()
        self.save_metadata(reason)


def preview(
    frames: list[np.ndarray], ids: list[int], status: str, stamps: list[float] | None = None
) -> np.ndarray:
    tiles = []
    for index, (camera_id, frame) in enumerate(zip(ids, frames, strict=True)):
        height, width = frame.shape[:2]
        scale = min(480 / width, 300 / height)
        resized = cv2.resize(frame, (max(1, int(width * scale)), max(1, int(height * scale))))
        tile = np.zeros((340, 480, 3), dtype=np.uint8)
        h, w = resized.shape[:2]
        tile[40 : 40 + h, (480 - w) // 2 : (480 - w) // 2 + w] = resized
        cv2.putText(
            tile,
            f"Camera {camera_id} | {status}",
            (10, 26),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (40, 230, 80),
            1,
        )
        if stamps is not None:
            age_ms = max(0, (time.monotonic() - stamps[index]) * 1000)
            cv2.putText(
                tile,
                f"Host frame age: {age_ms:.0f} ms",
                (10, 58),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.45,
                (0, 220, 255),
                1,
            )
        tiles.append(tile)
    columns = min(3, len(tiles))
    rows = math.ceil(len(tiles) / columns)
    canvas = np.zeros((rows * 340, columns * 480, 3), dtype=np.uint8)
    for index, tile in enumerate(tiles):
        row, column = divmod(index, columns)
        canvas[row * 340 : (row + 1) * 340, column * 480 : (column + 1) * 480] = tile
    return canvas


def save_snapshot(session: Path, ids: list[int], frames: list[np.ndarray]) -> None:
    directory = Path(tempfile.mkdtemp(prefix="snapshot_", dir=session))
    for camera_id, frame in zip(ids, frames, strict=True):
        if not cv2.imwrite(str(directory / f"camera_{camera_id}.png"), frame):
            raise RuntimeError(f"Failed to save snapshot for camera {camera_id}")
    print(f"Snapshot: {directory}", flush=True)


def read_preview_key() -> int:
    """Keep Qt's optional save-dialog errors separate from recording failures."""
    try:
        return cv2.waitKey(1) & 0xFF
    except cv2.error as error:
        if "saveView" not in str(error) or "file extension not recognized" not in str(error):
            raise
        print(
            "OpenCV preview save failed: use the S key without Ctrl to save PNG snapshots. "
            "Recording continues.",
            file=sys.stderr,
        )
        return -1


def run(args: argparse.Namespace) -> int:
    cameras = []
    take = None
    reason = "stopped"
    result = 0
    try:
        cameras = open_cameras(args)
        frames, stamps = capture_frames(cameras)
        args.output.mkdir(parents=True, exist_ok=True)
        session = Path(
            tempfile.mkdtemp(prefix=datetime.now().strftime("%Y%m%d_%H%M%S_"), dir=args.output)
        )
        print(f"Session: {session.resolve()}", flush=True)
        print("R/Space: start/stop (cancel countdown), S: snapshot, M: marker, Q/Esc: quit")
        print(f"Actual resolutions: {[(f.shape[1], f.shape[0]) for f in frames]}")
        if not args.no_preview:
            configure_qt_fonts()
            cv2.namedWindow(WINDOW, cv2.WINDOW_NORMAL | cv2.WINDOW_GUI_NORMAL)
        pending = time.monotonic() + args.countdown if args.auto_start or args.no_preview else None
        take_number = 0
        disk_check = 0.0
        while True:
            loop_start = time.monotonic()
            frames, stamps = capture_frames(cameras)
            now = time.monotonic()
            if now >= disk_check:
                if shutil.disk_usage(session).free < args.min_free_mb * 1024 * 1024:
                    raise RuntimeError("Free disk space below --min-free-mb; stopping")
                disk_check = now + 1
            if pending is not None and now >= pending:
                take_number += 1
                take = Take(session / f"take_{take_number:03d}", args, frames, now)
                pending = None
                print(f"Recording: {take.path}", flush=True)
            if take is not None:
                if args.duration and now - take.started >= args.duration:
                    take.finish_duration(args.duration)
                    take.close("duration_reached")
                    print(f"Saved: {take.path} ({take.count} frames)", flush=True)
                    take = None
                    if args.no_preview or args.auto_start:
                        break
                else:
                    take.write(frames, stamps, now)
            status = "READY"
            if pending is not None:
                status = f"START IN {max(0, math.ceil(pending - now))}"
            elif take is not None:
                status = f"REC {now - take.started:.1f}s DUP {take.duplicates}"
            key = -1
            if not args.no_preview:
                # Encoding may take time; show a fresh sample rather than the saved batch.
                frames, stamps = capture_frames(cameras)
                cv2.imshow(WINDOW, preview(frames, args.cameras, status, stamps))
                key = read_preview_key()
                if cv2.getWindowProperty(WINDOW, cv2.WND_PROP_VISIBLE) < 1:
                    break
            if key in (27, ord("q")):
                break
            if key in (ord("r"), ord(" ")):
                if take is not None:
                    take.close("stopped")
                    print(f"Saved: {take.path} ({take.count} frames)", flush=True)
                    take = None
                elif pending is not None:
                    pending = None
                else:
                    pending = now + args.countdown
            elif key == ord("s"):
                save_snapshot(session, args.cameras, frames)
            elif key == ord("m") and take is not None:
                take.marker(time.monotonic())
            time.sleep(max(0, 1 / args.fps - (time.monotonic() - loop_start)))
    except KeyboardInterrupt:
        reason = "interrupted"
    except (RuntimeError, OSError, cv2.error) as error:
        reason = "error"
        result = 1
        print(f"Recording error: {error}", file=sys.stderr)
    finally:
        try:
            if take is not None:
                take.close(reason)
                print(f"Saved: {take.path} ({take.count} frames)", flush=True)
        finally:
            for camera in cameras:
                camera.release()
            if not args.no_preview:
                cv2.destroyAllWindows()
    return result


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    def interrupt(signum: int, frame: object) -> None:
        raise KeyboardInterrupt

    previous = signal.signal(signal.SIGTERM, interrupt)
    try:
        return run(args)
    finally:
        signal.signal(signal.SIGTERM, previous)


if __name__ == "__main__":
    raise SystemExit(main())
