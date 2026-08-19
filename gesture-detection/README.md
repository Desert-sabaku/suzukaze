# Gesture Detection

OpenCV camera input is processed by two independent workers:

- MediaPipe Pose detects body landmarks and classifies fanning, sprinkling water, and relaxing.
- YOLO detects a Ramune bottle; touching the detected bottle with the right wrist selects the Ramune action.

## Run

The project uses Python 3.14 and `uv`:

```powershell
uv sync
uv run python fanning_detector.py
```

Press `Esc` in the camera window to exit. The pose model is downloaded automatically when it is missing.

## Structure

- `gesture_detection/app.py`: camera loop, worker lifecycle, action integration
- `gesture_detection/pose_worker.py`: MediaPipe inference and temporal gesture state
- `gesture_detection/yolo_worker.py`: bottle detection
- `gesture_detection/rendering.py`: OpenCV drawing helpers
- `gesture_detection/config.py`: model paths and thresholds
- `gesture_detection/ipc.py`: latest-value queue operations