using System.Collections.Generic;
using NUnit.Framework;
using Suzukaze.Gesture.Protocol;
using GestureAction = Suzukaze.Gesture.Protocol.Action;

namespace Suzukaze.Gesture.Tests
{
    public class KeyboardGesturesTests
    {
        private GestureEvents gestures;
        private KeyboardGestures keyboard;
        private List<StateView> changes;
        private List<OccurrenceGesture> occurrences;

        private sealed class Clock : IMonotonicClock
        {
            public double Now => 10;
        }

        // 認識結果は実際の受信経路 (ReceiverHandoff) から渡す
        private void DeliverNetwork(ContinuousGesture gesture)
        {
            var handoff = new ReceiverHandoff();
            var token = handoff.BeginConnection();
            Assert.That(handoff.Publish(token, new ReceivedMessage(new GestureEnvelope {
                Version = 1, SessionId = "s", State = new State {
                    Sequence = 1, SentAt = 10, ObservedAt = 10, StaleTimeout = .5,
                    Fresh = true, Tracking = true, Gesture = gesture
                }
            }, 10)), Is.True);
            handoff.Tick(new Clock(), keyboard);
        }

        [SetUp]
        public void SetUp()
        {
            gestures = new GestureEvents();
            keyboard = new KeyboardGestures(gestures);
            changes = new List<StateView>();
            occurrences = new List<OccurrenceGesture>();
            gestures.StateChanged += changes.Add;
            gestures.Occurred += (session, occurrence) => {
                Assert.That(session, Is.EqualTo(KeyboardGestures.SessionId));
                Assert.That(occurrence.ActionAccuracy, Is.EqualTo(KeyboardGestures.Accuracy));
                occurrences.Add(occurrence.Gesture);
                return true;
            };
        }

        [Test]
        public void NoKeysPassesNetworkStateThrough()
        {
            DeliverNetwork(ContinuousGesture.Relaxing);
            var network = gestures.CurrentState;
            keyboard.Tick(1, default);
            Assert.That(gestures.CurrentState, Is.SameAs(network));
            Assert.That(network.Gesture, Is.EqualTo(ContinuousGesture.Relaxing));
            Assert.That(changes, Has.Count.EqualTo(1));
        }

        [Test]
        public void HoldingFanningKeyFansUntilReleased()
        {
            keyboard.Tick(1, new KeyboardGestureInput { FanningHeld = true });
            var state = gestures.CurrentState;
            Assert.That(state.Fresh && state.Tracking, Is.True);
            Assert.That(state.Gesture, Is.EqualTo(ContinuousGesture.Fanning));
            Assert.That(state.Action, Is.EqualTo(GestureAction.Fanning));
            Assert.That(state.Phase, Is.EqualTo(Phase.Active));
            Assert.That(state.ActionAccuracy, Is.EqualTo(KeyboardGestures.Accuracy));

            keyboard.Tick(2, new KeyboardGestureInput { FanningHeld = true });
            Assert.That(changes, Has.Count.EqualTo(1));
            keyboard.Tick(3, default);
            Assert.That(gestures.CurrentState.Gesture, Is.EqualTo(ContinuousGesture.None));
            Assert.That(gestures.CurrentState.Tracking, Is.False);
        }

