using System;
using UnityEngine;

namespace Features.Common.Scripts
{
    /// <summary>
    ///     太陽が 1 日で通る平面。南中 (12 時) の方位と高度で決める。
    ///     6 時に南中方位の左 90° の地平線から昇り、12 時に南中し、18 時に右 90° の地平線へ沈む
    /// </summary>
    [Serializable]
    public struct SunPath
    {
        [Tooltip("12 時に太陽がある方位 (度)。真上から見て +Z を 0、+X を 90 とする時計回り")]
        [Range(-180f, 180f)]
        public float noonAzimuth;

        [Tooltip("12 時の太陽の高さ (度)。0 で地平線、90 で真上")]
        [Range(0f, 90f)]
        public float noonElevation;

        public SunPath(float noonAzimuth, float noonElevation)
        {
            this.noonAzimuth = noonAzimuth;
            this.noonElevation = noonElevation;
        }

        /// <summary>
        ///     hour 時に太陽がある方向 (ライトから見た向きの逆、単位ベクトル)
        /// </summary>
        public Vector3 SunDirectionAt(float hour)
        {
            var (sunrise, noon) = Basis();
            // 6 時を 0° として 24 時間で 1 周する
            var angle = (hour - 6f) * 360f / 24f * Mathf.Deg2Rad;
            return Mathf.Cos(angle) * sunrise + Mathf.Sin(angle) * noon;
        }

        /// <summary>
        ///     hour 時に Directional Light が向く回転
        /// </summary>
        public Quaternion RotationAt(float hour)
        {
            var (sunrise, noon) = Basis();
            // 平面の法線は光の向きと常に直交するので、真上から照らすときも up に使える
            return Quaternion.LookRotation(-SunDirectionAt(hour), Vector3.Cross(sunrise, noon));
        }

        /// <summary>
        ///     日の出 (6 時) と南中 (12 時) の太陽の方向
        /// </summary>
        private (Vector3 sunrise, Vector3 noon) Basis()
        {
            var noonRotation = Quaternion.Euler(-noonElevation, noonAzimuth, 0f);
            return (Quaternion.Euler(0f, noonAzimuth - 90f, 0f) * Vector3.forward, noonRotation * Vector3.forward);
        }
    }
}
