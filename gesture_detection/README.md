# Gesture Detection

OpenCV camera or video-file input is processed by a MediaPipe Pose worker.
It classifies fanning, sprinkling water, relaxing, and a two-hand Ramune opening
motion. No bottle or other prop is required; the application does not start YOLO.

## Relaxing (whole-body stillness)

Relaxing requires one continuous second of stillness in source time. It monitors
the nose, shoulders, elbows, wrists, hips, knees, ankles, heels, and toes when
they are visible inside the image. Both shoulders and hips must be tracked.
A change in which major parts can be tracked restarts the stillness period;
unobserved body parts are not assumed still.

The largest movement of any monitored part is used, rather than an average that
can hide a moving hip or foot among stationary points. Positions remain in image
coordinates, so whole-body translation, leaning, and approaching the camera are
not cancelled out by recentering the body. Horizontal distances account for the
image aspect ratio; distances are normalized by shoulder-to-hip length.

The current frame turns Relaxing off immediately if speed exceeds 0.30 torso
lengths/second or displacement from the fixed stillness reference exceeds 0.05
torso lengths. The fixed reference also prevents sustained slow movement from
being treated as stationary solely because each frame-to-frame change is small.
No moving average or release hold delays the exit. Re-entry requires a fresh
second of stillness. Small landmark jitter within the tolerances is allowed;
motion below both thresholds is indistinguishable from tracking noise.

Missing torso tracking, changed visibility, non-increasing timestamps, and gaps
over 0.25 source seconds cancel the state. Feet outside the camera image cannot
be assessed: for such recordings the guarantee covers the tracked torso and
visible body parts, not the entire unseen body. Camera movement is also image
motion and can cancel Relaxing. Camera display lag still depends on the existing
latest-frame pipeline; “immediate” means the first processed frame that detects
motion, not zero camera-to-display latency.

Tune `RELAXING_*` in `modules/config.py`. CI uses synthetic landmarks and mocked
inference to check whole-body movement, individual limb movement, immediate exit,
slow drift, visibility loss, source timing, and small tracking jitter.

A full replay with identical VIDEO-mode landmarks supplied to the old and new
classifiers gave these Relaxing-state counts (not frame-level accuracy scores):

| Recording | Frames | Before | After |
| --- | ---: | ---: | ---: |
| sabaku_other_01.mp4 | 821 | 794 | 0 |
| kohara_relaxing_01 | 365 | 353 | 201 |

The speed/drift tolerances were relaxed from 0.20/0.035 to 0.30/0.05 after
manual feedback. Replaying the same cached landmarks increased the static
reference from 132 to 201 Relaxing frames while sabaku_other_01 stayed at zero.
The one-second dwell and immediate threshold-crossing release are unchanged.
The static reference still enters Relaxing, but the stricter rules also reduce
its active duration. Thresholds may need calibration for other cameras and
tracking noise. [The before/after overlay at 5.024 seconds](docs/relaxing-motion-release.jpg)
shows movement in sabaku_other_01 no longer labelled Relaxing.
This was an offline video replay; live-camera behavior has not been manually tested.

## Sprinkling water (Uchimizu)

Start with either wrist low in front of your torso, lift it to scoop, then
lower it to release the water. The wrist may move sideways during the release;
horizontal movement is optional because the camera does not measure depth.
Keep your face, shoulders, hips, and the moving wrist visible.

The detector remembers an upward movement of at least 0.10 torso heights
within 1.2 seconds, starting below 0.55 torso heights from the shoulders.
Lower the wrist at least 0.15 torso heights from its highest point and finish
at or below the torso midpoint (0.50 torso heights from the shoulders).
The release window is 1.5 seconds and restarts when the wrist reaches a new
highest point during preparation. Preparation must stay away from the face
and within the torso's horizontal span plus 0.25 shoulder widths on either side. A brief pause at the top is allowed. Raising alone or lowering without
preparation does not count. Tracking loss or an expired preparation cancels
the sequence. These are initial thresholds, not measured accuracy guarantees.

Successful feedback lasts 0.35 seconds. A new scoop is required after a
0.6-second cooldown measured from success. Distances use shoulder-to-hip
height and timing uses elapsed seconds rather than frame counts. Tune the
`UCHIMIZU_*` constants in `modules/config.py` using real footage.

