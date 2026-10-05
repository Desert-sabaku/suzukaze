using System;
using Suzukaze.Gesture.Protocol;

namespace Suzukaze.Gesture.Receiver
{
    // One main-thread API for every scene effect. DeliveryPolicy owns expiry,
    // deduplication and ACKs; this class only publishes the resulting gestures.
    public sealed class GestureEvents : IGestureSink
    {
        public StateView CurrentState { get; private set; } = new StateView();
        public event Action<StateView> StateChanged;

        // Every subscriber runs. Return true only when an effect adopts the event;
        // observers and handlers for other gesture kinds return false.
        public event Func<string, Event, bool> Occurred;

        public void DeliverState(StateView state)
        {
            var previous = CurrentState;
            CurrentState = state;
            if (previous.SessionId != state.SessionId || previous.Gesture != state.Gesture
                || previous.Action != state.Action || previous.Phase != state.Phase
                || previous.BoothPresent != state.BoothPresent
                || previous.Fresh != state.Fresh || previous.Tracking != state.Tracking)
                StateChanged?.Invoke(state);
        }

        public bool TryAcceptEvent(string sessionId, Event occurrence)
        {
            var handlers = Occurred;
            if (handlers == null) return false;
            bool accepted = false;
            foreach (Func<string, Event, bool> handler in handlers.GetInvocationList())
                accepted |= handler(sessionId, occurrence.Clone());
            return accepted;
        }
    }
}
