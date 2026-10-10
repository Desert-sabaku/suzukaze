using System;
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
        // キー入力の所作の精度は、所作ごとにこの範囲から無作為に決める
        public const double MinAccuracy = 0.6;
        public const double MaxAccuracy = 1.0;

        private readonly IGestureSink target;
        // [0, 1) の一様乱数
        private readonly Func<double> random;
        // 合成に使う受信状態。長押し中は押し始めの値のまま更新しない
        private StateView network = new StateView();
        // 最後に受信した状態。長押しを離したときに network へ反映する
        private StateView latest = new StateView();
        private double now;
        private bool fanningHeld;
        private bool ramuneHeld;
        // 開栓キーを押している間は、開栓後に手を離すのを待つ状態にする
        private bool ramuneOpenHeld;
        private double bowUntil = double.NegativeInfinity;
        // 長押しの間は精度を変えず、押し直すたびに決め直す
        private double fanningAccuracy;
        private double bowAccuracy;
        private ulong eventId;

        public KeyboardGestures(IGestureSink target, Func<double> random = null)
        {
            this.target = target;
            this.random = random ?? new Random().NextDouble;
        }

        // 長押しキーを押している間は、受信した状態と成立イベントを購読側へ渡さない
        private bool LongPressHeld => fanningHeld || ramuneHeld || ramuneOpenHeld;

        public void DeliverState(StateView state)
        {
            latest = state;
            if (LongPressHeld) return;
            network = state;
            target.DeliverState(Compose(now < bowUntil, false));
        }

        public bool TryAcceptEvent(string sessionId, Event occurrence) =>
            !LongPressHeld && target.TryAcceptEvent(sessionId, occurrence);

        public void Reset()
        {
            fanningHeld = ramuneHeld = ramuneOpenHeld = false;
            bowUntil = double.NegativeInfinity;
        }

        public void Tick(double time, KeyboardGestureInput input)
        {
            now = time;
            if (input.FanningHeld && !fanningHeld) fanningAccuracy = NextAccuracy();
            fanningHeld = input.FanningHeld;
            ramuneHeld = input.RamuneHeld;
            // 同じフレームで押して離しても、そのフレームは開栓後の状態にする
            ramuneOpenHeld = input.RamuneOpenHeld || input.RamuneOpenPressed;
            if (!LongPressHeld) network = latest;
            if (input.BowPressed)
            {
                // 礼による画面遷移は、礼でない追跡状態を見てから礼を受け付ける。
                // 礼の直前に立っている状態を挟み、キーだけでも遷移できるようにする。
                if (now >= bowUntil) target.DeliverState(Compose(false, true));
                bowUntil = now + BowSeconds;
                bowAccuracy = NextAccuracy();
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
                ActionAccuracy = NextAccuracy()
            });
        }

        private double NextAccuracy() =>
            MinAccuracy + (MaxAccuracy - MinAccuracy) * random();

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
                ActionAccuracy = gesture == ContinuousGesture.Bow ? bowAccuracy
                    : gesture != null ? fanningAccuracy
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