Manual verification: try both hands, a brief pause before release, and a
sideways release. Then try face/chest-level fanning, raising only, lowering
only, and losing tracking during preparation. Check that sprinkling finishes
without switching to fanning, and that deliberate fanning afterward still
works. Automated tests use synthetic landmarks; camera accuracy needs a
separate manual check.

## Fanning near the torso midpoint

Fanning allows a brief excursion below the torso midpoint for up to 0.35
seconds. Lowering the wrist beyond 0.75 torso heights clears the posture
immediately; keeping it below the midpoint longer than the grace period also
clears it. During sprinkling preparation (READY), fanning scores alone cannot
select FANNING. After release, the same protection lasts one second from success,
letting the scoop/release leave the FFT window. A transient score from the other
hand cannot interrupt this sequence either. This does not extend the sprinkling feedback. Three substantial direction reversals
in the last second, together with a sufficient fanning score and valid posture,
can override this protection and take priority over sprinkling.
This lets sustained fanning settle into Fanning even when its first cycle
resembles a scoop. A single scoop/release does not establish this priority.
Outside preparation and the post-release grace period, normal fanning sensitivity
is unchanged. The grace period uses source time, not processing time, and is
configured by `FANNING_UCHIMIZU_GRACE_SECONDS` in `modules/config.py`.
The other relevant tolerances are `FANNING_*` constants there.

Manual verification: fan continuously around the torso midpoint, then lower
and hold the hand still. Check that fanning remains stable during the repeated
motion and clears after lowering. Also check that a single scoop still detects
sprinkling. The first cycle can remain ambiguous; real footage is needed to
calibrate these heuristic boundaries.

A before/after replay using identical VIDEO-mode landmarks for every decoded
frame produced the following counts (not accuracy scores):

| Recording | Frames | FANNING before → after | UCHIMIZU before → after |
| --- | ---: | ---: | ---: |
| kohara_uchimizu_01 | 700 | 3 → 0 | 33 → 33 |
| kohara_fanning_01 | 1495 | 196 → 141 | 0 → 0 |

The stricter priority also suppresses some fanning feedback near ambiguous
preparation/recovery motions. It does not guarantee zero interference on other
recordings. Compare [this frame at 3.563 seconds](docs/uchimizu-fanning-priority.jpg):
READY is preserved and the FANNING overlay is removed. The existing RELAXING
fallback can still be displayed when no primary action is selected.
Camera behavior has not been manually tested for this change.

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

Landmark drift between palm and wrist is allowed: horizontal hand separation
can reach 0.60 shoulder widths, and the lower hand may drift 0.50 shoulder
widths horizontally or 0.30 vertically from its initial position. The hands
need only come within 0.30 shoulder widths vertically at the end. To avoid
counting both hands moving down together, the upper hand must descend at least
0.25 shoulder widths and reduce the vertical gap by at least the same amount
from the end of preparation. These are initial tolerances, not measured accuracy
guarantees.

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

MediaPipe and its graphics backend normally print diagnostics directly to
stderr. The application suppresses those messages around model initialization
and inference. Set
`SUPPRESS_MEDIAPIPE_STARTUP_LOGS=false` in `.env` to expose them while debugging.

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

Gesture timing uses decoded video positions in seconds (`CAP_PROP_POS_MSEC`).
Frequency estimates, preparation holds, and cooldowns therefore use source time
regardless of processing speed. Invalid or non-increasing positions advance by
one frame at the source FPS (configured `FPS` if source FPS is invalid).
Camera input uses monotonic time recorded immediately after capture. Each frame
and its timestamp travel together through shared memory to all gesture detectors.
Input samples also carry a zero-based `frame_id`, incremented for every
successfully read frame, including camera frames skipped by inference.
Every pose result echoes the input `frame_id` and `timestamp`, even when no
person is detected. Pixels and metadata are copied under the same mailbox lock.
Video evaluation checks both fields before drawing or saving a result.
Camera overlays still use the latest available result; its metadata identifies
the older source frame rather than claiming it belongs to the displayed image.
Timestamps are source seconds for videos and monotonic capture seconds for
cameras, not wall-clock dates or inference completion times.

