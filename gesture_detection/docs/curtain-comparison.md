# Curtain pose comparison (2026-09-18)

Issue #26 proposed three conditions for footage recorded through the curtain:
Lite without preprocessing, Full without preprocessing, and Lite with a weak
blur. This run compares those conditions on the four local `*btn.mp4` clips.

## Result

Full is the best of the tested conditions for the Uchimizu clip, but none of
the three conditions recognizes all four gestures. A weak blur helps initial
pose detection substantially; it does not reliably improve the important
landmarks or the final gesture classification.

| Clip / expected action | Condition | Pose frames | Important landmarks visible | Expected action frames | Other action frames |
| --- | --- | ---: | ---: | ---: | --- |
| ラムネ / RAMUNE | Lite | 309/309 (100.0%) | 91.9% | 0 | FANNING 63, SPRINKLING 58 |
| | Full | 309/309 (100.0%) | 99.0% | 0 | FANNING 47 |
| | Lite + blur | 309/309 (100.0%) | 99.0% | 0 | FANNING 74, SPRINKLING 55 |
| 夕涼み / RELAXING | Lite | 168/323 (52.0%) | 0.0% | 0 | none |
| | Full | 143/323 (44.3%) | 36.5% | 0 | SPRINKLING 1 |
| | Lite + blur | 294/323 (91.0%) | 3.7% | 0 | none |
| 扇ぎ / FANNING | Lite | 0/321 (0.0%) | 0.0% | 0 | none |
| | Full | 0/321 (0.0%) | 0.0% | 0 | none |
| | Lite + blur | 4/321 (1.2%) | 0.0% | 0 | none |
| 打ち水 / SPRINKLING | Lite | 469/905 (51.8%) | 7.8% | 11 (1.2%) | FANNING 151 |
| | Full | 555/905 (61.3%) | 38.0% | 61 (6.7%) | FANNING 32 |
| | Lite + blur | 879/905 (97.1%) | 13.7% | 21 (2.3%) | FANNING 196 |

"Important landmarks visible" means that the nose, both shoulders, both
wrists, and both hips all have MediaPipe visibility above 0.5. Its denominator
is every decoded frame, including frames with no pose.

### Interpretation

- Full produces the strongest Uchimizu result: 61 expected-action frames versus
  11 for Lite, while reducing FANNING false positives from 151 to 32. Its
  important-landmark rate also rises from 7.8% to 38.0%.
- The weak Gaussian blur raises pose coverage from 50.9% to 80.0% over all four
  clips. On the Uchimizu clip it reaches 97.1%. However, important-landmark
  coverage rises only from 19.1% to 23.8% overall, and the Uchimizu clip produces
  more FANNING false positives than unprocessed Lite. Suppressing the mesh can
  help MediaPipe find a person without locating the wrists, shoulders, and hips
  accurately enough for the current rules.
- The Fanning clip is an initial-detection failure under every condition. A
  different model threshold, crop/contrast treatment, or detector is needed;
  switching from Lite to Full after detection cannot solve this case.
- The Ramune clip is not an initial-detection failure. All conditions find a
  pose in every frame, and Full has all important landmarks visible in 99.0% of
  frames, but no RAMUNE is emitted. This points to landmark geometry or the
  gesture rules rather than person detection. Full does remove the spurious
  SPRINKLING output seen with Lite.
- Relaxing never activates. Its whole-body stillness rule uses more landmarks
  than the seven-point visibility summary, so even Full's partial improvement
  is insufficient. Blur greatly increases pose presence but not complete,
  stable landmark availability.

## Method

- Python 3.12.3, MediaPipe 0.10.35, OpenCV 5.0.0; MediaPipe VIDEO mode.
- Lite SHA-256:
  `59929e1d1ee95287735ddd833b19cf4ac46d29bc7afddbbf6753c459690d574a`.
- Full SHA-256:
  `5134a3aad27a58b93da0088d431f366da362b44e3ccfbe3462b3827a839011b1`.
- Weak blur: OpenCV Gaussian blur, 5x5 kernel, sigma 1.2.
- Full clips at their original 1920x1080 resolution, decoded sequentially. A
  fresh `PoseAnalyzer` is created for every clip and condition.
- The application classifier processes every frame using its source timestamp.
  The evaluator checks that each result retains the input frame ID and timestamp.
- Clip-level expected actions come from the filenames. The evaluated UI action
  maps internal `UCHIMIZU` to `SPRINKLING` and uses `RELAXING` as the fallback.

Run the comparison from `gesture_detection/` after placing both model files and
the ignored sample clips in their default locations:

```bash
uv run python -m scripts.evaluate_curtain
```

Raw counts, transition times, visibility values, model hashes, and single-pass
timings are in [curtain-comparison.json](curtain-comparison.json). Timings are
recorded for reproducibility but were not controlled or repeated as a benchmark.

## Limitations and next experiment

The videos do not have frame-level start/end annotations. Therefore an
expected-action frame ratio is not a conventional accuracy, recall, or F1 score:
preparation and recovery frames are included in its denominator. The zero
results and comparisons on identical clips are still diagnostic, but reporting
true accuracy requires manually labelled action intervals.

The next useful experiment is to label intervals first, then focus on two
separate failure modes:

1. For Fanning, tune pose detection/presence confidence and compare contrast or
   downscaled stronger blur, because the current failure occurs before gesture
   classification.
2. For Uchimizu and Ramune, keep Full and inspect wrist/shoulder/hip trajectories
   against visible hand positions. Full already improves the required points;
   threshold calibration should be based on those labelled trajectories.

The tested 5x5 blur should not be enabled in the application globally: its
higher pose coverage comes with more Fanning false positives and no successful
Ramune, Relaxing, or Fanning recognition.

The confidence, preprocessing, foreground-pose, and current-spec Ramune
follow-up is recorded in [curtain-followup.md](curtain-followup.md).
