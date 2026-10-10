import math
import os
from datetime import datetime
from os import getenv
from pathlib import Path

import cv2

from gesture_detection.frame_rotation import ROTATIONS
from gesture_detection.qt_setup import configure_qt_fonts
from gesture_detection.settings import Settings

# The OpenCV wheel overwrites QT_QPA_FONTDIR during ``import cv2`` with a
# directory which is no longer shipped. Restore the system font path after the
# import and before the first HighGUI window is created.
configure_qt_fonts()

# Editable src layout keeps models and config.toml at the project root. A wheel
# installation uses an explicit data root, or the working directory.
_source_root = Path(__file__).resolve().parents[2]
_default_root = _source_root if (_source_root / "pyproject.toml").is_file() else Path.cwd()
PROJECT_ROOT = Path(getenv("GESTURE_PROJECT_ROOT") or _default_root).expanduser().resolve()
_config_override = getenv("GESTURE_CONFIG_PATH")
_config_file = Path(_config_override or "config.toml").expanduser()
CONFIG_PATH = _config_file if _config_file.is_absolute() else PROJECT_ROOT / _config_file
_settings = Settings(PROJECT_ROOT, CONFIG_PATH, required=_config_override is not None)


POSE_MODEL_PATH = _settings.path("models", "pose", "pose_landmarker_heavy.task")
_pose_name = POSE_MODEL_PATH.stem
POSE_MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/pose_landmarker/"
    f"{_pose_name}/float16/1/{_pose_name}.task"
    if POSE_MODEL_PATH.name
    in {f"pose_landmarker_{size}.task" for size in ("lite", "full", "heavy")}
    else None
)
# Use temporal tracking by default; retain IMAGE for baseline comparisons.
POSE_RUNNING_MODE = _settings.text("pose", "running_mode", "VIDEO").strip().upper()
POSE_DISPLAY_SMOOTHING = _settings.boolean("pose", "display_smoothing", True)
POSE_DISPLAY_TIME_CONSTANT = 0.06
POSE_DISPLAY_MAX_GAP = 0.25
if POSE_RUNNING_MODE not in {"IMAGE", "VIDEO"}:
    raise ValueError("POSE_RUNNING_MODE must be IMAGE or VIDEO")
# Selection uses the torso center in normalized full-frame coordinates.
POSE_SELECT_SUBJECT = _settings.boolean("pose", "select_subject", True)
_subject_area = _settings.get("pose.subject", "area", [0.35, 0.15, 0.75, 0.90])
if not isinstance(_subject_area, list) or any(
    type(value) not in (int, float) for value in _subject_area
):
    raise ValueError("pose.subject.area must be an array of numbers")
SUBJECT_AREA = tuple(float(value) for value in _subject_area)
if (
    len(SUBJECT_AREA) != 4
    or any(not math.isfinite(v) or not 0 <= v <= 1 for v in SUBJECT_AREA)
    or SUBJECT_AREA[0] >= SUBJECT_AREA[2]
    or SUBJECT_AREA[1] >= SUBJECT_AREA[3]
):
    raise ValueError("SUBJECT_AREA must be left,top,right,bottom within 0..1")
SUBJECT_MIN_TORSO_HEIGHT = _settings.number("pose.subject", "min_torso_height", 0.18)
SUBJECT_MIN_SHOULDER_WIDTH = _settings.number("pose.subject", "min_shoulder_width", 0.10)
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

BOOTH_DWELL_SECONDS = _settings.number("booth", "dwell_seconds", 1.0)
BOOTH_RELEASE_SECONDS = _settings.number("booth", "release_seconds", 0.5)
if any(not math.isfinite(v) or v <= 0 for v in (BOOTH_DWELL_SECONDS, BOOTH_RELEASE_SECONDS)):
    raise ValueError("Booth durations must be positive and finite")

SUPPRESS_MEDIAPIPE_STARTUP_LOGS = _settings.boolean(
    "diagnostics", "suppress_mediapipe_startup_logs", True
)

# The retired YOLO bottle detector left this key in older config.toml files.
_settings.get("models", "yolo", None)

CAMERA_BACKEND = _settings.integer("camera", "backend", cv2.CAP_ANY)
CAMERA_FOURCC = _settings.text("camera", "fourcc", "MJPG")
CAMERA_ROTATION = _settings.text("camera", "rotation", "none").strip().lower()
if CAMERA_ROTATION not in ROTATIONS:
    raise ValueError(f"camera.rotation must be one of: {', '.join(ROTATIONS)}")
