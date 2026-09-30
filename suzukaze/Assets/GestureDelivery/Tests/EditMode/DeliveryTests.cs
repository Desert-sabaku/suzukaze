using System;
using NUnit.Framework;
using Suzukaze.Gesture.Protocol;

namespace Suzukaze.Gesture.Delivery.Tests
{
    public sealed class TestClock : IMonotonicClock
    { public double Time = 10; public double Now => Time; }

    public sealed class TestSink : IGestureSink
    {
        public bool Accept = true;
        public bool Throw;
        public int Calls;
        public StateView State;
        public void DeliverState(StateView state) { State = state; }
        public bool TryAcceptEvent(string session, Event occurrence)
        { Calls++; if (Throw) throw new Exception("scene failed"); return Accept; }
    }

    public class DeliveryTests
    {
        public static ReceivedMessage Occurrence(ulong id = 1, string session = "s", double expires = 11)
        {
            return new ReceivedMessage(new GestureEnvelope {
                Version = 1, SessionId = session, Event = new Event {
                    EventId = id, Gesture = OccurrenceGesture.Ramune, OccurredAt = 10, ExpiresAt = expires
                }
            }, 10);
        }

        public static ReceivedMessage State(ulong sequence = 1, double arrival = 10)
        {
            return new ReceivedMessage(new GestureEnvelope {
                Version = 1, SessionId = "s", State = new State {
                    Sequence = sequence, SentAt = 10, ObservedAt = 10, StaleTimeout = .5,
                    Fresh = true, Tracking = true, Gesture = ContinuousGesture.Fanning
                }
            }, arrival);
        }

        [TestCase(true, AckStatus.Accepted)]
        [TestCase(false, AckStatus.Ignored)]
        public void DecisionsSurviveReconnect(bool accept, AckStatus expected)
        {
            var core = new ReceiverHandoff(); var clock = new TestClock();
            var sink = new TestSink { Accept = accept };
            long old = core.BeginConnection();
            core.Publish(old, Occurrence());
            Assert.That(core.TakeAck(old), Is.Null, "Receipt is not adoption");
            core.Tick(clock, sink);
            Assert.That(core.TakeAck(old).Ack.Status, Is.EqualTo(expected));
            core.Disconnect(old);
            long next = core.BeginConnection();
            core.Publish(next, Occurrence()); core.Tick(clock, sink);
            Assert.That(core.TakeAck(next).Ack.Status, Is.EqualTo(AckStatus.Duplicate));
            Assert.That(sink.Calls, Is.EqualTo(1));
            Assert.That(core.Publish(old, Occurrence(2)), Is.False);
            core.Disconnect(old);
            Assert.That(core.IsConnected(next), Is.True);
            core.Publish(next, Occurrence(1, "new")); core.Tick(clock, sink);
            Assert.That(core.TakeAck(next).Ack.Status, Is.EqualTo(expected));
            Assert.That(sink.Calls, Is.EqualTo(2));
        }

        [Test]
        public void MissingSinkIgnoresAndExpiryIsCheckedAtAdoption()
        {
            var core = new ReceiverHandoff(); var clock = new TestClock();
            long token = core.BeginConnection();
            core.Publish(token, Occurrence()); core.Tick(clock, null);
            Assert.That(core.TakeAck(token).Ack.Status, Is.EqualTo(AckStatus.Ignored));
            core.Publish(token, Occurrence(2)); clock.Time = 11;
            var sink = new TestSink(); core.Tick(clock, sink);
            Assert.That(core.TakeAck(token).Ack.Status, Is.EqualTo(AckStatus.Expired));
            Assert.That(sink.Calls, Is.Zero);
        }

        [Test]
        public void LatestStatePreservesArrivalAndAgesWithoutMessages()
        {
            var core = new ReceiverHandoff(); var clock = new TestClock(); var sink = new TestSink();
            long token = core.BeginConnection();
            core.Publish(token, State(2, 10)); core.Publish(token, State(1, 10.1));
            clock.Time = 10.4; core.Tick(clock, sink);
            Assert.That(sink.State.Sequence, Is.EqualTo(2));
            Assert.That(sink.State.ReceivedAt, Is.EqualTo(10));
            Assert.That(sink.State.Gesture, Is.EqualTo(ContinuousGesture.Fanning));
            clock.Time = 10.5; core.Tick(clock, sink);
            Assert.That(sink.State.Gesture, Is.EqualTo(ContinuousGesture.None));
            core.Disconnect(token); core.Tick(clock, sink);
            Assert.That(sink.State.Fresh, Is.False);
        }

        [Test]
        public void QueuedStateDoesNotGetFreshTimestampInUpdate()
        {
            var core = new ReceiverHandoff(); var clock = new TestClock { Time = 11 };
            var sink = new TestSink(); long token = core.BeginConnection();
            core.Publish(token, State()); core.Tick(clock, sink);
            Assert.That(sink.State.Fresh, Is.False);
            Assert.That(sink.State.ReceivedAt, Is.EqualTo(10));
        }

