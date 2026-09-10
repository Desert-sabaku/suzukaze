# Gesture Detection

OpenCV camera or video-file input is processed by two independent workers:

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
uv run python -m modules.app
```

Press `Esc` in the camera window to exit.

## Input source

By default, the application uses camera `0`. To process a video file, set
`VIDEO_SOURCE` in `modules/config.py`:

```python
VIDEO_SOURCE = PROJECT_ROOT / "sample.mp4"
```

Set it back to `None` to use the camera again. The application exits when the
video reaches its end. When a video file is used, the annotated output is saved
to `VIDEO_OUTPUT_PATH` (by default, `output.mp4` in the project root). The
output does not contain the source video's audio track.

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
uv run python -m pytest
```

Optional syntax check:

```bash
uv run python -m compileall modules
```

**Model requirements:**
- The MediaPipe pose model (`pose_landmarker_lite.task`) downloads automatically when missing.
- The YOLO model (`yolov8n.pt`) must be obtained separately and placed in the project root. You can download it from the [Ultralytics repository](https://github.com/ultralytics/assets/releases) or it will be downloaded automatically by the ultralytics library on first use.

## Structure

- `modules/app.py`: input loop, worker lifecycle, action integration
- `modules/pose_worker.py`: MediaPipe inference and temporal gesture state
- `modules/yolo_worker.py`: bottle detection
- `modules/rendering.py`: OpenCV drawing helpers
- `modules/config.py`: model paths and thresholds
- `modules/ipc.py`: latest-value queue operations

## CI

On pull requests, GitHub Actions runs:

- Ruff (`format --check` + `check`)
- Pyright (type checking)
- Pytest (tests + coverage report)
