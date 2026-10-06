using Features.Common.Scripts;
using UnityEngine;

namespace Features.Sound.Scripts
{
    /// <summary>
    ///     音響が参照する時刻。BetweenSceneTimeManager の時刻を使い、デバッグ時は上書きできる
    /// </summary>
    public static class SoundTimeOfDay
    {
        private const float FallbackHour = 12f;

        /// <summary>
        ///     null 以外なら、この時刻で鳴かせる (SoundscapeDirector から設定する)
        /// </summary>
        public static float? OverrideHour { get; set; }

        public static float CurrentHour
        {
            get
            {
                if (OverrideHour.HasValue) return Mathf.Repeat(OverrideHour.Value, 24f);
                var timeManager = BetweenSceneTimeManager.Instance;
                return timeManager ? timeManager.CurrentHour : FallbackHour;
            }
        }
    }
}
