using Features.Common.Scripts;
using UnityEngine;
using UnityEngine.VFX;

namespace Features.Firefly.Scripts
{
    /// <summary>
    ///     BetweenSceneTimeManager の時刻に合わせて、夜の間だけホタル (VFX) を飛ばす。
    ///     出現・消失は発生量と明るさをフェードさせ、残ったホタルは寿命まで光らせる
    /// </summary>
    [RequireComponent(typeof(VisualEffect))]
    public class FireflyTimeOfDay : MonoBehaviour
    {
        private const float FallbackHour = 12f;
        private static readonly int SpawnRateId = Shader.PropertyToID("SpawnRate");
        private static readonly int GlowIntensityId = Shader.PropertyToID("GlowIntensity");

        [Tooltip("この時刻 (0〜24) からホタルが出始める。日没は 18 時")]
        [SerializeField] [Range(0f, 24f)] private float appearHour = 18.5f;

        [Tooltip("この時刻 (0〜24) にホタルがいなくなる。日の出は 6 時")]
        [SerializeField] [Range(0f, 24f)] private float disappearHour = 5f;

        [Tooltip("1 秒あたりに発生させるホタルの数")]
        [SerializeField] [Min(0f)] private float spawnRate = 2.5f;

        [Tooltip("出現・消失のフェードにかける秒数")]
        [SerializeField] [Min(0f)] private float fadeSeconds = 3f;

        private float _level;
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
        }

        private void Start()
        {
            // 開始時点の状態にはフェードせずに合わせる
            _level = IsNight(CurrentHour) ? 1f : 0f;
            Apply();
        }

        private void Update()
        {
            var step = fadeSeconds > 0f ? Time.deltaTime / fadeSeconds : 1f;
            _level = Mathf.MoveTowards(_level, IsNight(CurrentHour) ? 1f : 0f, step);
            Apply();
        }

        /// <summary>
        ///     出現時刻から消失時刻までの間 (日付をまたぐ場合も含む) なら true
        /// </summary>
        private bool IsNight(float hour)
        {
            return appearHour <= disappearHour
                ? hour >= appearHour && hour < disappearHour
                : hour >= appearHour || hour < disappearHour;
        }

        private void Apply()
        {
            _vfx.SetFloat(SpawnRateId, spawnRate * _level);
            _vfx.SetFloat(GlowIntensityId, _level);
        }
    }
}
