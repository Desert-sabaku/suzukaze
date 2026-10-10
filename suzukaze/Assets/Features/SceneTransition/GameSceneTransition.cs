using System;
using Cysharp.Threading.Tasks;
using Features.Common.Scripts;
using Features.Result.Scripts;
using Features.SandTimer.Scripts;
using Sirenix.OdinInspector;
using Suzukaze.Gesture;
using Unity.Mathematics;
using UnityEngine;
using UnityEngine.InputSystem;
using UnityEngine.SceneManagement;
using GestureEvent = Suzukaze.Gesture.Protocol.Event;

namespace Features.SceneTransition
{
    /// <summary>
    ///     ゲームのシーンを一定時間経ったら切り替える．
    ///     プレイ中の所作の正確性を集計し，プレイ全体の正確性としてリザルトへ渡す
    /// </summary>
    public class GameSceneTransition : MonoBehaviour
    {
        [ShowInInspector] private float _elapsedTime;

        private GameSettings _gameSettings;
        private SandTimerController _sandTimerController;
        private GameInputs _input;
        private GestureReceiverBehaviour _gestureReceiver;
        private readonly AccuracyTally _accuracy = new();
        private static bool _isCycling;

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.SubsystemRegistration)]
        private static void ResetSceneCycle()
        {
            _isCycling = false;
        }

        private void Start()
        {
            UniTask.Create(async () => _gameSettings = await GameSettings.GetInstanceAsync());

            _sandTimerController = GetComponentInChildren<SandTimerController>();
        }

        private void OnEnable()
        {
            _input ??= new GameInputs();
            _input.Debug.Enable();
            _input.Debug.NextStep.performed += OnNextStep;

            _gestureReceiver = GestureReceiverBehaviour.GetOrCreate();
            _gestureReceiver.Events.Occurred += OnGestureOccurred;
        }

        private void OnDisable()
        {
            _input.Debug.NextStep.performed -= OnNextStep;
            _input.Debug.Disable();

            if (!_gestureReceiver) return;
            _gestureReceiver.Events.Occurred -= OnGestureOccurred;
            _gestureReceiver = null;
        }
        
        private void OnNextStep(InputAction.CallbackContext context)
        {
            if (_isCycling) return;
            CycleSceneAsync().Forget();
        }

        private async UniTask CycleSceneAsync()
        {
            _isCycling = true;
            try
            {
                _gameSettings ??= await GameSettings.GetInstanceAsync();
                var scenes = _gameSettings.gameScenes;
                if (scenes == null || scenes.Length == 0) return;
                var current = Array.IndexOf(scenes, SceneManager.GetActiveScene().name);
                var next = scenes[(current + 1) % scenes.Length];
                if (string.IsNullOrEmpty(next) || !Application.CanStreamedLevelBeLoaded(next))
                {
                    Debug.LogError($"Cannot cycle to game scene: {next}");
                    return;
                }

                await SceneTransitionManager.Instance.LoadSceneAsync(next);
            }
            finally
            {
                _isCycling = false;
            }
        }

        // 正確性を集計するだけの観測者なので，演出の採用には関与しない
        private bool OnGestureOccurred(string sessionId, GestureEvent occurrence)
        {
            if (_gameSettings) _accuracy.AddOccurrence(occurrence);
            return false;
        }

        private void Update()
        {
            if (!_gameSettings) return;

            if (_gestureReceiver)
            {
                var state = _gestureReceiver.Events.CurrentState;
                _accuracy.AddState(state.Gesture, state.ActionAccuracy, Time.deltaTime);
            }

            _elapsedTime += Time.deltaTime;
            _sandTimerController.Progress = math.unlerp(0f, _gameSettings.gameTimeLimit, _elapsedTime);
            // シーン遷移の重複を防ぐ。遷移中も時間の更新は続ける。
            if (_isCycling) return;
            var forceEnd = Keyboard.current != null && Keyboard.current.nKey.wasPressedThisFrame;
            if (!forceEnd && _elapsedTime < _gameSettings.gameTimeLimit) return;

            // 時間切れ、または N キーで結果シーンへ進む。評価できた所作がなければ 0。
            PlayScore.Submit((float)(_accuracy.Overall ?? 0));
            SceneTransitionManager.Instance.LoadSceneAsync(_gameSettings.resultScene).Forget();
            enabled = false;
        }
    }
}
