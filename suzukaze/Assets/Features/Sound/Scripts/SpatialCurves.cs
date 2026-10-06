using System.Collections.Generic;
using UnityEngine;

namespace Features.Sound.Scripts
{
    /// <summary>
    ///     距離による聞こえ方のカーブ
    /// </summary>
    public static class SpatialCurves
    {
        /// <summary>
        ///     AudioSource のカスタム減衰カーブ (横軸は maxDistance で正規化した距離)。
        ///     現実の点音源と同じく、距離が 2 倍になるごとに 6dB 下がる (1/r)。
        ///     maxDistance の手前で 0 へ落とし、急に途切れないようにする
        /// </summary>
        public static AnimationCurve InverseDistance(float minDistance, float maxDistance)
        {
            var points = new List<Vector2> { new(0f, 1f) };
            var min = Mathf.Clamp(minDistance / maxDistance, 0.001f, 0.9f);
            points.Add(new Vector2(min, 1f));

            const float fadeStart = 0.85f;
            for (var d = min * 1.5f; d < fadeStart; d *= 1.5f) points.Add(new Vector2(d, min / d));
            points.Add(new Vector2(fadeStart, min / fadeStart));
            points.Add(new Vector2(1f, 0f));
            return Linear(points);
        }

        /// <summary>
        ///     空気による高音の吸収。横軸は実際の距離 (m)、値は 22kHz を 1 とした遮断周波数の割合。
        ///     100m 先で 8kHz 付近から上が削れる程度にし、遠くの蝉や鳥の声をこもらせる
        /// </summary>
        public static AnimationCurve AirAbsorption()
        {
            return Linear(new List<Vector2>
            {
                new(0f, 1f),
                new(5f, 1f),
                new(20f, 0.75f),
                new(50f, 0.5f),
                new(100f, 0.36f),
                new(200f, 0.22f)
            });
        }

        private static AnimationCurve Linear(IReadOnlyList<Vector2> points)
        {
            var keys = new Keyframe[points.Count];
            for (var i = 0; i < points.Count; i++)
            {
                var inSlope = i > 0 ? Slope(points[i - 1], points[i]) : 0f;
                var outSlope = i < points.Count - 1 ? Slope(points[i], points[i + 1]) : 0f;
                keys[i] = new Keyframe(points[i].x, points[i].y, inSlope, outSlope);
            }

            return new AnimationCurve(keys);
        }

        private static float Slope(Vector2 a, Vector2 b)
        {
            return (b.y - a.y) / Mathf.Max(b.x - a.x, 1e-5f);
        }
    }
}
