# IMAGE / VIDEO comparison (2026-09-17)

This exploratory run supports keeping IMAGE as the default while making VIDEO
available for evaluation. VIDEO was faster in these runs, but gesture outputs
changed substantially. The clips have no frame-level ground-truth annotations;
counts below are classifier outputs, not accuracy measurements. The user
confirmed that the Ramune clip predates the current gesture specification.
Its action counts must not be used to evaluate current Ramune recognition.

## Method

- Python 3.12.3, MediaPipe 0.10.35, OpenCV 5.0.0; configured FPS=30.
- Same local machine; MediaPipe reported XNNPACK CPU inference and llvmpipe OpenGL.
- Model: pose_landmarker_lite.task, SHA-256
  `59929e1d1ee95287735ddd833b19cf4ac46d29bc7afddbbf6753c459690d574a`.
- Three local sample_movies clips: kohara_fanning_01, kohara_ramune_01,
  kohara_uchimizu_01 (full filenames are in the JSON).
- Full clips, original decoded images, sequential processing, no GUI or encoding.
- One Python process; a fresh PoseAnalyzer for every clip/mode. IMAGE then VIDEO
  per clip, one run each, no randomized order or repeated timing trials.
- Read with OpenCV, timestamp with FrameClock(is_video=True), then call
  analyzer.process(frame, timestamp, frame_id) once for every decoded frame.
- Assert returned frame_id and timestamp match each input; all 6,238 calls matched.
- Time only process() with time.perf_counter(); initialization, decoding, and
  encoding are excluded from the table. Times include Python gesture analysis.
- Count selected_action and non-empty landmarks. Record source-time transitions.
  These are not necessarily the UI fallback RELAXING labels.

## Observations

| Clip | Mode | Frames / with pose | Processing seconds | FANNING | UCHIMIZU | RAMUNE |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| kohara_fanning_01 | IMAGE | 1495 / 1479 | 137.636 | 490 | 0 | 0 |
| kohara_fanning_01 | VIDEO | 1495 / 1495 | 117.375 | 196 | 0 | 0 |
| kohara_ramune_01 | IMAGE | 924 / 924 | 187.496 | 39 | 144 | 0 |
| kohara_ramune_01 | VIDEO | 924 / 924 | 42.103 | 59 | 80 | 0 |
| kohara_uchimizu_01 | IMAGE | 700 / 700 | 48.630 | 0 | 79 | 0 |
| kohara_uchimizu_01 | VIDEO | 700 / 700 | 30.255 | 3 | 33 | 0 |

All other frames had selected_action=NONE.

- Fanning: first FANNING onset was 3.930 s in both modes, but classified duration
  differed (490 versus 196 frames). More frames with a pose did not imply more
  frames classified as fanning.
- Ramune: the input follows an obsolete gesture specification. Neither mode
  produced RAMUNE, but this does not indicate a failure against the current
  specification. Use this clip only for runtime/pipeline checks; current-spec
  footage is required before comparing Ramune recognition.
- Uchimizu: IMAGE produced six UCHIMIZU intervals, VIDEO three. VIDEO also
  produced three FANNING frames. No claim about correctness is made without labels.
- Timing is a single-machine, single-pass observation. Ordering, warm caches,
  and machine load were not controlled sufficiently to claim a general speedup.

## Compatibility and next decision

The native runs accepted increasing millisecond timestamps without errors and
preserved every input ID and original timestamp. They bypassed the application
GUI/IPC; sequential IPC and matching-result validation are covered separately
by unit tests. Camera behavior was not manually exercised.

Both modes retain application gesture histories. Only MediaPipe receives
millisecond timestamps; those may advance by 1 ms to resolve quantization
collisions. Gesture clocks and result metadata keep original source seconds.
Missing-pose resets do not rewind MediaPipe time. Camera dropping and overlay
lag remain properties of the existing latest-frame pipeline.

Keep IMAGE as the baseline. Before promoting VIDEO, label action intervals,
compare false positives/misses and onset/offset at identical frame IDs, and
inspect landmark trajectories around divergent intervals. Recalibration may be
needed; improved runtime alone is insufficient. Obtain current-spec Ramune
footage before evaluating that gesture.

Raw counts, timings, and transitions: [pose-mode-comparison.json](pose-mode-comparison.json).
The [README](../README.md#comparing-mediapipe-image-and-video-modes) provides
configuration and application-level A/B commands.
