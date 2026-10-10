using System.Collections.Generic;
using System.IO;
using System.Linq;
using Sirenix.OdinInspector;
using Suzukaze.Fan;
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

        [Tooltip("ゲーム開始時の時刻 (0〜24)")] [Range(0f, 24f)]
        public float startHour = 18f;

        [Tooltip("太陽の通り道の既定値。シーンの Directional Light に SceneSunPath があればそちらを優先する")]
        public SunPath sunPath = new(90f, 90f);

        [Title("ゲームの時間管理")] public int gameTimeLimit = 60;

        [ValueDropdown(nameof(GetSceneNames))] public string resultScene;
        [ValueDropdown(nameof(GetSceneNames))] public string[] ignoreTimeManageScenes;
        [ValueDropdown(nameof(GetSceneNames))] public string[] gameScenes;

        [Title("香り")] [Tooltip("ラムネを開けてから香りを出し続ける秒数")] [Min(0f)]
        public float ramuneScentSeconds = 10f;

        [Tooltip("扇ぐのをやめてから香りを止めるまでの秒数。認識が一瞬途切れても止めない")] [Min(0f)]
        public float fanningScentGraceSeconds = 3f;

        [Tooltip("扇いでも香りを出さないシーン")] [ValueDropdown(nameof(GetSceneNames))]
        public string[] noFanningScentScenes = { "Sea" };

        [Tooltip("ラムネの香りのディフューザーが裏にあるファン")]
        public FanLocation ramuneDiffuserFan = new(FanSide.Left, FanPosition.Front);

        [Tooltip("森の香り (扇ぎ) のディフューザーが裏にあるファン")]
        public FanLocation forestDiffuserFan = new(FanSide.Right, FanPosition.Front);

        [Tooltip("香りを出している間、ディフューザーの前のファンを回す出力 (0〜255)。" +
                 "実機のデューティは (値/255)^2.2 で、例えば 20% は 122、30% は 148")]
        [Range(0, 255)]
        public int scentFanOutput = 122;

        private static IEnumerable<string> GetSceneNames()
        {
#if UNITY_EDITOR
            // 登録されているシーンの名前を取得する
            return from t in EditorBuildSettings.scenes
                select t.path
                into scenePath
                let sceneName = Path.GetFileNameWithoutExtension(scenePath)
                where !string.IsNullOrEmpty(sceneName)
                select sceneName;
#else
            return new List<string>();
#endif
        }
    }
}