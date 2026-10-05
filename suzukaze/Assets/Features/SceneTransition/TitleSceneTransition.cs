using Cysharp.Threading.Tasks;
using Suzukaze.Gesture.Receiver;
using UnityEngine;
using UnityEngine.InputSystem;
using Event = Suzukaze.Gesture.Protocol.Event;

namespace Features.SceneTransition
{
    public class TitleSceneTransition : MonoBehaviour
    {
        private GameInputs _input;
        private GestureReceiverBehaviour _gestureReceiver;

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
            _gestureReceiver.Events.Occurred += OnGestureOccurred;
        }

        private void OnDisable()
        {
            if (_gestureReceiver)
                _gestureReceiver.Events.Occurred -= OnGestureOccurred;
            _gestureReceiver = null;
        }

        private static bool OnGestureOccurred(string sessionId, Event events)
        {
            OnTransition(default);
            return true;
        }

        private void OnDestroy()
        {
            _input.Debug.NextStep.performed -= OnTransition;
            _input.Disable();
            _input.Dispose();
        }

        private static void OnTransition(InputAction.CallbackContext ctx)
        {
            SceneTransitionManager.Instance.LoadSceneAsync("Sea").Forget();
        }
    }
}