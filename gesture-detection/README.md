# Gesture Detection

OpenCV camera input is processed by two independent workers:

- MediaPipe Pose detects body landmarks and classifies fanning, sprinkling water, and relaxing.
- YOLO detects a Ramune bottle; touching the detected bottle with the right wrist selects the Ramune action.

## Run

The project uses Python 3.9+ and `uv`:

```bash
uv sync
uv run gesture-detection
```

Alternatively, you can run the Python module directly:

```bash
uv run python -m gesture_detection.app
```

Press `Esc` in the camera window to exit.

**Model requirements:**
- The MediaPipe pose model (`pose_landmarker_lite.task`) downloads automatically when missing.
- The YOLO model (`yolov8n.pt`) must be obtained separately and placed in the project root. You can download it from the [Ultralytics repository](https://github.com/ultralytics/assets/releases) or it will be downloaded automatically by the ultralytics library on first use.

## Structure

- `gesture_detection/app.py`: camera loop, worker lifecycle, action integration
- `gesture_detection/pose_worker.py`: MediaPipe inference and temporal gesture state
- `gesture_detection/yolo_worker.py`: bottle detection
- `gesture_detection/rendering.py`: OpenCV drawing helpers
- `gesture_detection/config.py`: model paths and thresholds
- `gesture_detection/ipc.py`: latest-value queue operations