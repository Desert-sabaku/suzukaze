using System.Collections.Generic;
using System.IO;
using System.Linq;
using Sirenix.OdinInspector;
using UnityEditor;
using UnityEngine;

namespace Features.Common.Scripts
{
    [AddressableGlobalConfig("GameSettings")]
    [CreateAssetMenu(fileName = "Game Settings", menuName = "Game Settings", order = 0)]
    public class GameSettings : AddressableGlobalConfig<GameSettings>
    {
        [Title("シーン遷移")] public float sceneTransitionDuration = 1f;
        [Title("時間管理")] public float timeScale = 1f;
        [Tooltip("ゲーム開始時の時刻 (0〜24)")]
        [Range(0f, 24f)]
        public float startHour = 18f;

        [Tooltip("太陽の通り道の既定値。シーンの Directional Light に SceneSunPath があればそちらを優先する")]
        public SunPath sunPath = new(90f, 90f);

        [Title("ゲームの時間管理")] public int gameTimeLimit = 60;
#if UNITY_EDITOR
        [ValueDropdown(nameof(GetSceneNames))]
#endif
        public string resultScene;

#if UNITY_EDITOR
        [ValueDropdown(nameof(GetSceneNames))]
#endif
        public string[] ignoreTimeManageScenes;

#if UNITY_EDITOR
        private static IEnumerable<string> GetSceneNames()
        {
            // 登録されているシーンの名前を取得する
            return from t in EditorBuildSettings.scenes
                select t.path
                into scenePath
                let sceneName = Path.GetFileNameWithoutExtension(scenePath)
                where !string.IsNullOrEmpty(sceneName)
                select sceneName;
        }
#endif
    }
}