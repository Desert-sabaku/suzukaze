using Sirenix.OdinInspector;
using UnityEngine;

namespace Features.Common.Scripts
{
    [AddressableGlobalConfig("GameSettings")]
    [CreateAssetMenu(fileName = "Game Settings", menuName = "Game Settings", order = 0)]
    public class GameSettings : AddressableGlobalConfig<GameSettings>
    {
        [Title("シーン遷移")] public float sceneTransitionDuration = 1f;
        [Title("時間管理")] public float timeScale = 1f;
        public Vector3 lightAxis = new(0.3f, -1f, 0.3f);
    }
}