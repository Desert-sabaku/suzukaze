using Cysharp.Threading.Tasks;
using Features.Common.Scripts;
using Features.SandTimer.Scripts;
using Sirenix.OdinInspector;
using Unity.Mathematics;
using UnityEngine;

namespace Features.SceneTransition
{
    /// <summary>
    ///     ゲームのシーンを一定時間経ったら切り替える
    /// </summary>
    public class GameSceneTransition : MonoBehaviour
    {
        [ShowInInspector] private float _elapsedTime;

        private GameSettings _gameSettings;
        private SandTimerController _sandTimerController;

        private void Start()
        {
            UniTask.Create(async () => { _gameSettings = await GameSettings.GetInstanceAsync(); });

            _sandTimerController = GetComponentInChildren<SandTimerController>();
        }

        private void Update()
        {
            if (!_gameSettings) return;

            _elapsedTime += Time.deltaTime;
            _sandTimerController.Progress = math.unlerp(0f, _gameSettings.gameTimeLimit, _elapsedTime);
            if (_elapsedTime < _gameSettings.gameTimeLimit) return;

            // ゲームの時間が経過したら結果シーンに遷移する
            SceneTransitionManager.Instance.LoadSceneAsync(_gameSettings.resultScene).Forget();
            enabled = false;
        }
    }
}