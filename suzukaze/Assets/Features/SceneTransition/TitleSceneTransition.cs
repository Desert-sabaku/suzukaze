using Cysharp.Threading.Tasks;
using Sirenix.OdinInspector;
using Suzukaze.Gesture;
using Suzukaze.Gesture.Protocol;
using UnityEngine;
using UnityEngine.InputSystem;

namespace Features.SceneTransition
{
    public class TitleSceneTransition : MonoBehaviour
    {
        [SerializeField] private CanvasGroup gestureCanvasGroup;
        [SerializeField] private float gestureDisplayDuration = 2f;

        private GestureReceiverBehaviour _gestureReceiver;
        private GameInputs _input;

        [ShowInInspector] private bool _isShowingGesture;

        private void Start()
        {
            _input = new GameInputs();
            _input.Debug.Enable();

            gestureCanvasGroup.alpha = 0f;
            _input.Debug.NextStep.performed += OnTransition;
        }

        private void Update()
        {
            gestureCanvasGroup.alpha = Mathf.MoveTowards(
                gestureCanvasGroup.alpha, _isShowingGesture ? 1f : 0f,
                Time.deltaTime * gestureDisplayDuration
            );
        }

        private void OnEnable()
        {
            if (_gestureReceiver) return;
            _gestureReceiver = GestureReceiverBehaviour.GetOrCreate();
            _gestureReceiver.Events.StateChanged += OnGestureStateChanged;
        }

        private void OnDisable()
        {
            if (_gestureReceiver)
                _gestureReceiver.Events.StateChanged -= OnGestureStateChanged;
            _gestureReceiver = null;
        }

        private void OnDestroy()
        {
            _input.Debug.NextStep.performed -= OnTransition;
            _input.Disable();
            _input.Dispose();
        }

        private void OnGestureStateChanged(StateView state)
        {
            _isShowingGesture = state.BoothPresent;
            Debug.Log(state.BoothPresent ? "Gesture detected" : "Gesture lost");

            if (state.Tracking && state.Gesture == ContinuousGesture.Bow)
            {
                OnTransition(default);
                _gestureReceiver.Events.StateChanged -= OnGestureStateChanged;
                _gestureReceiver = null;
            }
        }

        private static void OnTransition(InputAction.CallbackContext ctx)
        {
            SceneTransitionManager.Instance.LoadSceneAsync("Sea").Forget();
        }
    }
}
