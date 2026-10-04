using System.Collections;
using System.Reflection;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.TestTools;

namespace Suzukaze.Gesture.Receiver.Tests
{
    public class OwnershipTests
    {
        private sealed class Clock : IMonotonicClock { public double Now => 10; }
        private sealed class AcceptingSubscriber
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
            RequireSupportedPlatform();
            ResetPlaySession();
            var first = new GameObject("lost ACK owner");
            GameObject second = null;
            var clock = new Clock(); var sink = new AcceptingSubscriber();
            try
            {
                var firstReceiver = CreateOwner(first);
                var firstEvents = firstReceiver.Events;
                firstReceiver.Events.Occurred += sink.TryAcceptEvent;
                firstReceiver.Events.StateChanged += sink.DeliverState;
                var old = Handoff(firstReceiver);
                old.Resume(); long token = old.BeginConnection();
                old.Publish(token, Occurrence()); old.Tick(clock, firstReceiver.Events);
                Assert.That(sink.Calls, Is.EqualTo(1));
                Assert.That(sink.State, Is.SameAs(firstReceiver.Events.CurrentState));
                // Do not dequeue/send the accepted ACK. Destroy the actual owner.
                Object.Destroy(first);
                yield return null;
                Assert.That(first == null, Is.True);
                Assert.That(old.IsConnected(token), Is.False);

                second = new GameObject("replacement owner");
                var receiver = CreateOwner(second);
                Assert.That(receiver.Events, Is.Not.SameAs(firstEvents));
                receiver.Events.Occurred += sink.TryAcceptEvent;
                receiver.Events.StateChanged += sink.DeliverState;
                var replacement = Handoff(receiver);
                Assert.That(replacement, Is.Not.SameAs(old), "Pending work belongs to each owner");
                replacement.Tick(clock, receiver.Events);
                Assert.That(receiver.Events.CurrentState.Fresh, Is.False);
                replacement.Resume(); token = replacement.BeginConnection();
                replacement.Publish(token, Occurrence()); replacement.Tick(clock, receiver.Events);
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
                newPlay.Publish(token, Occurrence()); newPlay.Tick(clock, receiver.Events);
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
            RequireSupportedPlatform();
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

        private static void RequireSupportedPlatform()
        {
            bool windows = Application.platform == RuntimePlatform.WindowsEditor
                || Application.platform == RuntimePlatform.WindowsPlayer;
            bool linux = Application.platform == RuntimePlatform.LinuxEditor
                || Application.platform == RuntimePlatform.LinuxPlayer;
            if (!windows && !(linux && System.IntPtr.Size == 8))
                Assert.Ignore("Production receiver requires Windows or 64-bit Linux");
        }

        [UnityTest]
        public IEnumerator DiagnosticSinkDoesNotAcceptByDefault()
        {
            RequireSupportedPlatform();
            RequireIsolatedReceiverScene();
            var go = new GameObject("gesture diagnostic test");
            GestureReceiverBehaviour receiver = null;
            try
            {
                var sink = go.AddComponent<GestureDiagnosticSink>();
                receiver = GestureReceiverBehaviour.GetOrCreate();
                receiver.enabled = false;
                var handoff = Handoff(receiver);
                handoff.Resume();
                long token = handoff.BeginConnection();
                Assert.That(handoff.Publish(token, Occurrence()), Is.True);
                handoff.Tick(new Clock(), receiver.Events);
                Assert.That(handoff.TakeAck(token).Ack.Status, Is.EqualTo(Protocol.AckStatus.Ignored));
                Assert.That(sink.EventCount, Is.EqualTo(1));
            }
            finally
            {
                go.SetActive(false);
                Object.Destroy(go);
                if (receiver != null) Object.Destroy(receiver.gameObject);
            }
            yield return null;
        }

        [UnityTest]
        public IEnumerator DiagnosticObserverReadsCurrentStateAndDoesNotStealAcceptedEvents()
        {
            RequireSupportedPlatform();
            RequireIsolatedReceiverScene();
            var owner = new GameObject("diagnostic observer owner");
            var go = new GameObject("gesture diagnostic observer");
            try
            {
                var receiver = CreateOwner(owner);
                var handoff = Handoff(receiver);
                handoff.Resume();
                long token = handoff.BeginConnection();
                // Establish a non-default session state before the observer subscribes.
                Assert.That(handoff.Publish(token, Occurrence()), Is.True);
                handoff.Tick(new Clock(), receiver.Events);
                Assert.That(handoff.TakeAck(token).Ack.Status, Is.EqualTo(Protocol.AckStatus.Ignored));
                var current = receiver.Events.CurrentState;
                Assert.That(current.SessionId, Is.EqualTo("owner-replacement"));

                var accepting = new AcceptingSubscriber();
                receiver.Events.Occurred += accepting.TryAcceptEvent;
                var observer = go.AddComponent<GestureDiagnosticSink>();
                Assert.That(observer.LatestState, Is.SameAs(current));
                Assert.That(observer.EventCount, Is.Zero);

                var message = Occurrence();
                message.Envelope.Event.EventId = 2;
                Assert.That(handoff.Publish(token, message), Is.True);
                handoff.Tick(new Clock(), receiver.Events);
                Assert.That(handoff.TakeAck(token).Ack.Status, Is.EqualTo(Protocol.AckStatus.Accepted));
                Assert.That(accepting.Calls, Is.EqualTo(1));
                Assert.That(observer.EventCount, Is.EqualTo(1));

                var updated = new StateView();
                receiver.Events.DeliverState(updated);
                Assert.That(observer.LatestState, Is.SameAs(updated));

                observer.enabled = false;
                var disabledState = observer.LatestState;
                message = Occurrence();
                message.Envelope.Event.EventId = 3;
                Assert.That(handoff.Publish(token, message), Is.True);
                handoff.Tick(new Clock(), receiver.Events);
                Assert.That(handoff.TakeAck(token).Ack.Status, Is.EqualTo(Protocol.AckStatus.Accepted));
                Assert.That(accepting.Calls, Is.EqualTo(2));
                Assert.That(observer.EventCount, Is.EqualTo(1));
                receiver.Events.DeliverState(new StateView());
                Assert.That(observer.LatestState, Is.SameAs(disabledState));

                observer.enabled = true;
                Assert.That(observer.LatestState, Is.SameAs(receiver.Events.CurrentState));
            }
            finally
            {
                go.SetActive(false);
                Object.Destroy(go);
                Object.Destroy(owner);
            }
            yield return null;
        }

        private static void RequireIsolatedReceiverScene()
        {
            if (Object.FindObjectsByType<GestureReceiverBehaviour>(
                FindObjectsInactive.Include).Length != 0)
                Assert.Ignore("Run in an isolated PlayMode test scene without an existing receiver");
            ResetPlaySession();
        }
    }
}
