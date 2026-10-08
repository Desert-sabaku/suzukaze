using UnityEngine;

namespace Features.Sound.Scripts
{
    /// <summary>
    ///     聞き手の感覚の鋭さ (0〜1)。夕涼みのあいだ YusuzumiSoundDirector が上げ、各音源が参照する
    /// </summary>
    public static class SoundSensitivity
    {
        private static float _level;

        public static float Level
        {
            get => _level;
            set => _level = Mathf.Clamp01(value);
        }

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.SubsystemRegistration)]
        private static void Reset()
        {
            _level = 0f;
        }
    }
}
