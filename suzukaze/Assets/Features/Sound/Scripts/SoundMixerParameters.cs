using UnityEngine;
using UnityEngine.Audio;

namespace Features.Sound.Scripts
{
    /// <summary>
    ///     MainMixer の Exposed Parameters の名前。値はすべて dB
    /// </summary>
    public static class SoundMixerParameters
    {
        public const string MasterVolume = "MasterVolume";
        public const string EnvironmentVolume = "EnvironmentVolume";
        public const string AmbientVolume = "AmbientVolume";
        public const string CicadasVolume = "CicadasVolume";
        public const string InsectsVolume = "InsectsVolume";
        public const string BirdsVolume = "BirdsVolume";
        public const string EnvironmentReverbVolume = "EnvironmentReverbVolume";
        public const string GestureEffectVolume = "GestureEffectVolume";

        private const float MinDb = -80f;

        /// <summary>
        ///     レイヤーの音量を 0〜1 の線形値で設定する
        /// </summary>
        public static void SetLinearVolume(AudioMixer mixer, string parameter, float linear)
        {
            var db = linear > 0.0001f ? 20f * Mathf.Log10(linear) : MinDb;
            mixer.SetFloat(parameter, Mathf.Max(db, MinDb));
        }
    }
}
