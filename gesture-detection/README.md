# Gesture Detection

OpenCV camera input is processed by two independent workers:

- MediaPipe Pose detects body landmarks and classifies fanning, sprinkling water, and relaxing.
- YOLO detects a Ramune bottle; touching the detected bottle with the right wrist selects the Ramune action.

## Run

The project uses Python 3.12+ and `uv`:

```bash
uv sync
uv run gesture-detection
```

Alternatively, you can run the Python module directly:

```bash
uv run python -m gesture_detection.app
```

Press `Esc` in the camera window to exit.

## Quality checks (local)

Install development dependencies:

```bash
uv sync --group dev
```

Run formatter, linter, type checker, and tests:

```bash
uv run ruff format --check $(git ls-files '*.py')
uv run ruff check $(git ls-files '*.py')
uv run pyright
uv run pytest
```

Optional syntax check:

```bash
uv run python -m compileall gesture_detection
```

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

## CI

On pull requests, GitHub Actions runs:

- Ruff (`format --check` + `check`)
- Pyright (type checking)
- Pytest (tests + coverage report)