Video files are evaluated sequentially: each decoded frame waits for inference,
then its own result is drawn and saved before the next frame is read. Only one
frame is in flight, so the shared mailbox cannot overwrite pending video frames.
Processing is not paced to playback speed; gesture timing still uses source time.
The final frame is inferred and saved before normal end-of-file shutdown.
Pressing `Esc` during inference cancels evaluation; the pending frame is not saved.
Worker failure stops evaluation with an error rather than saving stale results.

Camera input retains the latest-frame policy and may skip intermediate frames.
Encoding runs
on a separate thread with a bounded buffer (`VIDEO_OUTPUT_BUFFER_FRAMES`, default
8). Every frame accepted for saving is written in order, including when exiting
with `Esc`; closing may wait for pending frames to finish. If encoding cannot
keep up and the buffer fills, playback waits rather than dropping output frames.
This reduces display-loop overhead but does not guarantee real-time playback.
At 1080×720, eight buffered BGR frames use about 18 MiB, excluding active frames.

## Comparing MediaPipe IMAGE and VIDEO modes

Set `POSE_RUNNING_MODE=VIDEO` (default) or `POSE_RUNNING_MODE=IMAGE` in
`.env`. IMAGE uses `detect(image)` independently for each frame.
VIDEO creates the landmarker with `RunningMode.VIDEO` and calls
`detect_for_video(image, timestamp_ms)`. Both calls are synchronous.
According to the [MediaPipe guide](https://ai.google.dev/edge/mediapipe/solutions/vision/pose_landmarker/python),
VIDEO uses tracking to reduce repeated detection work. This may improve
throughput but can change landmark trajectories and gesture decisions;
it is not an accuracy guarantee.

For an A/B comparison, run the same video in two fresh application processes
with separate output paths:

```bash
POSE_RUNNING_MODE=IMAGE VIDEO_SOURCE=sample_movies/sample.mp4 VIDEO_OUTPUT_PATH=output/image.mp4 uv run gesture-detection
POSE_RUNNING_MODE=VIDEO VIDEO_SOURCE=sample_movies/sample.mp4 VIDEO_OUTPUT_PATH=output/video.mp4 uv run gesture-detection
```

An initial three-clip comparison is recorded in
[the evaluation notes](docs/pose-mode-comparison.md). The Ramune clip follows
an older specification and is used only for runtime/pipeline checks.

Keep the model, thresholds, FPS setting, input, and machine fixed. Compare
processing time separately from source video duration, and inspect recognition
onset/offset, missed actions, false positives, and recovery after tracking loss.
Use frame-level labels to measure accuracy; action frame counts alone do not
establish which mode is better. Both modes retain the application's wrist
histories and Ramune/Uchimizu state machines. Gesture score smoothing remains
frame-based; relaxing detection uses the source-time stillness rules above.

Compatibility with the input pipeline:

- File input still processes every frame in order and waits for its own result.
  VIDEO mode does not introduce asynchronous result callbacks or frame dropping.
- Camera input still uses the latest available frame; VIDEO tracks the frames
  actually delivered to the worker, using their capture times, including gaps.
  It does not remove camera overlay lag or recover skipped frames.
- MediaPipe receives source seconds converted to integer milliseconds. If two
  increasing source timestamps map to the same millisecond, only MediaPipe's
  timestamp advances to at least the previous value plus one. Gesture timers
  and returned `frame_id`/`timestamp` retain the original values.
- Repeated, backward, negative, or non-finite source timestamps are rejected in
  VIDEO mode. Normal input is already made increasing by the frame clock.
  Seeking/restarting a source requires a new analyzer; the app currently does
  neither within a run.
- Missing poses reset the application's gesture history as before, but do not
  rewind the MediaPipe clock. MediaPipe manages its own tracking/reacquisition.
- CI covers both modes using mocked image conversion and inference. Native
  model comparisons are separate manual checks, not CI requirements.

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
- `modules/relaxing.py`: source-time stillness and immediate motion release
- `modules/uchimizu.py`: scoop and downward-release sequence detection
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
