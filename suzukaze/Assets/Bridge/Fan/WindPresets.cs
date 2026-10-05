using System;
using UnityEngine;

namespace Suzukaze.Fan
{
    public enum WindPreset
    {
        [InspectorName("強風")] Strong,
        [InspectorName("扇ぎ")] Fanning,
        [InspectorName("そよ風")] Breeze,
        [InspectorName("揺らぎ")] Yuragi,
    }

    // Wind power (0-1) of each preset over time. The same time and seed give
    // the same power, so a run is reproducible; a new seed gives a new run.
    public static class WindPresets
    {
        // Equal-amplitude octaves add up to a 1/f spectrum.
        private static readonly float[] YuragiFrequencies = { 0.03f, 0.06f, 0.12f, 0.25f, 0.5f, 1f };

        public static Vector2 PowerRange(WindPreset preset) => preset switch
        {
            WindPreset.Strong => new Vector2(0.8f, 1f),
            WindPreset.Fanning => new Vector2(0.5f, 0.7f),
            WindPreset.Breeze => new Vector2(0.3f, 0.4f),
            WindPreset.Yuragi => new Vector2(0.2f, 0.6f),
            _ => throw new ArgumentOutOfRangeException(nameof(preset)),
        };

        public static float Power(WindPreset preset, float time, float seed)
        {
            Vector2 range = PowerRange(preset);
            float level = preset switch
            {
                WindPreset.Strong => Strong(time, seed),
                WindPreset.Fanning => Fanning(time, seed),
                WindPreset.Breeze => Breeze(time, seed),
                WindPreset.Yuragi => Yuragi(time, seed),
                _ => throw new ArgumentOutOfRangeException(nameof(preset)),
            };
            return Mathf.Lerp(range.x, range.y, Mathf.Clamp01(level));
        }

        // Slow swells with sharper gusts on top.
        private static float Strong(float time, float seed) =>
            0.6f * Noise(time * 0.2f, seed) + 0.4f * Noise(time * 1.2f, seed + 10f);

        // A hand-held fan: each stroke sends a quick puff that dies away while
        // the hand swings back, then a short lull before the next one.
        private const float FanningStrokeSeconds = 0.9f;
        private const float FanningAttack = 0.12f; // Share of a stroke spent pushing the air.
        private const float FanningDecay = 0.15f;  // How fast the puff dies away, in strokes.

        private static float Fanning(float time, float seed)
        {
            // The rhythm drifts like a person's; the phase still always moves forward.
            float phase = time / FanningStrokeSeconds + 0.4f * Noise(time * 0.3f, seed);
            int stroke = Mathf.FloorToInt(phase);
            float t = phase - stroke;
            float puff = t < FanningAttack
                ? Mathf.SmoothStep(0f, 1f, t / FanningAttack)
                : Mathf.Exp(-(t - FanningAttack) / FanningDecay);
            // Every stroke is a little different, and the arm tires and recovers slowly.
            float strength = Mathf.Lerp(0.7f, 1f, Hash(stroke, seed)) * Mathf.Lerp(0.85f, 1f, Noise(time * 0.1f, seed + 10f));
            return puff * strength;
        }

        // A repeatable pseudo-random value in 0-1 for each stroke.
        private static float Hash(int index, float seed)
        {
            float x = Mathf.Sin(index * 12.9898f + seed * 78.233f) * 43758.5453f;
            return x - Mathf.Floor(x);
        }

        // Smooth, unhurried changes.
        private static float Breeze(float time, float seed) =>
            0.7f * Noise(time * 0.1f, seed) + 0.3f * Noise(time * 0.4f, seed + 10f);

        // 1/f fluctuation: partly predictable, partly not.
        private static float Yuragi(float time, float seed)
        {
            float sum = 0f;
            for (int i = 0; i < YuragiFrequencies.Length; i++)
                sum += Noise(time * YuragiFrequencies[i], seed + 10f * i) - 0.5f;
            // Averaging octaves narrows the spread; widen it back toward 0-1.
            return 0.5f + 2.5f * sum / YuragiFrequencies.Length;
        }

        private static float Noise(float x, float row) => Mathf.Clamp01(Mathf.PerlinNoise(x, row));
    }
}
