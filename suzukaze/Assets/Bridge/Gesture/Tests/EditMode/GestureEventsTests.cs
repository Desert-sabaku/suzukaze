using System;
using System.Collections.Generic;
using NUnit.Framework;
using Suzukaze.Gesture.Protocol;

namespace Suzukaze.Gesture.Receiver.Tests
{
    public class GestureEventsTests
    {
        private sealed class Clock : IMonotonicClock
        {
            public double Time = 10;
            public double Now => Time;
        }

        private GestureEvents gestures;
        private ReceiverHandoff handoff;
        private Clock clock;
        private long token;

        [SetUp]
        public void SetUp()
        {
            gestures = new GestureEvents();
            handoff = new ReceiverHandoff();
            clock = new Clock();
            token = handoff.BeginConnection();
        }

        private void PublishState(ContinuousGesture gesture, ulong sequence = 1,
            string session = "s", bool fresh = true, bool tracking = true,
            string action = null, string phase = null)
        {
            var state = new State {
                Sequence = sequence, SentAt = clock.Time, ObservedAt = clock.Time,
                StaleTimeout = .5, Fresh = fresh, Tracking = tracking, Gesture = gesture
            };
            if (action != null) state.Action = action;
            if (phase != null) state.Phase = phase;
            Assert.That(handoff.Publish(token, new ReceivedMessage(new GestureEnvelope {
                Version = 1, SessionId = session, State = state
            }, clock.Time)), Is.True);
        }

        private void PublishOccurrence(OccurrenceGesture gesture = OccurrenceGesture.Ramune,
            ulong id = 1, string session = "s", double expires = 11)
        {
            Assert.That(handoff.Publish(token, new ReceivedMessage(new GestureEnvelope {
                Version = 1, SessionId = session, Event = new Event {
                    EventId = id, Gesture = gesture, OccurredAt = 10, ExpiresAt = expires
                }
            }, clock.Time)), Is.True);
        }

        private void Tick() { handoff.Tick(clock, gestures); }

        [TestCase(false)]
        [TestCase(true)]
        public void PhaseOnlyChangesNotifyAndStaleOrDisconnectClearsProgress(bool disconnect)
        {
            var changes = new List<StateView>();
            gestures.StateChanged += changes.Add;
            PublishState(ContinuousGesture.None, action: "RAMUNE", phase: "FORMING");
            Tick();
            PublishState(ContinuousGesture.None, 2, action: "RAMUNE", phase: "READY");
            Tick();
            Tick();
            Assert.That(changes.Count, Is.EqualTo(2));
            Assert.That(gestures.CurrentState.Action, Is.EqualTo("RAMUNE"));
            Assert.That(gestures.CurrentState.Phase, Is.EqualTo("READY"));
            if (disconnect) handoff.Disconnect(token);
            else clock.Time = 10.5;
            Tick();
            Assert.That(changes.Count, Is.EqualTo(3));
            Assert.That(gestures.CurrentState.Action, Is.Null);
            Assert.That(gestures.CurrentState.Phase, Is.Null);
        }

        private void AssertAck(AckStatus status, ulong id = 1)
        {
            var ack = handoff.TakeAck(token);
            Assert.That(ack, Is.Not.Null);
            Assert.That(ack.Ack.EventId, Is.EqualTo(id));
            Assert.That(ack.Ack.Status, Is.EqualTo(status));
        }

        [Test]
        public void InitialStateIsNeutralAndIdleTicksDoNotNotify()
        {
            int changes = 0;
            gestures.StateChanged += state => changes++;
            Assert.That(gestures.CurrentState, Is.Not.Null);
            Assert.That(gestures.CurrentState.SessionId, Is.Null);
            Assert.That(gestures.CurrentState.Gesture, Is.EqualTo(ContinuousGesture.None));
            Assert.That(gestures.CurrentState.Fresh, Is.False);
            Assert.That(gestures.CurrentState.Tracking, Is.False);
            Tick();
            Tick();
            Assert.That(changes, Is.Zero);
        }

        [Test]
        public void FanningRelaxingAndNoneAreDeliveredOnTick()
        {
            var changes = new List<ContinuousGesture>();
            gestures.StateChanged += state => {
                Assert.That(gestures.CurrentState, Is.SameAs(state));
                changes.Add(state.Gesture);
            };
            PublishState(ContinuousGesture.Fanning);
            Assert.That(changes, Is.Empty);
            Assert.That(gestures.CurrentState.Gesture, Is.EqualTo(ContinuousGesture.None));
            Tick();
            PublishState(ContinuousGesture.Relaxing, 2);
            Tick();
            PublishState(ContinuousGesture.None, 3);
            Tick();
            Assert.That(changes, Is.EqualTo(new[] {
                ContinuousGesture.Fanning, ContinuousGesture.Relaxing, ContinuousGesture.None
            }));
        }

