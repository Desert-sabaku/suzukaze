using UnityEngine;
using UnityEngine.Events;
using UnityEngine.VFX;

namespace Features.Result.Scripts
{
    /// <summary>
    ///     リザルト用の線香花火 (Senko Hanabi VFX) を再生する．
    ///     スコアから激しさと火玉が落ちるまでの時間を決め，VFX の Elapsed を進め，手で持っているように揺らす．
    ///     このオブジェクトの位置が手 (こよりの上端) で，火玉は StringLength だけ下にぶら下がる．
    /// </summary>
    [DisallowMultipleComponent]
    [RequireComponent(typeof(VisualEffect))]
    public class SenkoHanabiController : MonoBehaviour
    {
        private static readonly int IntensityId = Shader.PropertyToID("Intensity");
        private static readonly int DropTimeId = Shader.PropertyToID("DropTime");
        private static readonly int BurnDurationId = Shader.PropertyToID("BurnDuration");
        private static readonly int ElapsedId = Shader.PropertyToID("Elapsed");
        private static readonly int StringLengthId = Shader.PropertyToID("StringLength");
        private static readonly int GroundYId = Shader.PropertyToID("GroundY");

        [Header("Playback")] [SerializeField] private bool playOnStart = true;

        [Tooltip("playOnStart で使うスコア (0-1)．ゲームシーンから来たときはプレイ全体の正確性を使う．")]
        [Range(0f, 1f)]
        [SerializeField]
        private float score = 1f;

        [Header("Score Mapping")]
        [Tooltip("着火から散り菊が終わる (燃え尽きる) までの秒数．段階はこの長さに対する割合で進む．")]
        [SerializeField]
        private float burnDuration = 20f;

        [Tooltip("スコア 0 / 1 のときの激しさ．")] [SerializeField]
        private Vector2 intensityRange = new(0.1f, 1f);

        [Tooltip("スコア 0 のときに火玉が落ちるまでの秒数．")] [SerializeField]
        private float shortestDropTime = 3f;

        [Tooltip("スコア 1 のとき，燃え尽きてから火玉が落ちるまでの秒数．")] [SerializeField]
        private float dropDelayAfterBurnOut = 2f;

        [Header("Sway")] [Tooltip("手の傾きのゆっくりした揺れ (度)．")] [SerializeField]
        private float swayAngle = 2.5f;

        [SerializeField] private float swayFrequency = 0.3f;

        [Tooltip("手の細かい震え (度)．")] [SerializeField]
        private float tremorAngle = 0.4f;

        [SerializeField] private float tremorFrequency = 2.5f;

        [Tooltip("手の位置のゆっくりしたずれ (m)．")] [SerializeField]
        private float drift = 0.004f;

        [Header("Events")] [Tooltip("火玉が落ち始めたとき．")] [SerializeField]
        private UnityEvent onDropped = new();

        [Tooltip("落ちた火玉が冷えて消えたとき．")] [SerializeField]
        private UnityEvent onFinished = new();

        private Vector3 _baseLocalPosition;
        private Quaternion _baseLocalRotation;
        private float _finishTime;
        private float _noiseSeed;
        private VisualEffect _vfx;

        public float Intensity { get; private set; }
        public float DropTime { get; private set; }
        public float Elapsed { get; private set; }
        public bool IsPlaying { get; private set; }
        public bool IsDropped => IsPlaying && Elapsed >= DropTime;
        public UnityEvent OnDropped => onDropped;
        public UnityEvent OnFinished => onFinished;

        private void Awake()
        {
            _vfx = GetComponent<VisualEffect>();
            _baseLocalPosition = transform.localPosition;
            _baseLocalRotation = transform.localRotation;
            _noiseSeed = Random.Range(0f, 100f);
        }

        private void Start()
        {
            // ゲームシーンから来たときはプレイ全体の正確性を使う
            if (playOnStart) Play(PlayScore.TryTake(out var playScore) ? playScore : score);
            else _vfx.SetFloat(ElapsedId, 0f);
        }

        private void Update()
        {
            Sway(Time.time);
            if (!IsPlaying) return;

            var previous = Elapsed;
            Elapsed += Time.deltaTime;
            _vfx.SetFloat(ElapsedId, Elapsed);

            if (previous < DropTime && Elapsed >= DropTime) onDropped.Invoke();
            if (previous < _finishTime && Elapsed >= _finishTime)
            {
                IsPlaying = false;
                onFinished.Invoke();
            }
        }

        private void OnDisable()
        {
            transform.localPosition = _baseLocalPosition;
            transform.localRotation = _baseLocalRotation;
        }

        /// <summary>スコア (0-1) から激しさと火玉が落ちるまでの時間を決めて再生する．</summary>
        public void Play(float normalizedScore)
        {
            var s = Mathf.Clamp01(normalizedScore);
            var intensity = Mathf.Lerp(intensityRange.x, intensityRange.y, s);
            var dropTime = Mathf.Lerp(shortestDropTime, burnDuration + dropDelayAfterBurnOut, s);
            Play(intensity, dropTime);
        }

        /// <summary>激しさ (0-1) と火玉が落ちるまでの秒数を直接指定して再生する．</summary>
        public void Play(float intensity, float dropTime)
        {
            Intensity = Mathf.Clamp01(intensity);
            DropTime = Mathf.Max(0f, dropTime);
            Elapsed = 0f;
            _finishTime = DropTime + FallDuration() + 1.5f;

            _vfx.SetFloat(IntensityId, Intensity);
            _vfx.SetFloat(DropTimeId, DropTime);
            _vfx.SetFloat(BurnDurationId, burnDuration);
            _vfx.SetFloat(ElapsedId, 0f);
            _vfx.Reinit();
            IsPlaying = true;
        }

        public void Stop()
        {
            IsPlaying = false;
            _vfx.Reinit();
            _vfx.SetFloat(ElapsedId, 0f);
        }

        // 火玉が地面 (GroundY) に着くまでの秒数．VFX 側の落下と同じ計算．
        private float FallDuration()
        {
            var height = -_vfx.GetFloat(StringLengthId) - _vfx.GetFloat(GroundYId);
            return Mathf.Sqrt(Mathf.Max(0f, height) * 2f / 9.81f);
        }

        private void Sway(float time)
        {
            float Noise(float frequency, float offset)
            {
                return Mathf.PerlinNoise(_noiseSeed + offset, time * frequency) * 2f - 1f;
            }

            var pitch = Noise(swayFrequency, 0f) * swayAngle + Noise(tremorFrequency, 10f) * tremorAngle;
            var roll = Noise(swayFrequency, 20f) * swayAngle + Noise(tremorFrequency, 30f) * tremorAngle;
            transform.localRotation = _baseLocalRotation * Quaternion.Euler(pitch, 0f, roll);

            var offset = new Vector3(Noise(swayFrequency * 0.7f, 40f), Noise(swayFrequency * 0.7f, 50f),
                Noise(swayFrequency * 0.7f, 60f)) * drift;
            transform.localPosition = _baseLocalPosition + offset;
        }
    }
}
