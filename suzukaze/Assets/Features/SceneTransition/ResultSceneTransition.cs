using Features.Result.Scripts;
using LitMotion;
using Suzukaze.Gesture;
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

        private GestureReceiverBehaviour _gestureReceiver;

        private void OnEnable()
        {
            hanabi.OnDropped.AddListener(OnDropped);

            _gestureReceiver = GestureReceiverBehaviour.GetOrCreate();
            // _gestureReceiver.Events
        }

        private void OnDisable()
        {
            hanabi.OnDropped.RemoveListener(OnDropped);
        }

        private void OnDropped()
        {
            LSequence.Create()
                .AppendInterval(afterDropInterval)
                .Append(
                    LMotion.Create(0f, 1f, fadeDuration)
                        .Bind(v => resultUI.alpha = v)
                )
                .Run();
        }
    }
}