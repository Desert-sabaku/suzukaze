using System.Linq;
using Cysharp.Threading.Tasks;
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
        private float _currentTime;
        private Transform _directionalLight;
        private GameSettings _gameSettings;
        private bool _isActive = true;

        /// <summary>
        ///     現在の時刻 (0〜24)。太陽 (Directional Light) が最も高くなる角度を 12 時とする
        /// </summary>
        public float CurrentHour
        {
            get
            {
                if (!_gameSettings) return 12f;
                var angle = _currentTime * 360f / 24f - NoonAngle(_gameSettings.lightAxis);
                return Mathf.Repeat(12f + angle * 24f / 360f, 24f);
            }
        }

        private void Start()
        {
            var currentScene = SceneManager.GetActiveScene();
            _directionalLight = FindDirectionalLight(currentScene);
            Debug.Assert(_directionalLight != null, "Directional light not found in the scene.");

            SceneManager.activeSceneChanged += OnActiveSceneChanged;
            UniTask.Create(async () =>
            {
                _gameSettings = await GameSettings.GetInstanceAsync();
                _isActive = _gameSettings.ignoreTimeManageScenes.All(ignoreScene => ignoreScene != currentScene.name);
            }).Forget();
        }

        private void Update()
        {
            if (!_gameSettings || !_isActive) return;

            _currentTime += Time.deltaTime * _gameSettings.timeScale;
            _directionalLight.rotation = Quaternion.AngleAxis(
                _currentTime * 360f / 24f,
                _gameSettings.lightAxis
            );
        }

        private void OnDrawGizmos()
        {
            if (!_gameSettings || !_isActive) return;

            Gizmos.color = Color.yellow;
            Gizmos.DrawLine(Vector3.zero, _gameSettings.lightAxis.normalized * 5);
            // 回転する軸を描画
            Gizmos.DrawLine(Vector3.zero,
                Quaternion.AngleAxis(_currentTime * 360f / 24f, _gameSettings.lightAxis) * Vector3.forward * 5);
        }

        private void OnActiveSceneChanged(
            UnityEngine.SceneManagement.Scene oldScene,
            UnityEngine.SceneManagement.Scene newScene
        )
        {
            _isActive = _gameSettings.ignoreTimeManageScenes.All(ignoreScene => ignoreScene != newScene.name);
            _directionalLight = FindDirectionalLight(newScene);
            Debug.Assert(_directionalLight != null, "Directional light not found in the new scene.");
        }

        /// <summary>
        ///     ライトは AngleAxis(angle, axis) * forward を向くので、その y 成分は
        ///     -a.x * sin(angle) + a.y * a.z * (1 - cos(angle)) になる。これが最も小さく
        ///     (ライトが最も下向きに) なる角度を正午とする
        /// </summary>
        private static float NoonAngle(Vector3 axis)
        {
            var a = axis.normalized;
            return Mathf.Atan2(a.x, a.y * a.z) * Mathf.Rad2Deg;
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