using Cysharp.Threading.Tasks;
using Features.Common.Scripts;
using Features.Gesture_Movie.Scripts;
using Features.Result.Scripts;
using LitMotion;
using Sirenix.OdinInspector;
using Suzukaze.Gesture;
using Suzukaze.Gesture.Protocol;
using UnityEngine;

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
        [SerializeField] private float autoTransitionInterval = 60f;

        private GestureReceiverBehaviour _gestureReceiver;

        private bool ValidateAutoTransitionInterval()
        {
            return autoTransitionInterval > afterDropInterval;
        }

        private void OnEnable()
        {
            hanabi.OnDropped.AddListener(OnDropped);
            resultUI.alpha = 0f;

            if (_gestureReceiver) return;
            _gestureReceiver = GestureReceiverBehaviour.GetOrCreate();
            _gestureReceiver.Events.StateChanged += OnGestureStateChanged;
        }

        private void OnDisable()
        {
            hanabi.OnDropped.RemoveListener(OnDropped);

            if (!_gestureReceiver) return;
            _gestureReceiver.Events.StateChanged -= OnGestureStateChanged;
            _gestureReceiver = null;
        }

        private void OnGestureStateChanged(StateView state)
        {
            if (!state.Tracking) return;

            if (state.Gesture != ContinuousGesture.Bow) return;
            SceneTransitionManager.Instance.LoadSceneAsync("Title").Forget();
            _gestureReceiver.Events.StateChanged -= OnGestureStateChanged;
            _gestureReceiver = null;
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
                await UniTask.Delay(System.TimeSpan.FromSeconds(autoTransitionInterval));
                SceneTransitionManager.Instance.LoadSceneAsync("Title").Forget();
            }).Forget();
        }
    }
}