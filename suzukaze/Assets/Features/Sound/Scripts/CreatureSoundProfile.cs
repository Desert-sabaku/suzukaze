using Sirenix.OdinInspector;
using UnityEngine;
using UnityEngine.Audio;

namespace Features.Sound.Scripts
{
    /// <summary>
    ///     生き物や環境音 1 種類分の鳴き方。CreatureSoundEmitter がこれを参照して鳴く
    /// </summary>
    [CreateAssetMenu(fileName = "Creature Sound Profile", menuName = "Sound/Creature Sound Profile", order = 0)]
    public class CreatureSoundProfile : ScriptableObject
    {
        public enum PlaybackMode
        {
            /// <summary>鳴き終わるたびに休み、また鳴く (蝉・鳥)</summary>
            Call,

            /// <summary>ループ素材を鳴らし続ける (コオロギ・波・風)</summary>
            Loop
        }

        [Title("音源")] public AudioClip[] clips;
        public AudioMixerGroup output;
        public PlaybackMode mode = PlaybackMode.Call;
        [Range(0f, 1f)] public float volume = 1f;

        [Tooltip("個体ごとに固定されるピッチのばらつき (体の大きさの違い)")] [Range(0f, 0.2f)]
        public float individualPitchVariance = 0.04f;

        [Range(0f, 0.1f)] public float callPitchVariance = 0.01f;
        [Range(0f, 12f)] public float callVolumeVarianceDb = 2f;

        [Title("時間帯")] [Tooltip("横軸が時刻 (0〜24)、縦軸が活動度 (0〜1)")]
        public AnimationCurve activityByHour = AnimationCurve.Constant(0f, 24f, 1f);

        [Tooltip("時刻の変化に追従するまでの時間 (秒)")] [Min(0.01f)]
        public float activitySmoothing = 3f;

        [Title("Call")] [ShowIf(nameof(mode), PlaybackMode.Call)] [Tooltip("活動度 1 のときの、鳴き終わってから次に鳴き始めるまでの間隔 (秒)")]
        [MinMaxSlider(0f, 120f, true)]
        public Vector2 restSeconds = new(5f, 15f);

        [ShowIf(nameof(mode), PlaybackMode.Call)] [Tooltip("続けて鳴く回数 (カラスの「カー、カー、カー」など)")]
        public Vector2Int callsPerBout = new(1, 1);

        [ShowIf(nameof(mode), PlaybackMode.Call)] [MinMaxSlider(0f, 5f, true)]
        public Vector2 gapInBoutSeconds = new(0.3f, 0.8f);

        [Title("Loop")] [ShowIf(nameof(mode), PlaybackMode.Loop)] [Tooltip("鳴き続ける時間と休む時間 (秒)。休む時間が 0 なら休まない")]
        [MinMaxSlider(0f, 300f, true)]
        public Vector2 singSeconds = new(20f, 60f);

        [ShowIf(nameof(mode), PlaybackMode.Loop)] [MinMaxSlider(0f, 120f, true)]
        public Vector2 pauseSeconds = Vector2.zero;

        [ShowIf(nameof(mode), PlaybackMode.Loop)] [Tooltip("風の強弱のようなゆっくりした音量の揺らぎ (0〜1)")] [Range(0f, 1f)]
        public float modulationDepth;

        [ShowIf(nameof(mode), PlaybackMode.Loop)] [Min(0.1f)]
        public float modulationPeriod = 8f;

        [ShowIf(nameof(mode), PlaybackMode.Loop)] [Min(0.01f)]
        public float fadeSeconds = 1.5f;

        [Title("風への追従")] public bool windDrivenLoop;
        [ShowIf(nameof(windDrivenLoop))] [Range(0f, 0.99f)]
        public float windThreshold = 0.5f;
        [ShowIf(nameof(windDrivenLoop))] [Min(0f)]
        public float windVolumeMultiplier = 1f;

        public float WindGain(float power) => windDrivenLoop ? Mathf.InverseLerp(windThreshold, 1f, power) : 1f;
        public float WindVolumeScale => windDrivenLoop ? windVolumeMultiplier : 1f;

        [Title("立体音響")] [Tooltip("0 で 2D (どこにいても同じ聞こえ方)、1 で完全な 3D")] [Range(0f, 1f)]
        public float spatialBlend = 1f;

        [Tooltip("この距離までは減衰しない。音源の大きさの目安")] [Min(0.01f)]
        public float minDistance = 2f;

        [Min(0.1f)] public float maxDistance = 80f;

        [Tooltip("音の広がり。小さな生き物は 0 (点音源)、波打ち際のように広い音源は大きくする")] [Range(0f, 360f)]
        public float spread;

        [Tooltip("遠いほど高音が減衰する (空気による吸収)")] public bool airAbsorption = true;

        [Range(0, 256)] public int priority = 128;

        public bool HasClips => clips != null && clips.Length > 0;

        /// <summary>
        ///     指定した時刻での活動度 (0〜1)
        /// </summary>
        public float Activity(float hour)
        {
            return Mathf.Clamp01(activityByHour.Evaluate(Mathf.Repeat(hour, 24f)));
        }

        /// <summary>
        ///     鳴く素材を選ぶ。素材が複数あるときは直前と同じものを避ける
        /// </summary>
        public AudioClip PickClip(AudioClip previous)
        {
            if (!HasClips) return null;
            if (clips.Length == 1) return clips[0];

            AudioClip clip;
            do clip = clips[Random.Range(0, clips.Length)];
            while (clip == previous);
            return clip;
        }
    }
}
