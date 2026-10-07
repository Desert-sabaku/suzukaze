using UnityEngine;

namespace Features.Common.Scripts
{
    /// <summary>
    ///     Directional Light の高度に応じて明るさを落とす。
    ///     BetweenSceneTimeManager は向きしか変えないため、夜に地平線の下から照らされるのを防ぐ
    /// </summary>
    [RequireComponent(typeof(Light))]
    public class SunHorizonFade : MonoBehaviour
    {
        // 0 にすると URP のカリングでメインライトから外れ、スカイボックスが太陽の向きを取れなくなる
        private const float MinIntensity = 0.001f;

        [Tooltip("地平線からこの高度 (度) までの間で明るさを 0 からフェードする")]
        [SerializeField] private float fadeDegrees = 10f;

        private float _baseIntensity;
        private Light _light;

        private void Awake()
        {
            _light = GetComponent<Light>();
            _baseIntensity = _light.intensity;
        }

        private void LateUpdate()
        {
            // ライトは forward 方向に照らすので、下向き成分が太陽の高さになる
            var elevation = Mathf.Asin(Mathf.Clamp(-transform.forward.y, -1f, 1f)) * Mathf.Rad2Deg;
            var factor = Mathf.Clamp01(elevation / Mathf.Max(fadeDegrees, 0.01f));
            _light.intensity = Mathf.Max(_baseIntensity * factor, MinIntensity);
        }
    }
}
