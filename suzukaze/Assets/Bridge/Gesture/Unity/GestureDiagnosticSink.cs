using Suzukaze.Gesture.Protocol;
using UnityEngine;
using Event = Suzukaze.Gesture.Protocol.Event;

namespace Suzukaze.Gesture.Receiver
{
    // Explicit opt-in diagnostic sink. No scene/device mappings are implied.
    public sealed class GestureDiagnosticSink : MonoBehaviour
    {
        [SerializeField] private bool acceptEvents;
        private GestureReceiverBehaviour receiver;
        private readonly StateView inactiveState = new StateView();
        public StateView LatestState => receiver != null ? receiver.Events.CurrentState : inactiveState;
        public int EventCount { get; private set; }

        private void OnEnable()
        {
            receiver = GestureReceiverBehaviour.GetOrCreate();
            receiver.Events.Occurred += TryAcceptEvent;
        }

        private void OnDisable()
        {
            if (receiver != null)
            {
                receiver.Events.Occurred -= TryAcceptEvent;
            }
            receiver = null;
        }
        public bool TryAcceptEvent(string sessionId, Event occurrence)
        {
            EventCount++;
            Debug.Log($"Gesture {sessionId}/{occurrence.EventId}: {occurrence.Gesture}, accepted={acceptEvents}", this);
            return acceptEvents;
        }
    }
}
