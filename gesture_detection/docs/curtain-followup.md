# Behind-screen pose follow-up (2026-09-19)

This follow-up uses the four existing `*btn.mp4` clips. The user confirmed that
`ラムネbtn.mp4` performs the current gesture specification, although it may not be an
ideal execution. This is distinct from the older `kohara_ramune_01` clip used
by the IMAGE/VIDEO comparison.

## MediaPipe experiments

The evaluator now supports configurable detection, presence, and tracking
confidence, clip selection, fixed foreground masking, 50% area downsampling,
and luminance CLAHE. The Uchimizu expected interval excludes the interruption
from 16 to 23 seconds; the other clips use their full duration.

| Full-model condition | Fanning pose | Relaxing pose / important | Uchimizu expected / other-action frames | Ramune action |
| --- | ---: | ---: | ---: | ---: |
| Baseline confidence 0.50 | 0.0% | 44.3% / 36.5% | 28/695 (4.0%) / 22 | 0 |
| Detection + presence 0.35 | 0.0% | 93.8% / 47.1% | 45/695 (6.5%) / 45 | 0 |
| Detection + presence 0.20 | 1.9% | 80.8% / 51.1% | 31/695 (4.5%) / 27 | 0 |
| 50% area downsample | 0.0% | 91.3% / 4.0% | 11/695 (1.6%) / 69 | 0 |
| Center mask + downsample | 0.3% | 89.5% / 0.0% | 1/695 (0.1%) / 31 | 0 |

CLAHE, downsample plus CLAHE, and the center mask without downsampling were
screened on Fanning; all produced zero pose frames. Confidence 0.35 improves
initial pose coverage on Relaxing and slightly improves Uchimizu output, but it
doubles other-action frames in the annotated Uchimizu intervals. None of these
conditions solves Fanning, Relaxing, or Ramune classification.

## YOLO Pose comparison

YOLOv8n-pose was evaluated at image size 640 and confidence 0.05. Low confidence
also detects many background people, so only detections covering at least 8%
of the image are counted as the foreground performer. This installation-specific
size constraint is essential; without it, background people make pose coverage
look much better than it is.

| Clip | Foreground pose | All important points > 0.5 | Mean point confidence | p95 point jump |
| --- | ---: | ---: | ---: | ---: |
| ラムネ | 100.0% | 85.1% | 0.846 | 0.066 |
| 夕涼み | 100.0% | 33.7% | 0.706 | 0.067 |
| 扇ぎ | 81.0% | 36.4% | 0.743 | 0.406 |
| 打ち水 | 90.7% | 36.1% | 0.716 | 0.167 |

The matching ordinary-camera controls all have 100% foreground pose coverage,
94.5--98.5% important-point coverage, and p95 jumps of 0.010--0.020. The screen
therefore causes substantial landmark loss and jitter even when YOLO finds the
foreground person. Raw results are in
[yolo-pose-curtain.json](yolo-pose-curtain.json) and
[yolo-pose-control.json](yolo-pose-control.json).

A prototype YOLO-foreground-crop to MediaPipe Full pipeline was also tested on
Fanning. YOLO supplied a foreground crop on 260/321 frames, but MediaPipe never
produced a frame with all important landmarks and emitted no action. Cropping
does not rescue the MediaPipe landmark stage on this clip.

## Current-spec Ramune diagnosis

MediaPipe Full sees the six required shoulder, wrist, and hip points on 306/309
frames. The raw preparation geometry is satisfied on only 16 frames, split
across 11 runs; the longest run is 0.068 seconds, below the required 0.25-second
dwell. The analyzer consequently spends 293 frames in `IDLE`, 16 in `FORMING`,
and none in `READY`.

The detected hand-gap median is 0.174 shoulder widths, below the configured
minimum 0.30, while the alignment median is 0.570 against a maximum of 0.60.
The clip is therefore a useful current-spec failure example: the model sees the
body, but detected hand geometry never remains inside the preparation window.
Do not relax the production thresholds from this single, possibly imperfect
execution; retain it for comparison with the new recordings.

## Decision

Follow-up: [the temporal experiment](pose-temporal.md) tested tracking,
short-gap interpolation, and smoothing. It did not solve Fanning or Uchimizu;
visual review found incorrect partial-body skeletons even after area filtering.
The recommendations below describe candidates before that experiment, not a
validated solution.

- Do not enable global blur, downsampling, CLAHE, or center masking.
- Keep MediaPipe confidence 0.50 in the application for now. The 0.35 setting
  improves coverage but has not demonstrated a net gesture-level improvement.
- Use YOLO Pose plus foreground-area filtering as the next offline prototype,
  with temporal identity tracking and short-gap keypoint smoothing before
  adapting the gesture rules to its 17-keypoint schema.
- Use Monday's recordings to determine whether that temporal pipeline is
  sufficiently stable. Preserve current-spec `ラムネbtn.mp4` as a hard case rather
  than treating it as obsolete data.

Run the MediaPipe matrix or selected conditions with:

```bash
uv run python -m scripts.evaluate_curtain --condition full_conf035
```

After obtaining `yolov8n-pose.pt`, run the foreground-pose comparison with:

```bash
uv run python -m scripts.evaluate_yolo_pose --confidence 0.05
```
