import os
from datetime import datetime
from os import getenv
from pathlib import Path

import cv2
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env", override=False)


def _env_path(name: str, default: str) -> Path:
    """Resolve relative paths from the project root, regardless of working directory."""
    value = Path(getenv(name) or default).expanduser()
    return value if value.is_absolute() else PROJECT_ROOT / value


POSE_MODEL_PATH = _env_path("POSE_MODEL_PATH", "pose_landmarker_lite.task")
POSE_MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/pose_landmarker/"
    "pose_landmarker_lite/float16/1/pose_landmarker_lite.task"
)
# Keep IMAGE as the baseline until VIDEO recognition accuracy has been validated.
POSE_RUNNING_MODE = getenv("POSE_RUNNING_MODE", "IMAGE").strip().upper()
if POSE_RUNNING_MODE not in {"IMAGE", "VIDEO"}:
    raise ValueError("POSE_RUNNING_MODE must be IMAGE or VIDEO")

YOLO_MODEL_PATH = _env_path("YOLO_MODEL_PATH", "yolov8n.pt")

CAMERA_INDEX = int(getenv("CAMERA_INDEX", "0"))
CAMERA_BACKEND = int(getenv("CAMERA_BACKEND", str(cv2.CAP_ANY)))
CAMERA_FOURCC = getenv("CAMERA_FOURCC", "MJPG")
if len(CAMERA_FOURCC) != 4:
    raise ValueError("CAMERA_FOURCC must contain exactly four characters")

# An empty source selects camera input.
VIDEO_SOURCE: Path | None = _env_path("VIDEO_SOURCE", "") if getenv("VIDEO_SOURCE") else None
OUTPUT_DIR = _env_path("OUTPUT_DIR", "output")
_output_name = os.path.splitext(VIDEO_SOURCE.name)[0] if VIDEO_SOURCE is not None else "camera"
VIDEO_OUTPUT_PATH = _env_path(
    "VIDEO_OUTPUT_PATH",
    str(OUTPUT_DIR / f"{_output_name}{int(datetime.now().timestamp())}.output.mp4"),
)

# Maximum queued output frames; full buffers apply backpressure without dropping.
VIDEO_OUTPUT_BUFFER_FRAMES = int(getenv("VIDEO_OUTPUT_BUFFER_FRAMES", "8"))
FPS = int(getenv("FPS", "30"))
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
# Wrist must stay in the upper half of the torso (or higher) before fanning.
FANNING_MAX_TORSO_HEIGHT = 0.5
FANNING_POSITION_DWELL_SECONDS = 0.2

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

# Ramune distances are measured in shoulder widths; times use source seconds.
RAMUNE_ALIGN_TOLERANCE = 0.60
# Allow landmark drift across the hand, especially sideways. Relative closing
# motion still distinguishes a press from moving both hands down together.
RAMUNE_BASE_X_TOLERANCE = 0.50
RAMUNE_BASE_TOLERANCE = 0.30
RAMUNE_MIN_READY_GAP = 0.30
RAMUNE_MAX_READY_GAP = 0.90
RAMUNE_CONTACT_GAP = 0.30
RAMUNE_MIN_PRESS = 0.25
RAMUNE_DWELL_SECONDS = 0.25
RAMUNE_PRESS_TIMEOUT = 1.5
RAMUNE_HOLD_SECONDS = 0.8
RAMUNE_MAX_FRAME_GAP = 0.5

# Sprinkling distances are relative to shoulder-to-hip height.
UCHIMIZU_MIN_RAISE = 0.10
UCHIMIZU_MIN_DROP = 0.15
UCHIMIZU_LOW_HEIGHT = 0.55
UCHIMIZU_FINISH_HEIGHT = 0.50
UCHIMIZU_X_MARGIN = 0.25
UCHIMIZU_MAX_FRAME_GAP = 0.8
UCHIMIZU_RAISE_WINDOW_SECONDS = 1.2
UCHIMIZU_READY_TIMEOUT_SECONDS = 1.5
UCHIMIZU_FEEDBACK_SECONDS = 0.35
UCHIMIZU_COOLDOWN_SECONDS = 0.6

# Brief excursions below the fanning boundary must return promptly.
FANNING_POSITION_GRACE_SECONDS = 0.35
FANNING_EXIT_TORSO_HEIGHT = 0.75
FANNING_REVERSAL_DISTANCE = 0.08
FANNING_MIN_REVERSALS = 3