        [Test]
        public void PendingOverflowDisconnectsWithoutAdoptionOrAck()
        {
            var core = new ReceiverHandoff(1); long token = core.BeginConnection();
            Assert.That(core.Publish(token, Occurrence()), Is.True);
            Assert.That(core.Publish(token, Occurrence(2)), Is.False);
            var sink = new TestSink(); core.Tick(new TestClock(), sink);
            Assert.That(sink.Calls, Is.Zero); Assert.That(core.TakeAck(token), Is.Null);
        }

        [Test]
        public void AckOverflowAndDedupCapacityFailClosed()
        {
            foreach (var core in new[] { new ReceiverHandoff(1, 10), new ReceiverHandoff(10, 1) })
            {
                long token = core.BeginConnection(); var sink = new TestSink(); var clock = new TestClock();
                var disconnected = core.WaitForDisconnectAsync(token);
                Assert.That(disconnected.IsCompleted, Is.False);
                core.Publish(token, Occurrence()); core.Tick(clock, sink);
                core.Publish(token, Occurrence(2));
                Assert.Throws<InvalidOperationException>(() => core.Tick(clock, sink));
                Assert.That(sink.Calls, Is.EqualTo(1));
                Assert.That(core.TakeAck(token), Is.Null);
                Assert.That(core.IsConnected(token), Is.False);
                Assert.That(disconnected.IsCompleted, Is.True, "Must interrupt blocked socket operations");
            }
        }

        [Test]
        public void ExpiredDedupEntriesCanBeReclaimed()
        {
            var core = new ReceiverHandoff(10, 1); var clock = new TestClock();
            long token = core.BeginConnection(); var sink = new TestSink();
            core.Publish(token, Occurrence()); core.Tick(clock, sink); core.TakeAck(token);
            clock.Time = 11; core.Publish(token, Occurrence(2, expires: 12)); core.Tick(clock, sink);
            Assert.That(core.TakeAck(token).Ack.Status, Is.EqualTo(AckStatus.Accepted));
        }

        [Test]
        public void SceneExceptionDoesNotAckOrRepeatAnUncertainEffect()
        {
            var core = new ReceiverHandoff(); var clock = new TestClock();
            var sink = new TestSink { Throw = true }; long token = core.BeginConnection();
            core.Publish(token, Occurrence()); Assert.Throws<Exception>(() => core.Tick(clock, sink));
            Assert.That(core.TakeAck(token), Is.Null);
            token = core.BeginConnection(); sink.Throw = false;
            core.Publish(token, Occurrence()); core.Tick(clock, sink);
            Assert.That(core.TakeAck(token).Ack.Status, Is.EqualTo(AckStatus.Duplicate));
            Assert.That(sink.Calls, Is.EqualTo(1));
        }

        [Test]
        public void SuspendRejectsLateConnectAndResumptionRetainsDedup()
        {
            var core = new ReceiverHandoff(); var clock = new TestClock();
            long token = core.BeginConnection(); core.Publish(token, Occurrence()); core.Tick(clock, null);
            core.Suspend(); Assert.That(core.BeginConnection(), Is.Zero);
            Assert.That(core.Publish(token, Occurrence()), Is.False);
            core.Resume(); token = core.BeginConnection();
            core.Publish(token, Occurrence()); core.Tick(clock, null);
            Assert.That(core.TakeAck(token).Ack.Status, Is.EqualTo(AckStatus.Duplicate));
        }

        [Test]
        public void SessionChangeDropsOldPendingWorkAndResetsStateSequence()
        {
            var core = new ReceiverHandoff(); var clock = new TestClock(); var sink = new TestSink();
            long token = core.BeginConnection();
            core.Publish(token, State(100)); core.Tick(clock, sink);
            core.Publish(token, Occurrence());
            var next = State(1); next.Envelope.SessionId = "next";
            core.Publish(token, next); core.Tick(clock, sink);
            Assert.That(sink.State.SessionId, Is.EqualTo("next"));
            Assert.That(sink.State.Sequence, Is.EqualTo(1));
            Assert.That(sink.Calls, Is.Zero);
            Assert.That(core.TakeAck(token), Is.Null);
        }

        [Test]
        public void FutureEventFailsWithoutSinkCallAndUnknownFieldsAreTolerated()
        {
            var core = new ReceiverHandoff(); var sink = new TestSink();
            long token = core.BeginConnection(); core.Publish(token, Occurrence());
            Assert.Throws<InvalidOperationException>(() => core.Tick(new TestClock { Time = 9 }, sink));
            Assert.That(sink.Calls, Is.Zero);
            Assert.That(core.TakeAck(token), Is.Null);
            // Field 100 (varint) is unknown to v1 but must not break validation.
            byte[] bytes = WireTests.Hex("08011207666978747572655a1608011001190000000000002440210000000000002640a00601");
            Assert.DoesNotThrow(() => WireMessage.Validate(GestureEnvelope.Parser.ParseFrom(bytes)));
        }
    }
}
