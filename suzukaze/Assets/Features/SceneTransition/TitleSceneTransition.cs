using Cysharp.Threading.Tasks;
using Suzukaze.Gesture;
using Suzukaze.Gesture.Protocol;
using UnityEngine;
using UnityEngine.InputSystem;

namespace Features.SceneTransition
{
    public class TitleSceneTransition : MonoBehaviour
    {
        private GestureReceiverBehaviour _gestureReceiver;
        private GameInputs _input;

        private void Start()
        {
            _input = new GameInputs();
            _input.Debug.Enable();

            _input.Debug.NextStep.performed += OnTransition;
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

        private static void OnGestureStateChanged(StateView state)
        {
            if (!state.Tracking) return;

            if (state.Gesture == ContinuousGesture.Bow) OnTransition(default);
        }

        private static void OnTransition(InputAction.CallbackContext ctx)
        {
            SceneTransitionManager.Instance.LoadSceneAsync("Sea").Forget();
        }
    }
}