from pathlib import Path

import cv2

PROJECT_ROOT = Path(__file__).resolve().parent.parent
POSE_MODEL_PATH = PROJECT_ROOT / "pose_landmarker_lite.task"
POSE_MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/pose_landmarker/"
    "pose_landmarker_lite/float16/1/pose_landmarker_lite.task"
)
YOLO_MODEL_PATH = PROJECT_ROOT / "yolov8n.pt"

# Camera settings may need to be changed to match the capture device/driver.
CAMERA_BACKEND = cv2.CAP_V4L2
CAMERA_FOURCC = "MJPG"

FPS = 60
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
