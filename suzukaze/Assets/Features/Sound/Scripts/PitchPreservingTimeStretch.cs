using System;
using UnityEngine;

namespace Features.Sound.Scripts
{
    // WSOLA: align short waveform segments, then crossfade them without resampling.
    public static class PitchPreservingTimeStretch
    {
        public static AudioClip CreateClip(AudioClip original, float speed)
        {
            var input = new float[original.samples * original.channels];
            if (!original.GetData(input, 0))
            {
                Debug.LogWarning($"[Sound] Cannot time-stretch {original.name}; use a readable, decompressed clip.", original);
                return original;
            }
            var samples = Stretch(input, original.channels, original.frequency, speed);
            var clip = AudioClip.Create($"{original.name}_Speed_{speed:F2}", samples.Length / original.channels,
                original.channels, original.frequency, false);
            clip.SetData(samples, 0);
            return clip;
        }

        public static float[] Stretch(float[] input, int channels, int sampleRate, float speed)
        {
            if (input == null) throw new ArgumentNullException(nameof(input));
            if (channels <= 0 || input.Length % channels != 0) throw new ArgumentOutOfRangeException(nameof(channels));
            if (sampleRate <= 0) throw new ArgumentOutOfRangeException(nameof(sampleRate));
            if (float.IsNaN(speed) || float.IsInfinity(speed) || speed <= 0f)
                throw new ArgumentOutOfRangeException(nameof(speed));
            if (input.Length == 0 || Mathf.Approximately(speed, 1f)) return (float[])input.Clone();

            int frames = input.Length / channels;
            int outputFrames = Mathf.Max(1, Mathf.RoundToInt(frames / speed));
            var output = new float[outputFrames * channels];
            int hop = Mathf.Max(16, Mathf.RoundToInt(sampleRate * 0.01f));
            int window = hop * 2;
            int radius = Mathf.Max(4, Mathf.RoundToInt(sampleRate * 0.0025f));
            // Preserve the attack instead of repeating or smearing the initial impact.
            Array.Copy(input, output, Mathf.Min(input.Length, Mathf.Min(output.Length, window * channels)));
            for (int position = hop; position < outputFrames; position += hop)
            {
                int expected = Mathf.Clamp(Mathf.RoundToInt(position * speed), 0, Mathf.Max(0, frames - window));
                int overlap = Mathf.Min(hop, outputFrames - position);
                int start = Mathf.Max(0, expected - radius);
                int end = Mathf.Min(Mathf.Max(0, frames - window), expected + radius);
                int best = expected;
                double bestScore = double.NegativeInfinity;
                // Search all channels together so stereo images keep their phase relationship.
                for (int candidate = start; candidate <= end; candidate++)
                {
                    double dot = 0, sourceEnergy = 0, targetEnergy = 0;
                    for (int n = 0; n < overlap; n += 4)
                    {
                        if (candidate + n >= frames) break;
                        for (int channel = 0; channel < channels; channel++)
                        {
                            float a = input[(candidate + n) * channels + channel];
                            float b = output[(position + n) * channels + channel];
                            dot += a * b; sourceEnergy += a * a; targetEnergy += b * b;
                        }
                    }
                    double score = dot / Math.Sqrt(sourceEnergy * targetEnergy + 1e-20)
                        - Math.Abs(candidate - expected) * 1e-7;
                    if (score > bestScore) { bestScore = score; best = candidate; }
                }
                for (int n = 0; n < window && position + n < outputFrames; n++)
                {
                    float weight = n < hop ? (float)n / hop : 1f;
                    for (int channel = 0; channel < channels; channel++)
                    {
                        int destination = (position + n) * channels + channel;
                        float value = best + n < frames ? input[(best + n) * channels + channel] : 0f;
                        output[destination] = output[destination] * (1f - weight) + value * weight;
                    }
                }
            }
            // End cleanly when the final aligned segment extends beyond the original tail.
            int fade = Mathf.Min(hop, outputFrames);
            for (int n = 0; n < fade; n++)
                for (int channel = 0; channel < channels; channel++)
                    output[(outputFrames - fade + n) * channels + channel] *= 1f - (float)n / fade;
            return output;
        }
    }
}