        [Test]
        public void RamuneWaitsForReleaseWhileOpenKeyIsHeldAndCanOpenAgain()
        {
            keyboard.Tick(1, new KeyboardGestureInput { RamuneHeld = true });
            Assert.That(gestures.CurrentState.Action, Is.EqualTo(GestureAction.Ramune));
            Assert.That(gestures.CurrentState.Phase, Is.EqualTo(Phase.Ready));
            Assert.That(occurrences, Is.Empty);

            keyboard.Tick(2, new KeyboardGestureInput {
                RamuneHeld = true, RamuneOpenPressed = true, RamuneOpenHeld = true
            });
            Assert.That(gestures.CurrentState.Phase, Is.EqualTo(Phase.WaitRelease));
            Assert.That(occurrences, Is.EqualTo(new[] { OccurrenceGesture.Ramune }));

            keyboard.Tick(10, new KeyboardGestureInput { RamuneHeld = true, RamuneOpenHeld = true });
            Assert.That(gestures.CurrentState.Phase, Is.EqualTo(Phase.WaitRelease));
            Assert.That(occurrences, Has.Count.EqualTo(1));

            keyboard.Tick(11, new KeyboardGestureInput { RamuneHeld = true });
            Assert.That(gestures.CurrentState.Phase, Is.EqualTo(Phase.Ready));

            keyboard.Tick(12, new KeyboardGestureInput {
                RamuneHeld = true, RamuneOpenPressed = true, RamuneOpenHeld = true
            });
            Assert.That(gestures.CurrentState.Phase, Is.EqualTo(Phase.WaitRelease));
            Assert.That(occurrences, Has.Count.EqualTo(2));

            keyboard.Tick(13, default);
            Assert.That(gestures.CurrentState.Action, Is.Null);
        }

        [Test]
        public void OpeningWithoutReadyWaitsOnlyWhileOpenKeyIsHeld()
        {
            keyboard.Tick(1, new KeyboardGestureInput { RamuneOpenPressed = true, RamuneOpenHeld = true });
            Assert.That(gestures.CurrentState.Phase, Is.EqualTo(Phase.WaitRelease));
            Assert.That(occurrences, Is.EqualTo(new[] { OccurrenceGesture.Ramune }));
            keyboard.Tick(2, default);
            Assert.That(gestures.CurrentState.Action, Is.Null);
        }

        [Test]
        public void TapWithinOneFrameStillOpens()
        {
            keyboard.Tick(1, new KeyboardGestureInput { RamuneHeld = true, RamuneOpenPressed = true });
            Assert.That(gestures.CurrentState.Phase, Is.EqualTo(Phase.WaitRelease));
            Assert.That(occurrences, Has.Count.EqualTo(1));
            keyboard.Tick(2, new KeyboardGestureInput { RamuneHeld = true });
            Assert.That(gestures.CurrentState.Phase, Is.EqualTo(Phase.Ready));
        }

        [Test]
        public void UchimizuKeyOccursOnce()
        {
            keyboard.Tick(1, new KeyboardGestureInput { UchimizuPressed = true });
            keyboard.Tick(2, default);
            Assert.That(occurrences, Is.EqualTo(new[] { OccurrenceGesture.Uchimizu }));
            Assert.That(changes, Is.Empty);
        }

        [Test]
        public void BowIsPrecededByTrackedStateAndEnds()
        {
            keyboard.Tick(1, new KeyboardGestureInput { BowPressed = true });
            Assert.That(changes, Has.Count.EqualTo(2));
            Assert.That(changes[0].Tracking, Is.True);
            Assert.That(changes[0].Gesture, Is.EqualTo(ContinuousGesture.None));
            Assert.That(changes[1].Gesture, Is.EqualTo(ContinuousGesture.Bow));
            Assert.That(changes[1].Action, Is.EqualTo(GestureAction.Bow));
            Assert.That(changes[1].Phase, Is.EqualTo(Phase.Hold));

            keyboard.Tick(1 + KeyboardGestures.BowSeconds, default);
            Assert.That(gestures.CurrentState.Gesture, Is.EqualTo(ContinuousGesture.None));
        }

        [Test]
        public void NetworkStateDuringHeldKeyKeepsKeyboardGesture()
        {
            keyboard.Tick(1, new KeyboardGestureInput { FanningHeld = true });
            DeliverNetwork(ContinuousGesture.Relaxing);
            Assert.That(gestures.CurrentState.Gesture, Is.EqualTo(ContinuousGesture.Fanning));
        }

        [Test]
        public void ResetReleasesHeldKeys()
        {
            keyboard.Tick(1, new KeyboardGestureInput { FanningHeld = true, RamuneHeld = true });
            keyboard.Reset();
            keyboard.DeliverState(new StateView());
            Assert.That(gestures.CurrentState.Gesture, Is.EqualTo(ContinuousGesture.None));
            Assert.That(gestures.CurrentState.Action, Is.Null);
        }
    }
}
