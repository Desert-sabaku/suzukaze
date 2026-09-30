using System.Collections;
using System.Reflection;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.TestTools;

namespace Suzukaze.Gesture.Delivery.Tests
{
    public class OwnershipTests
    {
        private sealed class Clock : IMonotonicClock { public double Now => 10; }
        private sealed class AcceptingSink : IGestureSink
        {
            public int Calls;
            public StateView State;
            public void DeliverState(StateView state) { State = state; }
            public bool TryAcceptEvent(string session, Protocol.Event occurrence) { Calls++; return true; }
        }

        private static ReceiverHandoff Handoff(GestureReceiverBehaviour receiver) =>
            (ReceiverHandoff)typeof(GestureReceiverBehaviour).GetField("handoff",
                BindingFlags.Instance | BindingFlags.NonPublic).GetValue(receiver);

        private static void ResetPlaySession() =>
            typeof(GestureReceiverBehaviour).GetMethod("ResetPlaySession",
                BindingFlags.Static | BindingFlags.NonPublic).Invoke(null, null);

        private static GestureReceiverBehaviour CreateOwner(GameObject go)
        {
            go.SetActive(false);
            var receiver = go.AddComponent<GestureReceiverBehaviour>();
            typeof(GestureReceiverBehaviour).GetField("endpoint", BindingFlags.Instance | BindingFlags.NonPublic)
                .SetValue(receiver, "ws://127.0.0.1:1");
            go.SetActive(true);
            receiver.enabled = false;
            return receiver;
        }

        private static ReceivedMessage Occurrence() => new ReceivedMessage(new Protocol.GestureEnvelope {
            Version = 1, SessionId = "owner-replacement", Event = new Protocol.Event {
                EventId = 1, Gesture = Protocol.OccurrenceGesture.Ramune, OccurredAt = 10, ExpiresAt = 11
            }
        }, 10);

        [UnityTest]
        public IEnumerator DestroyedOwnerReplacementDoesNotRepeatLostAckEffect()
        {
            if (Application.platform != RuntimePlatform.WindowsEditor && Application.platform != RuntimePlatform.WindowsPlayer)
                Assert.Ignore("Production receiver intentionally requires Windows QPC");
            ResetPlaySession();
            var first = new GameObject("lost ACK owner");
            GameObject second = null;
            var clock = new Clock(); var sink = new AcceptingSink();
            try
            {
                var old = Handoff(CreateOwner(first));
                old.Resume(); long token = old.BeginConnection();
                old.Publish(token, Occurrence()); old.Tick(clock, sink);
                Assert.That(sink.Calls, Is.EqualTo(1));
                // Do not dequeue/send the accepted ACK. Destroy the actual owner.
                Object.Destroy(first);
                yield return null;
                Assert.That(first == null, Is.True);
                Assert.That(old.IsConnected(token), Is.False);

                second = new GameObject("replacement owner");
                var receiver = CreateOwner(second);
                var replacement = Handoff(receiver);
                Assert.That(replacement, Is.Not.SameAs(old), "Pending work belongs to each owner");
                replacement.Tick(clock, sink);
                Assert.That(sink.State.Fresh, Is.False);
                replacement.Resume(); token = replacement.BeginConnection();
                replacement.Publish(token, Occurrence()); replacement.Tick(clock, sink);
                Assert.That(replacement.TakeAck(token).Ack.Status, Is.EqualTo(Protocol.AckStatus.Duplicate));
                Assert.That(sink.Calls, Is.EqualTo(1), "Replacement must not repeat the effect");

                // Simulate subsystem registration with domain AND scene reload off:
                // statics and the same component remain, but the new play run is isolated.
                ResetPlaySession();
                Assert.That(replacement.IsConnected(token), Is.False);
                receiver.enabled = true;
                receiver.enabled = false;
                var newPlay = Handoff(receiver);
                Assert.That(newPlay, Is.Not.SameAs(replacement));
                newPlay.Resume(); token = newPlay.BeginConnection();
                newPlay.Publish(token, Occurrence()); newPlay.Tick(clock, sink);
                Assert.That(newPlay.TakeAck(token).Ack.Status, Is.EqualTo(Protocol.AckStatus.Accepted));
                Assert.That(sink.Calls, Is.EqualTo(2));
            }
            finally
            {
                if (first != null) Object.Destroy(first);
                if (second != null) Object.Destroy(second);
                ResetPlaySession();
            }
            yield return null;
        }

        [UnityTest]
        public IEnumerator DuplicateOwnerIsDestroyedAndOwnerSurvivesDisable()
        {
            if (Application.platform != RuntimePlatform.WindowsEditor && Application.platform != RuntimePlatform.WindowsPlayer)
                Assert.Ignore("Production receiver intentionally requires Windows QPC");
            var first = new GameObject("gesture test owner");
            var duplicate = new GameObject("gesture duplicate");
            try
            {
                var receiver = first.AddComponent<GestureReceiverBehaviour>();
                duplicate.AddComponent<GestureReceiverBehaviour>();
                yield return null;
                Assert.That(receiver.IsOwner, Is.True);
                Assert.That(duplicate == null, Is.True);
                receiver.enabled = false;
                yield return null;
                Assert.That(receiver.IsOwner, Is.True);
                receiver.enabled = true;
                yield return null;
                Assert.That(receiver.IsOwner, Is.True);
            }
            finally
            {
                if (first != null) Object.Destroy(first);
                if (duplicate != null) Object.Destroy(duplicate);
            }
            yield return null;
        }

        [UnityTest]
        public IEnumerator DiagnosticSinkDoesNotAcceptByDefault()
        {
            var go = new GameObject("gesture diagnostic test");
            try
            {
                var sink = go.AddComponent<GestureDiagnosticSink>();
                Assert.That(sink.TryAcceptEvent("test", new Protocol.Event { EventId = 1 }), Is.False);
                Assert.That(sink.EventCount, Is.EqualTo(1));
            }
            finally { Object.Destroy(go); }
            yield return null;
        }
    }
}
