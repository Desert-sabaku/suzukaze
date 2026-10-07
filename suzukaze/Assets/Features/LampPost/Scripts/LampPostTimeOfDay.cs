using Features.Common.Scripts;
using UnityEngine;
using UnityEngine.VFX;

namespace Features.LampPost.Scripts
{
    /// <summary>
    ///     BetweenSceneTimeManager の時刻に合わせて街灯の炎 (VFX) とライトを点けたり消したりする。
    ///     消すときは発生だけを止め、残った炎は寿命まで燃え尽きさせる
    /// </summary>
    [RequireComponent(typeof(VisualEffect))]
    public class LampPostTimeOfDay : MonoBehaviour
    {
        private const float FallbackHour = 12f;

        [Tooltip("この時刻 (0〜24) に点灯する。日没は 18 時")]
        [SerializeField] [Range(0f, 24f)] private float turnOnHour = 17.5f;

        [Tooltip("この時刻 (0〜24) に消灯する。日の出は 6 時")]
        [SerializeField] [Range(0f, 24f)] private float turnOffHour = 6.5f;

        [Tooltip("ライトが点灯・消灯しきるまでの秒数")]
        [SerializeField] [Min(0f)] private float lightFadeSeconds = 1.5f;

        [Tooltip("ライトの明るさを揺らす幅 (基準強度に対する割合)。0 で揺らさない")]
        [SerializeField] [Range(0f, 1f)] private float flickerAmount = 0.15f;

        [Tooltip("ライトの明るさが揺らぐ速さ")]
        [SerializeField] [Min(0f)] private float flickerSpeed = 2f;

        [Tooltip("街灯と連動させるライト")]
        [SerializeField] private Light[] lights;

        private float[] _baseIntensities;
        private bool _isOn;
        private float _lightLevel;
        private float _noiseOffset;
        private VisualEffect _vfx;

        private static float CurrentHour
        {
            get
            {
                var timeManager = BetweenSceneTimeManager.Instance;
                return timeManager ? timeManager.CurrentHour : FallbackHour;
            }
        }

        private void Awake()
        {
            _vfx = GetComponent<VisualEffect>();
            _baseIntensities = new float[lights.Length];
            for (var i = 0; i < lights.Length; i++) _baseIntensities[i] = lights[i].intensity;
            // 街灯ごとに揺らぎをずらす
            _noiseOffset = Random.value * 100f;
        }

        private void Start()
        {
            // 開始時点の状態にはフェードせずに合わせる
            _isOn = ShouldBeOn(CurrentHour);
            if (!_isOn) _vfx.Stop();
            _lightLevel = _isOn ? 1f : 0f;
            ApplyLights();
        }

        private void Update()
        {
            var shouldBeOn = ShouldBeOn(CurrentHour);
            if (shouldBeOn != _isOn)
            {
                _isOn = shouldBeOn;
                if (_isOn) _vfx.Play();
                else _vfx.Stop();
            }

            var step = lightFadeSeconds > 0f ? Time.deltaTime / lightFadeSeconds : 1f;
            _lightLevel = Mathf.MoveTowards(_lightLevel, _isOn ? 1f : 0f, step);
            ApplyLights();
        }

        /// <summary>
        ///     点灯時刻から消灯時刻までの間 (日付をまたぐ場合も含む) なら true
        /// </summary>
        private bool ShouldBeOn(float hour)
        {
            return turnOnHour <= turnOffHour
                ? hour >= turnOnHour && hour < turnOffHour
                : hour >= turnOnHour || hour < turnOffHour;
        }

        private void ApplyLights()
        {
            var noise = Mathf.PerlinNoise(Time.time * flickerSpeed + _noiseOffset, 0.37f);
            var flicker = Mathf.Max(0f, 1f + flickerAmount * (noise * 2f - 1f));
            for (var i = 0; i < lights.Length; i++)
            {
                lights[i].intensity = _baseIntensities[i] * _lightLevel * flicker;
                lights[i].enabled = _lightLevel > 0f;
            }
        }
    }
}
