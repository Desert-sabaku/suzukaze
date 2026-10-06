using Sirenix.OdinInspector;
using UnityEngine;
using UnityEngine.Audio;

namespace Features.Sound.Scripts
{
    /// <summary>
    ///     シーン全体の音響を時刻に合わせて調整する。各シーンの Soundscape に 1 つ置く
    /// </summary>
    public class SoundscapeDirector : MonoBehaviour
    {
        [Title("Mixer")] [SerializeField] [Required]
        private AudioMixer mixer;

        [Tooltip("時刻ごとの屋外残響の戻り量 (dB)。風が止み静かな夜は音が遠くまで響く")] [SerializeField]
        private AnimationCurve reverbDbByHour = new(
            new Keyframe(0f, -4f),
            new Keyframe(4.5f, -4f),
            new Keyframe(7f, -10f),
            new Keyframe(17f, -10f),
            new Keyframe(19.5f, -4f),
            new Keyframe(24f, -4f));

        [Title("デバッグ")] [Tooltip("有効にすると、下の時刻で鳴かせる")] [SerializeField]
        private bool overrideHour;

        [SerializeField] [Range(0f, 24f)] [ShowIf(nameof(overrideHour))]
        private float debugHour = 12f;

        [ShowInInspector] [ReadOnly] private float CurrentHour => SoundTimeOfDay.CurrentHour;

        private void Update()
        {
            SoundTimeOfDay.OverrideHour = overrideHour ? debugHour : null;
            if (mixer)
                mixer.SetFloat(SoundMixerParameters.EnvironmentReverbVolume,
                    reverbDbByHour.Evaluate(SoundTimeOfDay.CurrentHour));
        }

        private void OnDisable()
        {
            if (overrideHour) SoundTimeOfDay.OverrideHour = null;
        }
    }
}
