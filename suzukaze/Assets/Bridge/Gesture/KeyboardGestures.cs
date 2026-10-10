using Suzukaze.Gesture.Protocol;
using Event = Suzukaze.Gesture.Protocol.Event;
using GestureAction = Suzukaze.Gesture.Protocol.Action;

namespace Suzukaze.Gesture
{
    // 1フレーム分のキー入力。Held は押している間、Pressed は押したフレームだけ true。
    public struct KeyboardGestureInput
    {
        public bool UchimizuPressed;
        public bool RamuneHeld;
        public bool RamuneOpenPressed;
        public bool RamuneOpenHeld;
        public bool FanningHeld;
        public bool BowPressed;
    }

    // カメラがなくても演出を確かめられるよう、キー入力を受信した所作に重ねる。
    // 受信した状態と GestureEvents の間に入り、購読側からは認識結果と区別しない。
    public sealed class KeyboardGestures : IGestureSink
    {
        public const string SessionId = "keyboard";
        public const double BowSeconds = 1.0;
        public const double EventLifetimeSeconds = 1.0;
        // キー入力の所作は常に正確に行ったものとして採点する
        public const double Accuracy = 1.0;

        private readonly IGestureSink target;
        private StateView network = new StateView();
        private double now;
        private bool fanningHeld;
        private bool ramuneHeld;
        // 開栓キーを押している間は、開栓後に手を離すのを待つ状態にする
        private bool ramuneOpenHeld;
        private double bowUntil = double.NegativeInfinity;
        private ulong eventId;

        public KeyboardGestures(IGestureSink target) { this.target = target; }

        public void DeliverState(StateView state)
        {
            network = state;
            target.DeliverState(Compose(now < bowUntil, false));
        }

        public bool TryAcceptEvent(string sessionId, Event occurrence) =>
            target.TryAcceptEvent(sessionId, occurrence);

        public void Reset()
        {
            fanningHeld = ramuneHeld = ramuneOpenHeld = false;
            bowUntil = double.NegativeInfinity;
        }

        public void Tick(double time, KeyboardGestureInput input)
        {
            now = time;
            fanningHeld = input.FanningHeld;
            ramuneHeld = input.RamuneHeld;
            // 同じフレームで押して離しても、そのフレームは開栓後の状態にする
            ramuneOpenHeld = input.RamuneOpenHeld || input.RamuneOpenPressed;
            if (input.BowPressed)
            {
                // 礼による画面遷移は、礼でない追跡状態を見てから礼を受け付ける。
                // 礼の直前に立っている状態を挟み、キーだけでも遷移できるようにする。
                if (now >= bowUntil) target.DeliverState(Compose(false, true));
                bowUntil = now + BowSeconds;
            }
            target.DeliverState(Compose(now < bowUntil, false));
            if (input.RamuneOpenPressed) Occur(OccurrenceGesture.Ramune);
            if (input.UchimizuPressed) Occur(OccurrenceGesture.Uchimizu);
        }

        private void Occur(OccurrenceGesture gesture)
        {
            target.TryAcceptEvent(SessionId, new Event {
                EventId = ++eventId, Gesture = gesture,
                OccurredAt = now, ExpiresAt = now + EventLifetimeSeconds,
                ActionAccuracy = Accuracy
            });
        }

        private StateView Compose(bool bow, bool tracked)
        {
            var ramune = ramuneHeld || ramuneOpenHeld;
            ContinuousGesture? gesture = bow ? ContinuousGesture.Bow
                : fanningHeld ? ContinuousGesture.Fanning : null;
            if (gesture == null && !ramune && !tracked) return network;

            var observed = network.Fresh && network.Tracking;
            var state = new StateView {
                SessionId = network.SessionId,
                Sequence = network.Sequence,
                ReceivedAt = network.ReceivedAt,
                Fresh = true,
                Tracking = true,
                BoothPresent = network.BoothPresent,
                Gesture = gesture ?? (observed ? network.Gesture : ContinuousGesture.None),
                ActionAccuracy = gesture != null ? Accuracy
                    : observed ? network.ActionAccuracy : null
            };
            if (ramune)
            {
                state.Action = GestureAction.Ramune;
                state.Phase = ramuneOpenHeld ? Phase.WaitRelease : Phase.Ready;
            }
            else if (gesture == ContinuousGesture.Bow)
            {
                state.Action = GestureAction.Bow;
                state.Phase = Phase.Hold;
            }
            else if (gesture == ContinuousGesture.Fanning)
            {
                state.Action = GestureAction.Fanning;
                state.Phase = Phase.Active;
            }
            else if (observed)
            {
                state.Action = network.Action;
                state.Phase = network.Phase;
            }
            return state;
        }
    }
}
