using System;
using Cysharp.Threading.Tasks;
using Features.Common.Scripts;
using Features.Gesture_Movie.Scripts;
using Features.Result.Scripts;
using LitMotion;
using Sirenix.OdinInspector;
using Suzukaze.Gesture;
using Suzukaze.Gesture.Protocol;
using UnityEngine;
using UnityEngine.InputSystem;

namespace Features.SceneTransition
{
    /// <summary>
    ///     リザルトシーンで線香花火に応じてUIの表示制御と所作によるシーン遷移を行うクラス
    /// </summary>
    public class ResultSceneTransition : MonoBehaviour
    {
        [SerializeField] private CanvasGroup resultUI;
        [SerializeField] private SenkoHanabiController hanabi;
        [SerializeField] private float afterDropInterval = 3f;
        [SerializeField] private float fadeDuration = 0.5f;

        [ValidateInput(nameof(ValidateAutoTransitionInterval), "自動遷移のインターバルはドロップ後のインターバルより長くする必要があります")]
        [SerializeField]
        private float autoTransitionInterval = 60f;

        private GestureReceiverBehaviour _gestureReceiver;
        private GameInputs _input;

        /// <summary>
        ///     前のシーンから礼が継続している間は遷移しないよう、礼以外の姿勢を一度確認してから礼を受け付ける
        /// </summary>
        private bool _isBowReleased;

        private void OnEnable()
        {
            hanabi.OnDropped.AddListener(OnDropped);
            resultUI.alpha = 0f;

            _input ??= new GameInputs();
            _input.Debug.Enable();
            _input.Debug.NextStep.performed += OnDebugNextStep;

            if (_gestureReceiver) return;
            _gestureReceiver = GestureReceiverBehaviour.GetOrCreate();
            _isBowReleased = false;
            UpdateBowReleased(_gestureReceiver.Events.CurrentState);
            _gestureReceiver.Events.StateChanged += OnGestureStateChanged;
        }

        private void OnDisable()
        {
            hanabi.OnDropped.RemoveListener(OnDropped);
            
            _input.Debug.NextStep.performed -= OnDebugNextStep;

            if (!_gestureReceiver) return;
            _gestureReceiver.Events.StateChanged -= OnGestureStateChanged;
            _gestureReceiver = null;
        }

        private void OnDestroy()
        {
            _input.Debug.Disable();
            _input.Dispose();
        }

        private bool ValidateAutoTransitionInterval()
        {
            return autoTransitionInterval > afterDropInterval;
        }

        private void Update()
        {
            if (Keyboard.current == null || !Keyboard.current.zKey.wasPressedThisFrame) return;
            OnDebugNextStep(default);
            enabled = false;
        }

        private void OnDebugNextStep(InputAction.CallbackContext ctx)
        {
            SceneTransitionManager.Instance.LoadSceneAsync("Title").Forget();
        }

        private void OnGestureStateChanged(StateView state)
        {
            if (!state.Tracking) return;

            UpdateBowReleased(state);
            if (!_isBowReleased || state.Gesture != ContinuousGesture.Bow) return;
            SceneTransitionManager.Instance.LoadSceneAsync("Title").Forget();
            _gestureReceiver.Events.StateChanged -= OnGestureStateChanged;
            _gestureReceiver = null;
        }

        private void UpdateBowReleased(StateView state)
        {
            if (state.Tracking && state.Gesture != ContinuousGesture.Bow) _isBowReleased = true;
        }

        private void OnDropped()
        {
            var gestureMovie = FindAnyObjectByType<GestureMoviePlayer>();
            if (!gestureMovie) return;

            LSequence.Create()
                .AppendInterval(afterDropInterval)
                .Append(
                    LMotion.Create(0f, 1f, fadeDuration)
                        .WithOnComplete(() => gestureMovie.SetAnimation(Gestures.Rei))
                        .Bind(v => resultUI.alpha = v)
                )
                .Run();
            UniTask.Create(async () =>
            {
                await UniTask.Delay(TimeSpan.FromSeconds(autoTransitionInterval));
                SceneTransitionManager.Instance.LoadSceneAsync("Title").Forget();
            }).Forget();
        }
    }
}