        [TestCase(false)]
        [TestCase(true)]
        public void StaleExpiryOrDisconnectEmitsOneNeutralTransition(bool disconnect)
        {
            var changes = new List<StateView>();
            gestures.StateChanged += changes.Add;
            PublishState(ContinuousGesture.Fanning);
            Tick();
            if (disconnect) handoff.Disconnect(token);
            else clock.Time = 10.5;
            Tick();
            Tick();
            Assert.That(changes.Count, Is.EqualTo(2));
            Assert.That(changes[1].Gesture, Is.EqualTo(ContinuousGesture.None));
            Assert.That(changes[1].Fresh, Is.False);
            Assert.That(changes[1].Tracking, Is.False);
        }

        [Test]
        public void SessionRestartNotifiesEvenWithSameGestureAndResetsSequence()
        {
            var changes = new List<StateView>();
            gestures.StateChanged += changes.Add;
            PublishState(ContinuousGesture.Fanning, 100);
            Tick();
            PublishState(ContinuousGesture.Fanning, 1, "restarted");
            Tick();
            Assert.That(changes.Count, Is.EqualTo(2));
            Assert.That(changes[1].SessionId, Is.EqualTo("restarted"));
            Assert.That(changes[1].Sequence, Is.EqualTo(1));
            Assert.That(changes[1].Gesture, Is.EqualTo(ContinuousGesture.Fanning));
        }

        [Test]
        public void SessionRestartWithoutStateClearsPreviousGesture()
        {
            var changes = new List<StateView>();
            gestures.StateChanged += changes.Add;
            PublishState(ContinuousGesture.Relaxing);
            Tick();
            PublishOccurrence(session: "restarted");
            Tick();
            Assert.That(changes.Count, Is.EqualTo(2));
            Assert.That(gestures.CurrentState.SessionId, Is.EqualTo("restarted"));
            Assert.That(gestures.CurrentState.Gesture, Is.EqualTo(ContinuousGesture.None));
            Assert.That(gestures.CurrentState.Fresh, Is.False);
            Assert.That(gestures.CurrentState.Tracking, Is.False);
        }

        [Test]
        public void FreshnessAndTrackingChangesNotifyWithUnchangedGesture()
        {
            var changes = new List<StateView>();
            gestures.StateChanged += changes.Add;
            PublishState(ContinuousGesture.None, fresh: false, tracking: false);
            Tick();
            PublishState(ContinuousGesture.None, 2, tracking: false);
            Tick();
            PublishState(ContinuousGesture.None, 3);
            Tick();
            Assert.That(changes.Count, Is.EqualTo(3));
            Assert.That(changes[0].Fresh, Is.False);
            Assert.That(changes[1].Fresh, Is.True);
            Assert.That(changes[1].Tracking, Is.False);
            Assert.That(changes[2].Tracking, Is.True);
            foreach (var state in changes)
                Assert.That(state.Gesture, Is.EqualTo(ContinuousGesture.None));
        }

        [Test]
        public void MetadataUpdatesWithoutRepeatedStateChanged()
        {
            int changes = 0;
            gestures.StateChanged += state => changes++;
            PublishState(ContinuousGesture.Fanning);
            Tick();
            clock.Time = 10.25;
            PublishState(ContinuousGesture.Fanning, 2);
            Tick();
            Assert.That(gestures.CurrentState.Sequence, Is.EqualTo(2));
            Assert.That(gestures.CurrentState.ReceivedAt, Is.EqualTo(10.25));
            Tick();
            Assert.That(changes, Is.EqualTo(1));
        }

        [TestCase(OccurrenceGesture.Ramune)]
        [TestCase(OccurrenceGesture.Uchimizu)]
        public void PolicySuppressesDuplicateAndExpiredOccurrences(OccurrenceGesture gesture)
        {
            int calls = 0;
            gestures.Occurred += (session, occurrence) => {
                Assert.That(session, Is.EqualTo("s"));
                Assert.That(occurrence.Gesture, Is.EqualTo(gesture));
                calls++;
                return true;
            };
            PublishOccurrence(gesture);
            Assert.That(calls, Is.Zero);
            Assert.That(handoff.TakeAck(token), Is.Null);
            Tick();
            AssertAck(AckStatus.Accepted);
            PublishOccurrence(gesture);
            Tick();
            AssertAck(AckStatus.Duplicate);
            PublishOccurrence(gesture, 2);
            clock.Time = 11;
            Tick();
            AssertAck(AckStatus.Expired, 2);
            Assert.That(calls, Is.EqualTo(1));
        }

