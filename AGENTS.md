# Repository Guidelines

## Project Structure & Module Organization

This is a monorepo. Each Python project is managed separately with uv; run
`uv sync` in a project before importing its package, and do not import `src`
as a package.

- `gesture_detection/` (Python 3.12+): camera-based gesture recognition. The
  package is `src/gesture_detection/`: `app.py` / `multicam_app.py` own the
  camera loops and worker lifecycle, `pose_worker.py` runs MediaPipe inference,
  `recognition.py` and the per-gesture modules hold recognition state,
  `rendering.py` draws OpenCV overlays, `ipc.py` handles latest-value queues,
  and `config.py` centralizes paths and thresholds. `recognition_types.py`
  defines `GestureSample`, the value sent to `unity_bridge`. Tests live under
  `tests/` and mirror module names where practical; evaluation tools are in
  `scripts/`.
- `unity_bridge/` (Python 3.14+): WebSocket server for Unity. The package is
  `src/unity_bridge/` with tests in `test/`.
- `mcu/` (Python 3.12+): serial client library for the firmware (`mcu/cli.py`
  is a debugging CLI).
- `firmware/`: Raspberry Pi Pico fan-control firmware (TinyGo). See
  `firmware/README.md`.
- `proto/`: protobuf schemas and the buf template. `buf.gen.yaml` generates
  `comms` (firmware Go, mcu Python) and `gesture` (unity_bridge Python, Unity
  C#); each plugin selects its package with `types`.
- `suzukaze/`: Unity project (6000.5.8f1). Code that talks to `unity_bridge`
  lives in `Assets/Bridge/` (`Generated/` for buf output, `Gesture/` for the
  gesture receiver).

## Project Architecture

- Input: `gesture_detection` via the cameras (two with `MULTICAM_ENABLED=true`).
  `unity_bridge --gesture` starts it
  as a child process and receives `GestureSample` values over a
  `multiprocessing.Queue`.
- Control: Unity manages the whole experience. It connects to `unity_bridge`
  over WebSocket (`ws://127.0.0.1:5000`), receives gesture state/events as
  protobuf, and returns ACKs. Delivery state (retries, expiry, ACKs) is owned by
  `unity_bridge`'s `DeliveryOutbox`.
- Output: Unity footage is output directly via the projector. The fan and
  speaker are driven by the microcontroller; `unity_bridge` is planned to call
  the `mcu` library in-process, which talks to `firmware/` over USB serial
  using framed `comms` protobuf.

## Build, Test, and Development Commands

Generated protobuf code is not committed. After cloning or changing a schema,
run from `proto/` (requires the buf CLI):

```bash
buf generate
```

From `gesture_detection/`:

```bash
uv sync --group dev
uv run gesture-detection        # Recognition only (does not send to Unity)
uv run python -m pytest
```

From `unity_bridge/`:

```bash
uv sync --group dev
uv run unity-bridge --gesture   # Start recognition and serve Unity
uv run unity-gesture-probe      # Mock Unity receiver
uv run python -m pytest
```

The applications need working cameras and display an OpenCV window; press
`Esc` to exit. Keep each `uv.lock` synchronized whenever dependencies change.
See `firmware/README.md` for TinyGo build and flashing commands.

## Coding Style & Naming Conventions

Follow standard Python conventions: four-space indentation, `snake_case` for
functions and modules, `PascalCase` for classes, and `UPPER_SNAKE_CASE` for
configuration constants. Prefer small, responsibility-focused modules and keep
tunable thresholds in `config.py`. Use relative imports within the package and
type hints for new or substantially changed interfaces. Each Python project
configures Ruff and Pyright; run `uv run ruff format`, `uv run ruff check`, and
`uv run pyright` before submitting. Generated code is excluded from both.

## Testing Guidelines

Each Python project uses pytest (`uv run python -m pytest`). On pull requests,
CI runs Ruff, Pyright, and pytest for `gesture_detection` and `unity_bridge`. For logic changes, add focused tests named
`test_<module>.py`; keep camera, model, and hardware dependencies mocked so
tests remain deterministic. `unity_bridge`'s integration tests start a real
child process with a fake recognition target. Unity tests run in the Unity Test
Runner (`Assets/Bridge/Gesture/Tests/`). Manually exercise affected camera
behavior before submitting.

## Commit & Pull Request Guidelines

Be sure to create a branch from the “main” branch before working on it. Commit messages can be in either Japanese or English, but it is important that the content be clear.
Recent history favors short, imperative subjects with Conventional Commit-style
prefixes such as `feat:` and `fix:`. Keep each commit scoped to one concern.
Create a branch or a worktree for each feature or bugfix.
Pull requests should explain the behavior change, list verification steps, and
link relevant issues. Include a screenshot or short recording for changes to
rendered overlays or gesture feedback, and call out new model files, dependency
changes, or hardware assumptions.
