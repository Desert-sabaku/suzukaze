using Features.Common.Scripts;
using UnityEngine;
using UnityEngine.VFX;

namespace Features.Bonfire.Scripts
{
    /// <summary>
    ///     BetweenSceneTimeManager の時刻に合わせて焚き火を点けたり消したりする。
    ///     消すときは発生だけを止め、残った炎や煙は寿命まで燃え尽きさせる
    /// </summary>
    [RequireComponent(typeof(VisualEffect))]
    public class BonfireTimeOfDay : MonoBehaviour
    {
        private const float FallbackHour = 12f;

        [Tooltip("この時刻 (0〜24) に点火する。日没は 18 時")]
        [SerializeField] [Range(0f, 24f)] private float igniteHour = 17.5f;

        [Tooltip("この時刻 (0〜24) に消火する。日の出は 6 時")]
        [SerializeField] [Range(0f, 24f)] private float extinguishHour = 6.5f;

        [Tooltip("ライトが点灯・消灯しきるまでの秒数")]
        [SerializeField] [Min(0f)] private float lightFadeSeconds = 1.5f;

        [Tooltip("ライトの明るさを揺らす幅 (基準強度に対する割合)。0 で揺らさない")]
        [SerializeField] [Range(0f, 1f)] private float flickerAmount = 0.45f;

        [Tooltip("ライトの明るさが揺らぐ速さ")]
        [SerializeField] [Min(0f)] private float flickerSpeed = 3f;

        [Tooltip("焚き火と連動させるライト")]
        [SerializeField] private Light[] lights;

        private float[] _baseIntensities;
        private bool _isLit;
        private float _lightLevel;
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
        }

        private void Start()
        {
            // 開始時点の状態にはフェードせずに合わせる
            _isLit = ShouldBeLit(CurrentHour);
            if (!_isLit) _vfx.Stop();
            _lightLevel = _isLit ? 1f : 0f;
            ApplyLights();
        }

        private void Update()
        {
            var shouldBeLit = ShouldBeLit(CurrentHour);
            if (shouldBeLit != _isLit)
            {
                _isLit = shouldBeLit;
                if (_isLit) _vfx.Play();
                else _vfx.Stop();
            }

            var step = lightFadeSeconds > 0f ? Time.deltaTime / lightFadeSeconds : 1f;
            _lightLevel = Mathf.MoveTowards(_lightLevel, _isLit ? 1f : 0f, step);
            ApplyLights();
        }

        /// <summary>
        ///     点火時刻から消火時刻までの間 (日付をまたぐ場合も含む) なら true
        /// </summary>
        private bool ShouldBeLit(float hour)
        {
            return igniteHour <= extinguishHour
                ? hour >= igniteHour && hour < extinguishHour
                : hour >= igniteHour || hour < extinguishHour;
        }

        /// <summary>
        ///     ゆっくりした大きな揺らぎと速い細かな揺らぎを重ねた、炎らしい明るさの倍率
        /// </summary>
        private float FlickerMultiplier()
        {
            var t = Time.time * flickerSpeed;
            var slow = Mathf.PerlinNoise(t, 0.37f);
            var fast = Mathf.PerlinNoise(t * 3.1f, 5.71f);
            var noise = slow * 0.7f + fast * 0.3f;
            return Mathf.Max(0f, 1f + flickerAmount * (noise * 2f - 1f));
        }

        private void ApplyLights()
        {
            var flicker = FlickerMultiplier();
            for (var i = 0; i < lights.Length; i++)
            {
                lights[i].intensity = _baseIntensities[i] * _lightLevel * flicker;
                lights[i].enabled = _lightLevel > 0f;
            }
        }
    }
}
