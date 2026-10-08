using Sirenix.OdinInspector;
using UnityEngine;

namespace Features.Common.Scripts
{
    /// <summary>
    ///     シーンごとの太陽の通り道。シーンの Directional Light に付けると、
    ///     BetweenSceneTimeManager は GameSettings.sunPath の代わりにこの通り道で太陽を動かす
    /// </summary>
    [RequireComponent(typeof(Light))]
    public class SceneSunPath : MonoBehaviour
    {
        [InlineProperty]
        [HideLabel]
        public SunPath sunPath = new(0f, 60f);

        [Title("プレビュー")]
        [Tooltip("エディタ上で確認する時刻 (0〜24)")]
        [Range(0f, 24f)]
        [SerializeField]
        private float previewHour = 12f;

        [Button("この時刻の向きにする")]
        private void ApplyPreview()
        {
#if UNITY_EDITOR
            UnityEditor.Undo.RecordObject(transform, "Preview Sun Hour");
#endif
            transform.rotation = sunPath.RotationAt(previewHour);
        }

        private void OnDrawGizmosSelected()
        {
            const float radius = 5f;
            const int segments = 48;
            var origin = transform.position;

            // 太陽の通り道。地平線より上を黄色、下を灰色で描く
            for (var i = 0; i < segments; i++)
            {
                var from = sunPath.SunDirectionAt(24f * i / segments);
                var to = sunPath.SunDirectionAt(24f * (i + 1) / segments);
                Gizmos.color = from.y + to.y >= 0f ? Color.yellow : Color.gray;
                Gizmos.DrawLine(origin + from * radius, origin + to * radius);
            }

            // 南中の位置とプレビュー時刻の位置
            Gizmos.color = Color.red;
            Gizmos.DrawLine(origin, origin + sunPath.SunDirectionAt(12f) * radius);
            Gizmos.color = Color.cyan;
            Gizmos.DrawLine(origin, origin + sunPath.SunDirectionAt(previewHour) * radius);
        }
    }
}