        [Test]
        public void NoSubscribersProducesIgnoredDecisionRetainedForRetry()
        {
            PublishOccurrence();
            Tick();
            AssertAck(AckStatus.Ignored);
            int calls = 0;
            gestures.Occurred += (session, occurrence) => { calls++; return true; };
            PublishOccurrence();
            Tick();
            AssertAck(AckStatus.Duplicate);
            Assert.That(calls, Is.Zero);
        }

        [Test]
        public void AcceptanceIsOrCombinedAndLaterObserversStillRun()
        {
            var calls = new List<string>();
            gestures.Occurred += (session, occurrence) => { calls.Add("before"); return false; };
            gestures.Occurred += (session, occurrence) => { calls.Add("effect"); return true; };
            gestures.Occurred += (session, occurrence) => { calls.Add("after"); return false; };
            PublishOccurrence();
            Tick();
            AssertAck(AckStatus.Accepted);
            Assert.That(calls, Is.EqualTo(new[] { "before", "effect", "after" }));
        }

        [Test]
        public void UnregisterStopsCallbacksAndLeavesObserverDecisionIgnored()
        {
            int stateCalls = 0, effectCalls = 0, observerCalls = 0;
            Action<StateView> onState = state => stateCalls++;
            Func<string, Event, bool> effect = (session, occurrence) => { effectCalls++; return true; };
            gestures.StateChanged += onState;
            gestures.Occurred += effect;
            gestures.Occurred += (session, occurrence) => { observerCalls++; return false; };
            PublishState(ContinuousGesture.Fanning);
            PublishOccurrence();
            Tick();
            AssertAck(AckStatus.Accepted);
            gestures.StateChanged -= onState;
            gestures.Occurred -= effect;
            PublishState(ContinuousGesture.Relaxing, 2);
            PublishOccurrence(id: 2);
            Tick();
            AssertAck(AckStatus.Ignored, 2);
            Assert.That(stateCalls, Is.EqualTo(1));
            Assert.That(effectCalls, Is.EqualTo(1));
            Assert.That(observerCalls, Is.EqualTo(2));
            Assert.That(gestures.CurrentState.Gesture, Is.EqualTo(ContinuousGesture.Relaxing));
        }

        [Test]
        public void EachSubscriberReceivesAnIndependentOccurrenceClone()
        {
            var original = new Event {
                EventId = 7, Gesture = OccurrenceGesture.Uchimizu, OccurredAt = 10, ExpiresAt = 11
            };
            var expected = original.Clone();
            Event first = null, second = null;
            gestures.Occurred += (session, occurrence) => {
                first = occurrence;
                occurrence.EventId = 99;
                occurrence.Gesture = OccurrenceGesture.Ramune;
                occurrence.OccurredAt = 0;
                occurrence.ExpiresAt = 100;
                return true;
            };
            gestures.Occurred += (session, occurrence) => {
                Assert.That(session, Is.EqualTo("s"));
                second = occurrence;
                return false;
            };
            Assert.That(gestures.TryAcceptEvent("s", original), Is.True);
            Assert.That(first, Is.Not.SameAs(original));
            Assert.That(second, Is.Not.SameAs(original));
            Assert.That(second, Is.Not.SameAs(first));
            Assert.That(second, Is.EqualTo(expected));
            Assert.That(original, Is.EqualTo(expected));
        }

        [Test]
        public void SubscriberExceptionPropagatesWithoutAckOrRepeatingEffectOnReconnect()
        {
            int calls = 0;
            var failure = new InvalidOperationException("effect failed");
            gestures.Occurred += (session, occurrence) => { calls++; throw failure; };
            PublishOccurrence();
            Assert.That(Assert.Throws<InvalidOperationException>(() => Tick()), Is.SameAs(failure));
            Assert.That(handoff.IsConnected(token), Is.False);
            Assert.That(handoff.TakeAck(token), Is.Null);
            token = handoff.BeginConnection();
            PublishOccurrence();
            Tick();
            AssertAck(AckStatus.Duplicate);
            Assert.That(calls, Is.EqualTo(1));
        }
    }
}
