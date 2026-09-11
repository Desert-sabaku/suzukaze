import datetime
import os
from pathlib import Path

import cv2
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env", override=False)


def _env_path(name: str, default: str) -> Path:
    """Resolve relative paths from the project root, regardless of working directory."""
    value = Path(os.environ.get(name) or default).expanduser()
    return value if value.is_absolute() else PROJECT_ROOT / value


POSE_MODEL_PATH = _env_path("POSE_MODEL_PATH", "pose_landmarker_lite.task")
POSE_MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/pose_landmarker/"
    "pose_landmarker_lite/float16/1/pose_landmarker_lite.task"
)
YOLO_MODEL_PATH = _env_path("YOLO_MODEL_PATH", "yolov8n.pt")

FPS = 60
CAMERA_INDEX = int(os.environ.get("CAMERA_INDEX", "0"))
CAMERA_BACKEND = int(os.environ.get("CAMERA_BACKEND", str(cv2.CAP_ANY)))
CAMERA_FOURCC = os.environ.get("CAMERA_FOURCC", "MJPG")
if len(CAMERA_FOURCC) != 4:
    raise ValueError("CAMERA_FOURCC must contain exactly four characters")

# An empty source selects camera input.
VIDEO_SOURCE: Path | None = (
    _env_path("VIDEO_SOURCE", "") if os.environ.get("VIDEO_SOURCE") else None
)
OUTPUT_DIR = _env_path("OUTPUT_DIR", "output")
_output_name = VIDEO_SOURCE.name if VIDEO_SOURCE is not None else "camera"
VIDEO_OUTPUT_PATH = _env_path(
    "VIDEO_OUTPUT_PATH",
    str(OUTPUT_DIR / f"{_output_name}{datetime.date.today()}.output.mp4"),
)

# Maximum queued output frames; full buffers apply backpressure without dropping.
VIDEO_OUTPUT_BUFFER_FRAMES = int(os.environ.get("VIDEO_OUTPUT_BUFFER_FRAMES", "8"))
FPS = int(os.environ.get("FPS", "30"))
if FPS <= 0 or VIDEO_OUTPUT_BUFFER_FRAMES <= 0:
    raise ValueError("FPS and VIDEO_OUTPUT_BUFFER_FRAMES must be positive integers")

WINDOW_SECONDS = 1
BUFFER_SIZE = FPS * WINDOW_SECONDS
TARGET_LANDMARKS = (0, 11, 12, 15, 16)
RIGHT_WRIST_INDEX = 16
YOLO_BOTTLE_CLASS_ID = 39
YOLO_CONFIDENCE_THRESHOLD = 0.5
YOLO_TTL_SECONDS = 0.5
YOLO_EMA_ALPHA = 0.3

READY_FACE_EXCLUSION_DISTANCE = 1.0
FANNING_FACE_DISTANCE = 1.5

WINDOW_TITLE = "Gesture Recognition (Async Pipeline)"
POSE_CONNECTIONS = (
    (0, 1),
    (1, 2),
    (2, 3),
    (3, 7),
    (0, 4),
    (4, 5),
    (5, 6),
    (6, 8),
    (9, 10),
    (11, 12),
    (11, 13),
    (13, 15),
    (15, 17),
    (15, 19),
    (15, 21),
    (17, 19),
    (12, 14),
    (14, 16),
    (16, 18),
    (16, 20),
    (16, 22),
    (18, 20),
    (11, 23),
    (12, 24),
    (23, 24),
    (23, 25),
    (24, 26),
    (25, 27),
    (26, 28),
    (27, 29),
    (28, 30),
    (29, 31),
    (30, 32),
    (27, 31),
    (28, 32),
)
