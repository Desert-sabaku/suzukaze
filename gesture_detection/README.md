# Gesture Detection

OpenCV camera or video-file input is processed by a MediaPipe Pose worker.
It classifies fanning, sprinkling water, relaxing, and a two-hand Ramune opening
motion. No bottle or other prop is required; the application does not start YOLO.

## Ramune gesture

1. Make a ring representing the bottle mouth with either hand, in front of your torso.
2. Place the other hand above it and hold briefly (0.25 seconds).
3. Keep the lower hand still and press the upper hand down toward it within 1.5 seconds.
4. The opening feedback stays visible for 0.8 seconds. Lift the upper hand and
   prepare again to perform another opening.

The bottom panel guides preparation, pressing, success, and retry. Text is in
English to work with the existing OpenCV font. Finger shape is an instruction,
not a recognition requirement: recognition uses wrist positions and their order
of movement. Either hand can play either role. Both hands moving down together,
sideways motions, or contact without preparation do not count. Tracking loss
cancels preparation. Ramune preparation takes priority over the single-hand
classifiers to prevent a press being interpreted as sprinkling water.

Keep both wrists, shoulders, and hips visible, facing the camera. Distances are
relative to shoulder width in normalized image coordinates; thresholds in
`modules/config.py` are initial values and need calibration with real footage,
including different camera aspect ratios and users.

### Manual verification

Run the camera app and try both hand assignments, repeat an opening after
lifting the upper hand, then try moving both hands down and bringing them
together without preparation. Check that only the intended sequence opens
Ramune, and that fanning/sprinkling still work outside the Ramune posture.
A synthetic overlay example is in [docs/ramune-guide.png](docs/ramune-guide.png);
it demonstrates the UI, not camera recognition accuracy.

## Run

The project uses Python 3.12+ and `uv`:

```bash
uv sync
cp .env.example .env
uv run gesture-detection
```

Alternatively, you can run the Python module directly:

```bash
uv run python -m modules.app
```

Press `Esc` in the camera window to exit.

## Input source

Copy `.env.example` to `.env` and adjust the local settings there. `.env` and
`.env.*` are ignored by Git, except for the tracked `.env.example` template.
Existing environment variables take precedence over `.env`. The file is loaded
from the project root, regardless of the working directory.

By default, the application uses camera `0`. To process a video file, set:

```dotenv
VIDEO_SOURCE="sample_movies/sample.mp4"
```

Leave `VIDEO_SOURCE` empty to use the camera. The application exits when the
video reaches its end. Annotated output is saved to `VIDEO_OUTPUT_PATH`, or to
`<OUTPUT_DIR>/<source filename><YYYY-MM-DD>.output.mp4` when that setting is empty.
`OUTPUT_DIR` defaults to `output`. Relative paths are resolved from the project
root; absolute paths and `~` are also supported. Output has no audio track.

The template also documents camera index/backend/FourCC, model paths, FPS, and
output buffer size. `CAMERA_BACKEND=0` selects OpenCV's automatic backend;
Linux V4L2 devices can use `200`. Gesture thresholds and model definitions remain
in `modules/config.py`.

The inference worker receives the latest frame through shared memory. Encoding runs
on a separate thread with a bounded buffer (`VIDEO_OUTPUT_BUFFER_FRAMES`, default
8). Every frame accepted for saving is written in order, including when exiting
with `Esc`; closing may wait for pending frames to finish. If encoding cannot
keep up and the buffer fills, playback waits rather than dropping output frames.
This reduces display-loop overhead but does not guarantee real-time playback.
At 1080×720, eight buffered BGR frames use about 18 MiB, excluding active frames.

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
- The retained `yolo_worker.py` module and YOLO dependency are unused by the application; no YOLO model is required to run it.

## Structure

- `modules/app.py`: input loop, worker lifecycle, action integration
- `modules/pose_worker.py`: MediaPipe inference and temporal gesture state
- `modules/ramune.py`: two-hand preparation and press state machine
- `modules/yolo_worker.py`: legacy bottle detection (unused)
- `modules/rendering.py`: OpenCV drawing helpers
- `modules/config.py`: model paths and thresholds
- `modules/ipc.py`: latest-value queue operations

## CI

On pull requests, GitHub Actions runs:

- Ruff (`format --check` + `check`)
- Pyright (type checking)
- Pytest (tests + coverage report)
