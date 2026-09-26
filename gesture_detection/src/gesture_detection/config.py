import math
import os
from datetime import datetime
from os import getenv
from pathlib import Path

import cv2
from dotenv import load_dotenv

# The OpenCV wheel overwrites QT_QPA_FONTDIR during ``import cv2`` with a
# directory which is no longer shipped. Restore the system font path after the
# import and before the first HighGUI window is created.
for _qt_font_directory in (
    Path("/usr/share/fonts/truetype/dejavu"),
    Path("/usr/share/fonts/truetype/noto"),
    Path("/usr/share/fonts/truetype"),
):
    if _qt_font_directory.is_dir():
        os.environ["QT_QPA_FONTDIR"] = str(_qt_font_directory)
        break

# Editable src layout keeps models and .env at the project root. A wheel
# installation uses an explicit data root, or the working directory.
_source_root = Path(__file__).resolve().parents[2]
_default_root = _source_root if (_source_root / "pyproject.toml").is_file() else Path.cwd()
PROJECT_ROOT = Path(getenv("GESTURE_PROJECT_ROOT") or _default_root).expanduser().resolve()
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
# Use temporal tracking by default; retain IMAGE for baseline comparisons.
POSE_RUNNING_MODE = getenv("POSE_RUNNING_MODE", "VIDEO").strip().upper()
POSE_DISPLAY_SMOOTHING = getenv("POSE_DISPLAY_SMOOTHING", "true").strip().lower() not in {
    "0",
    "false",
    "no",
    "off",
}
POSE_DISPLAY_TIME_CONSTANT = 0.06
POSE_DISPLAY_MAX_GAP = 0.25
if POSE_RUNNING_MODE not in {"IMAGE", "VIDEO"}:
    raise ValueError("POSE_RUNNING_MODE must be IMAGE or VIDEO")
# Selection uses the torso center in normalized full-frame coordinates.
POSE_SELECT_SUBJECT = getenv("POSE_SELECT_SUBJECT", "true").strip().lower() not in {
    "0",
    "false",
    "no",
    "off",
}
SUBJECT_AREA = tuple(float(v) for v in getenv("SUBJECT_AREA", "0.35,0.15,0.75,0.90").split(","))
if (
    len(SUBJECT_AREA) != 4
    or any(not math.isfinite(v) or not 0 <= v <= 1 for v in SUBJECT_AREA)
    or SUBJECT_AREA[0] >= SUBJECT_AREA[2]
    or SUBJECT_AREA[1] >= SUBJECT_AREA[3]
):
    raise ValueError("SUBJECT_AREA must be left,top,right,bottom within 0..1")
SUBJECT_MIN_TORSO_HEIGHT = float(getenv("SUBJECT_MIN_TORSO_HEIGHT", "0.18"))
SUBJECT_MIN_SHOULDER_WIDTH = float(getenv("SUBJECT_MIN_SHOULDER_WIDTH", "0.10"))
if any(
    not math.isfinite(v) or not 0 < v < 1
    for v in (SUBJECT_MIN_TORSO_HEIGHT, SUBJECT_MIN_SHOULDER_WIDTH)
):
    raise ValueError("Subject minimum dimensions must be finite and between 0 and 1")
SUBJECT_ACQUIRE_SECONDS = 0.2
SUBJECT_RELEASE_SECONDS = 0.5
SUBJECT_MAX_FRAME_GAP = 0.5
SUBJECT_MIN_VISIBILITY = 0.5
SUBJECT_MIN_SCALE_RATIO = 0.65
SUBJECT_MAX_SCALE_RATIO = 1.55
SUBJECT_MAX_CENTER_DISTANCE = 0.6

SUPPRESS_MEDIAPIPE_STARTUP_LOGS = getenv(
    "SUPPRESS_MEDIAPIPE_STARTUP_LOGS", "true"
).strip().lower() not in {"0", "false", "no", "off"}

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

# The learned profile is opt-in and supplies its own continuously masked input.
RAMUNE_DETECTOR = getenv("RAMUNE_DETECTOR", "rules").strip().lower()
if RAMUNE_DETECTOR not in {"rules", "learned"}:
    raise ValueError("RAMUNE_DETECTOR must be rules or learned")
RAMUNE_LEARNED_MODEL_PATH = _env_path(
    "RAMUNE_LEARNED_MODEL_PATH", str(Path(__file__).with_name("models") / "ramune_0924.npz")
)

WINDOW_SECONDS = 1
BUFFER_SIZE = FPS * WINDOW_SECONDS
# Stillness is measured in torso heights and source seconds.
RELAXING_LANDMARKS = (0, 11, 12, 13, 14, 15, 16, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32)
RELAXING_TORSO_LANDMARKS = (11, 12, 23, 24)
RELAXING_MIN_VISIBILITY = 0.5
RELAXING_MAX_SPEED = 0.30
RELAXING_MAX_DRIFT = 0.05
RELAXING_DWELL_SECONDS = 1.0
RELAXING_MAX_FRAME_GAP = 0.25
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

# Let the scoop/release leave the FFT window before accepting residual fanning.
FANNING_UCHIMIZU_GRACE_SECONDS = WINDOW_SECONDS

# Local gesture notifications, separate from unity_bridge's WebSocket port.
GESTURE_DELIVERY_ENABLED = getenv("GESTURE_DELIVERY_ENABLED", "false").lower() in {
    "1",
    "true",
    "yes",
    "on",
}
GESTURE_DELIVERY_HOST = "127.0.0.1"
GESTURE_DELIVERY_PORT = int(getenv("GESTURE_DELIVERY_PORT", "5001"))
GESTURE_STATE_INTERVAL = float(getenv("GESTURE_STATE_INTERVAL", "0.1"))
GESTURE_STALE_TIMEOUT = float(getenv("GESTURE_STALE_TIMEOUT", "0.5"))
GESTURE_EVENT_TTL = float(getenv("GESTURE_EVENT_TTL", "1.0"))
GESTURE_RETRY_INTERVAL = float(getenv("GESTURE_RETRY_INTERVAL", "0.1"))
GESTURE_MAX_PENDING = int(getenv("GESTURE_MAX_PENDING", "64"))
if not 1 <= GESTURE_DELIVERY_PORT <= 65535 or GESTURE_MAX_PENDING <= 0:
    raise ValueError("Gesture delivery port or capacity is invalid")
if any(
    not math.isfinite(value) or value <= 0
    for value in (
        GESTURE_STATE_INTERVAL,
        GESTURE_STALE_TIMEOUT,
        GESTURE_EVENT_TTL,
        GESTURE_RETRY_INTERVAL,
    )
):
    raise ValueError("Gesture delivery durations must be finite and positive")
if GESTURE_STATE_INTERVAL >= GESTURE_STALE_TIMEOUT:
    raise ValueError("Gesture state interval must be shorter than stale timeout")
