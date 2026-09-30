using Suzukaze.Gesture.Protocol;
using UnityEngine;
using Event = Suzukaze.Gesture.Protocol.Event;

namespace Suzukaze.Gesture.Delivery
{
    // Explicit opt-in diagnostic sink. No scene/device mappings are implied.
    public sealed class GestureDiagnosticSink : MonoBehaviour, IGestureSink
    {
        [SerializeField] private bool acceptEvents;
        public StateView LatestState { get; private set; }
        public int EventCount { get; private set; }
        public void DeliverState(StateView state) { LatestState = state; }
        public bool TryAcceptEvent(string sessionId, Event occurrence)
        {
            EventCount++;
            Debug.Log($"Gesture {sessionId}/{occurrence.EventId}: {occurrence.Gesture}, accepted={acceptEvents}", this);
            return acceptEvents;
        }
    }
}
