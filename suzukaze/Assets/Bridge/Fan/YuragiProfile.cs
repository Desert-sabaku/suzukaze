using System;
using UnityEngine;

namespace Suzukaze.Fan
{
    // A tunable 1/f-like fluctuation. Octaves of noise, each twice as fast as
    // the one before, are added up; roughness sets how much the faster ones
    // count. The same time and seed give the same power.
    [Serializable]
    public struct YuragiProfile
    {
        public const int MaxOctaves = 8;

        [Tooltip("強さの (最小, 最大)。0-1")]
        public Vector2 powerRange;

        [Tooltip("いちばん遅いうねりの周波数 (Hz)。大きいほど速く変わる")] [Min(0.001f)]
        public float baseFrequency;

        [Tooltip("重ねる層の数。層ごとに周波数が倍になる")] [Range(1, MaxOctaves)]
        public int octaves;

        [Tooltip("速い層の効き具合。1 で全層が同じ強さ (1/f)、小さいほど滑らか")] [Range(0f, 1f)]
        public float roughness;

        [Tooltip("揺らぎの深さ。1 では範囲の中ほどに集まり、大きいほど範囲の端まで振れる (端では頭打ちになる)")]
        [Range(0.5f, 4f)]
        public float depth;

        public YuragiProfile(Vector2 powerRange, float baseFrequency, int octaves, float roughness, float depth)
        {
            this.powerRange = powerRange;
            this.baseFrequency = baseFrequency;
            this.octaves = octaves;
            this.roughness = roughness;
            this.depth = depth;
        }

        // Slow, smooth swells, like wind across a landscape.
        public static YuragiProfile Natural => new(new Vector2(0.35f, 0.65f), 0.15f, 4, 0.6f, 2.2f);

        // Quicker and rougher, down to about the pace of a swinging arm.
        public static YuragiProfile Fanning => new(new Vector2(0.7f, 1f), 0.15f, 5, 1f, 2f);

        public float Power(float time, float seed)
        {
            var count = Mathf.Clamp(octaves, 1, MaxOctaves);
            float sum = 0f, weightSquares = 0f, weight = 1f, frequency = baseFrequency;
            for (var i = 0; i < count; i++)
            {
                sum += weight * (Mathf.Clamp01(Mathf.PerlinNoise(time * frequency, seed + 10f * i)) - 0.5f);
                weightSquares += weight * weight;
                weight *= roughness;
                frequency *= 2f;
            }

            // Adding octaves narrows the spread; widen it back the same way
            // whatever the weights, then by depth.
            var level = 0.5f + depth * sum / Mathf.Sqrt(weightSquares);
            return Mathf.Lerp(powerRange.x, powerRange.y, Mathf.Clamp01(level));
        }
    }
}