if len(CAMERA_FOURCC) != 4:
    raise ValueError("CAMERA_FOURCC must contain exactly four characters")

# An empty source selects camera input.
VIDEO_SOURCE = _settings.optional_path("video", "source")
OUTPUT_DIR = _settings.path("output", "directory", "output")
_output_name = os.path.splitext(VIDEO_SOURCE.name)[0] if VIDEO_SOURCE is not None else "camera"
VIDEO_OUTPUT_PATH = _settings.optional_path("output", "path") or (
    OUTPUT_DIR / f"{_output_name}{int(datetime.now().timestamp())}.output.mp4"
)

# Maximum queued output frames; full buffers apply backpressure without dropping.
VIDEO_OUTPUT_BUFFER_FRAMES = _settings.integer("output", "buffer_frames", 8)
FPS = _settings.integer("camera", "fps", 30)
if FPS <= 0 or VIDEO_OUTPUT_BUFFER_FRAMES <= 0:
    raise ValueError("FPS and VIDEO_OUTPUT_BUFFER_FRAMES must be positive integers")

# The learned profile is opt-in and supplies its own continuously masked input.
RAMUNE_DETECTOR = _settings.text("ramune", "detector", "rules").strip().lower()
if RAMUNE_DETECTOR not in {"rules", "learned"}:
    raise ValueError("RAMUNE_DETECTOR must be rules or learned")
RAMUNE_LEARNED_MODEL_PATH = _settings.optional_path("ramune", "learned_model") or (
    Path(__file__).with_name("models") / "ramune_0924.npz"
)

WINDOW_SECONDS = 1
BUFFER_SIZE = FPS * WINDOW_SECONDS
# Stillness is measured in torso heights and source seconds.
RELAXING_LANDMARKS = (0, 11, 12, 13, 14, 15, 16, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32)
RELAXING_TORSO_LANDMARKS = (11, 12, 23, 24)
RELAXING_MIN_VISIBILITY = 0.5
RELAXING_MAX_SPEED = 0.40
RELAXING_MAX_DRIFT = 0.055
RELAXING_DWELL_SECONDS = 1.0
RELAXING_MAX_FRAME_GAP = 0.25
# Bow is a sustained, side-visible hip hinge; angles are measured from vertical.
BOW_MIN_ANGLE_DEGREES = 20.0
BOW_MAX_ANGLE_DEGREES = 75.0
# Compare hip-to-face and hip-to-shoulder directions, not a neck angle.
BOW_MAX_HEAD_DEVIATION_DEGREES = 40.0
BOW_DWELL_SECONDS = 0.25
BOW_MAX_FRAME_GAP = 0.25
BOW_MIN_VISIBILITY = 0.5
# The nose becomes partially occluded in an oblique bow; torso visibility stays strict.
BOW_HEAD_MIN_VISIBILITY = 0.35
# A bowing head can leave the side of a close camera; MediaPipe still estimates it.
BOW_HEAD_FRAME_MARGIN = 0.10
RIGHT_WRIST_INDEX = 16

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
# Preparation can be wider than the final press/contact alignment.
RAMUNE_READY_ALIGN_TOLERANCE = 0.70
# Preparation needs roughly stacked hands: horizontal gap / vertical gap.
# 0.70 is about 35 degrees from vertical.
RAMUNE_READY_MAX_SLOPE = 0.70
# Allow landmark drift across the hand, especially sideways. Relative closing
# motion still distinguishes a press from moving both hands down together.
RAMUNE_BASE_X_TOLERANCE = 0.75
RAMUNE_BASE_TOLERANCE = 0.50
# Separate upper-hand upward excursions from lower-hand position tolerance.
RAMUNE_UPPER_RAISE_TOLERANCE = 0.30
RAMUNE_MIN_READY_GAP = 0.30
RAMUNE_MAX_READY_GAP = 0.90
# Once prepared, allow a higher backswing before the downward press.
RAMUNE_MAX_WINDUP_GAP = 1.50
RAMUNE_WINDUP_SECONDS = 1.0
RAMUNE_CONTACT_GAP = 0.30
RAMUNE_MIN_PRESS = 0.25
RAMUNE_DWELL_SECONDS = 0.25
RAMUNE_PRESS_TIMEOUT = 3.0
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

# Motion-quality observation requirements (separate from classifier scores).
ACCURACY_FANNING_MIN_SECONDS = 0.6
ACCURACY_FANNING_MAX_GAP = 0.25
ACCURACY_FANNING_MIN_HZ = 1.0
ACCURACY_FANNING_MAX_HZ = 3.0

