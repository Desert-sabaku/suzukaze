using Cysharp.Threading.Tasks;
using LitMotion;
using Sirenix.OdinInspector;
using UnityEngine;
using UnityEngine.Audio;
using UnityEngine.SceneManagement;

namespace Features.Sound.Scripts
{
    /// <summary>
    ///     シーン全体の音響を時刻に合わせて調整する。各シーンの Soundscape に 1 つ置く
    /// </summary>
    public class SoundscapeDirector : MonoBehaviour
    {
        private static SoundscapeDirector _current;
        private static AudioMixer _lastMixer;

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

        [Title("シーン遷移")] [Tooltip("シーン開始時に環境音をフェードインする時間 (秒)")] [SerializeField] [Min(0f)]
        private float fadeInSeconds = 1.5f;

        [Title("デバッグ")] [Tooltip("有効にすると、下の時刻で鳴かせる")] [SerializeField]
        private bool overrideHour;

        [SerializeField] [Range(0f, 24f)] [ShowIf(nameof(overrideHour))]
        private float debugHour = 12f;

        private float _fade;
        private MotionHandle _fadeMotion;

        [ShowInInspector] [ReadOnly] private float CurrentHour => SoundTimeOfDay.CurrentHour;

        private void Awake()
        {
            // 音源が鳴り始める前に環境音を絞っておき、Start からフェードインする
            ApplyFade(0f);
        }

        private void Start()
        {
            FadeTo(1f, fadeInSeconds);
        }

        private void Update()
        {
            SoundTimeOfDay.OverrideHour = overrideHour ? debugHour : null;
            if (mixer)
                mixer.SetFloat(SoundMixerParameters.EnvironmentReverbVolume,
                    reverbDbByHour.Evaluate(SoundTimeOfDay.CurrentHour));
        }

        private void OnEnable()
        {
            _current = this;
            _lastMixer = mixer;
        }

        private void OnDisable()
        {
            if (overrideHour) SoundTimeOfDay.OverrideHour = null;
            if (_fadeMotion.IsActive()) _fadeMotion.Cancel();
            if (_current == this) _current = null;
        }

        /// <summary>
        ///     シーンを離れる前に、今のシーンの環境音をフェードアウトする
        /// </summary>
        public static UniTask FadeOutAsync(float duration)
        {
            // フェード中に別のフェードで上書きされても、遷移側の待機は例外で止めない
            return _current
                ? _current.FadeTo(0f, duration).ToUniTask().SuppressCancellationThrow().AsUniTask()
                : UniTask.CompletedTask;
        }

        private MotionHandle FadeTo(float target, float duration)
        {
            if (_fadeMotion.IsActive()) _fadeMotion.Cancel();
            _fadeMotion = LMotion.Create(_fade, target, duration)
                .WithEase(Ease.InOutSine)
                .Bind(ApplyFade);
            return _fadeMotion;
        }

        private void ApplyFade(float value)
        {
            _fade = value;
            if (mixer) SoundMixerParameters.SetLinearVolume(mixer, SoundMixerParameters.EnvironmentVolume, value);
        }

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.SubsystemRegistration)]
        private static void InstallSceneHook()
        {
            _current = null;
            _lastMixer = null;
            SceneManager.sceneLoaded -= OnSceneLoaded;
            SceneManager.sceneLoaded += OnSceneLoaded;
        }

        /// <summary>
        ///     Soundscape の無いシーンへ移ったときに、フェードアウトしたままにならないよう戻す
        /// </summary>
        private static void OnSceneLoaded(UnityEngine.SceneManagement.Scene scene, LoadSceneMode mode)
        {
            if (!_current && _lastMixer) _lastMixer.ClearFloat(SoundMixerParameters.EnvironmentVolume);
        }
    }
}
