using System.Linq;
using Cysharp.Threading.Tasks;
using Suzukaze.Gesture;
using UnityEditor;
using UnityEngine;
using UnityEngine.SceneManagement;
using LightType = UnityEngine.LightType;

namespace Features.Common.Scripts
{
    /// <summary>
    ///     シーン間で時間を共有するための時間管理を行う
    /// </summary>
    public class BetweenSceneTimeManager : SingletonMonoBehaviour<BetweenSceneTimeManager>
    {
        private float _currentHour = 12f;
        private Transform _directionalLight;
        private SceneSunPath _sceneSunPath;
        private GameSettings _gameSettings;
        private bool _isActive = true;

        /// <summary>
        ///     現在の時刻 (0〜24)。太陽 (Directional Light) が最も高くなる角度を 12 時とする
        /// </summary>
        public float CurrentHour => Mathf.Repeat(_currentHour, 24f);

        /// <summary>
        ///     太陽の通り道。シーンの Directional Light に SceneSunPath があればそれ、なければ GameSettings のものを使う
        /// </summary>
        private SunPath SunPath => _sceneSunPath ? _sceneSunPath.sunPath : _gameSettings.sunPath;

        private void Start()
        {
            var currentScene = SceneManager.GetActiveScene();
            SetDirectionalLight(FindDirectionalLight(currentScene));
            Debug.Assert(_directionalLight != null, "Directional light not found in the scene.");

            SceneManager.activeSceneChanged += OnActiveSceneChanged;
            UniTask.Create(async () =>
            {
                _gameSettings = await GameSettings.GetInstanceAsync();
                _currentHour = _gameSettings.startHour;
                _isActive = _gameSettings.ignoreTimeManageScenes.All(ignoreScene => ignoreScene != currentScene.name);
#if UNITY_EDITOR
                if (_isActive && EditorBuildSettings.scenes.All(scene => scene.path != currentScene.path))
                {
                    _isActive = false;
                    Debug.Log($"{currentScene.name} は Build Settings に含まれていないため、時間と太陽を動かしません");
                }
#endif
            }).Forget();
        }

        private void Update()
        {
            // 設定画面 (unity_bridge) から変えられる倍率を掛け、反映後の値を設定画面へ返す
            var control = RuntimeControl.Instance;
            var timeScale = _gameSettings ? _gameSettings.timeScale * (float)control.TimeScaleMultiplier : 0f;
            control.EffectiveTimeScale = _isActive ? timeScale : 0;
            control.CurrentHour = _gameSettings && _isActive ? CurrentHour : (double?)null;
            if (!_gameSettings || !_isActive) return;

            _currentHour += Time.deltaTime * timeScale;
            _directionalLight.rotation = SunPath.RotationAt(_currentHour);
        }

        private void OnDrawGizmos()
        {
            if (!_gameSettings || !_isActive) return;

            Gizmos.color = Color.yellow;
            // 現在の太陽の方向を描画
            Gizmos.DrawLine(Vector3.zero, SunPath.SunDirectionAt(_currentHour) * 5);
        }

        private void OnActiveSceneChanged(
            UnityEngine.SceneManagement.Scene oldScene,
            UnityEngine.SceneManagement.Scene newScene
        )
        {
            _isActive = _gameSettings.ignoreTimeManageScenes.All(ignoreScene => ignoreScene != newScene.name);
            SetDirectionalLight(FindDirectionalLight(newScene));
            Debug.Assert(_directionalLight != null, "Directional light not found in the new scene.");
        }

        private void SetDirectionalLight(Transform directionalLight)
        {
            _directionalLight = directionalLight;
            _sceneSunPath = directionalLight ? directionalLight.GetComponent<SceneSunPath>() : null;
        }

        private static Transform FindDirectionalLight(UnityEngine.SceneManagement.Scene scene)
        {
            var lightObj = scene.GetRootGameObjects().FirstOrDefault(go =>
            {
                var light = go.GetComponent<Light>();
                return light != null && light.type == LightType.Directional;
            });
            return lightObj ? lightObj.transform : null;
        }

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.AfterSceneLoad)]
        public static void Initialize()
        {
            var obj = new GameObject("BetweenSceneTimeManager");
            InstanceInternal = obj.AddComponent<BetweenSceneTimeManager>();
            DontDestroyOnLoad(obj);
        }
    }
}