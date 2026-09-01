# Repository Guidelines

## Project Structure & Module Organization

The runnable project lives in `gesture-detection/`. Application code is in the
`gesture_detection/` package: `app.py` owns the camera loop and worker lifecycle,
`pose_worker.py` and `yolo_worker.py` run inference, `rendering.py` draws OpenCV
overlays, `ipc.py` handles latest-value queues, and `config.py` centralizes model
paths and thresholds. `main.py` is a lightweight entry point. Model assets
(`pose_landmarker_lite.task` and `yolov8n.pt`) sit beside `pyproject.toml`.
There is currently no test directory; add tests under `gesture-detection/tests/`
and mirror package module names where practical.

## Build, Test, and Development Commands

Run commands from `gesture-detection/`:

```bash
uv sync                         # Create/update the environment from uv.lock
uv run gesture-detection        # Start the camera-based application
uv run python -m gesture_detection.app  # Equivalent module entry point
uv run python -m compileall gesture_detection  # Basic syntax check
```

Python 3.12 or newer is required by `pyproject.toml`. The application needs a
working camera and displays an OpenCV window; press `Esc` to exit. Keep
`uv.lock` synchronized whenever dependencies change.

## Coding Style & Naming Conventions

Follow standard Python conventions: four-space indentation, `snake_case` for
functions and modules, `PascalCase` for classes, and `UPPER_SNAKE_CASE` for
configuration constants. Prefer small, responsibility-focused modules and keep
tunable thresholds in `config.py`. Use relative imports within the package and
type hints for new or substantially changed interfaces. No formatter or linter
is configured, so keep edits PEP 8-compatible and consistent with nearby code.

## Testing Guidelines

No automated test framework or coverage threshold is configured yet. For logic
changes, add focused `pytest` tests named `tests/test_<module>.py`; keep camera,
model, and multiprocessing dependencies mocked so tests remain deterministic.
Before submitting, run the syntax check above and manually exercise affected
camera behavior. If adding pytest, declare it as a development dependency and
document `uv run pytest` in the README.

## Commit & Pull Request Guidelines

Recent history favors short, imperative subjects with Conventional Commit-style
prefixes such as `feat:` and `fix:`. Keep each commit scoped to one concern.
Pull requests should explain the behavior change, list verification steps, and
link relevant issues. Include a screenshot or short recording for changes to
rendered overlays or gesture feedback, and call out new model files, dependency
changes, or hardware assumptions.