# Let the scoop/release leave the FFT window before accepting residual fanning.
FANNING_UCHIMIZU_GRACE_SECONDS = WINDOW_SECONDS

# Opt-in paired-camera profile, frozen from the 0928 event experiment.
MULTICAM_SCOOP_MIN_MOTION_SECONDS = 0.08
MULTICAM_RELEASE_SECONDS = 0.3
MULTICAM_RELEASE_MAX_GAP = 0.25
MULTICAM_FUSION_FPS = 30.0
MULTICAM_MAX_AGE_SECONDS = 0.2
MULTICAM_EVENT_DEDUP_SECONDS = 0.6
# A live camera may drop a few reads (USB bandwidth, a nudged cable). Reopen it
# after this many consecutive failures, and give up after the larger count.
CAMERA_REOPEN_AFTER_FAILURES = 15
CAMERA_MAX_READ_FAILURES = 90


MULTICAM_ENABLED = _settings.boolean("multicam", "enabled", False)
_camera_indices = _settings.get("camera", "indices", [])
if not isinstance(_camera_indices, list) or any(
    type(value) is not int for value in _camera_indices
):
    raise ValueError("camera.indices must be an array of camera IDs")
CAMERA_INDICES: tuple[int, ...] | None = tuple(_camera_indices) if _camera_indices else None
if CAMERA_INDICES is not None and (
    len(CAMERA_INDICES) != (2 if MULTICAM_ENABLED else 1)
    or len(set(CAMERA_INDICES)) != len(CAMERA_INDICES)
    or min(CAMERA_INDICES) < 0
):
    raise ValueError("camera.indices must contain one ID (or two distinct IDs in multicamera mode)")
CAMERA_SCAN_MAX_INDEX = _settings.integer("camera", "scan_max_index", 9)
if not 0 <= CAMERA_SCAN_MAX_INDEX <= 9:
    raise ValueError("CAMERA_SCAN_MAX_INDEX must be between 0 and 9")
RECORD_LIVE_VIDEO = _settings.boolean("output", "record_live", False)
MULTICAM_SELECT_SUBJECT = (
    _settings.boolean("multicam.first", "select_subject", True),
    _settings.boolean("multicam.second", "select_subject", False),
)
MULTICAM_ROTATION = tuple(
    _settings.text(f"multicam.{slot}", "rotation", "none").strip().lower()
    for slot in ("first", "second")
)
if any(rotation not in ROTATIONS for rotation in MULTICAM_ROTATION):
    raise ValueError(f"multicam rotation must be one of: {', '.join(ROTATIONS)}")
MULTICAM_VIDEO_SESSION = _settings.optional_path("multicam.replay", "session")
MULTICAM_TRACE_PATH = _settings.optional_path("diagnostics", "multicam_trace")
MULTICAM_HEADLESS = _settings.boolean("multicam", "headless", False)
MULTICAM_WIDTH = _settings.integer("multicam", "width", 1280)
MULTICAM_HEIGHT = _settings.integer("multicam", "height", 720)
ANNOTATION_DEFAULT_PAGE = _settings.text("annotation", "default_page", "intervals").strip().lower()
if ANNOTATION_DEFAULT_PAGE not in {"intervals", "landmarks"}:
    raise ValueError("ANNOTATION_DEFAULT_PAGE must be intervals or landmarks")
ANNOTATION_NINE_POINT_ASSIST = _settings.boolean("annotation", "nine_point_landmark_assist", False)
if min(MULTICAM_WIDTH, MULTICAM_HEIGHT) <= 0:
    raise ValueError("MULTICAM_WIDTH and MULTICAM_HEIGHT must be positive")
if MULTICAM_ENABLED and (POSE_RUNNING_MODE != "VIDEO" or RAMUNE_DETECTOR != "rules"):
    raise ValueError(
        'Multicamera recognition requires pose.running_mode="VIDEO" and ramune.detector="rules"'
    )
if MULTICAM_ENABLED and VIDEO_SOURCE is not None:
    raise ValueError("Use multicam.replay.session instead of video.source in multicamera mode")

# Occurrence lifetime, used by multicamera fusion to drop late events.
GESTURE_EVENT_TTL = _settings.number("events", "ttl_seconds", 1.0)
if not math.isfinite(GESTURE_EVENT_TTL) or GESTURE_EVENT_TTL <= 0:
    raise ValueError("GESTURE_EVENT_TTL must be finite and positive")

_settings.finish()
