using System;
using System.Collections;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.TestTools;
using Object = UnityEngine.Object;

namespace Suzukaze.Gesture.Tests
{
    public class UchimizuTests
    {
        private sealed class Clock : IMonotonicClock { public double Now => 10; }
        private const BindingFlags PrivateInstance = BindingFlags.Instance | BindingFlags.NonPublic;
        private readonly List<GameObject> objects = new List<GameObject>();
        private Type effectType;
        private ParticleSystem prefab;
        private Transform neck;
        private Transform player;
        private GestureReceiverBehaviour receiver;
        private string particleName;
        private bool ownsSession;

        [SetUp]
        public void SetUp()
        {
            // Never take ownership of, reset, or destroy another scene's receiver.
            if (Object.FindObjectsByType<GestureReceiverBehaviour>(
                FindObjectsInactive.Include).Length != 0)
                Assert.Ignore("Run in an isolated PlayMode test scene without an existing receiver");

            effectType = Type.GetType("ParticleOnEnter, Assembly-CSharp");
            Assert.That(effectType, Is.Not.Null, "The real runtime effect must be available");
            ResetPlaySession();
            ownsSession = true;

            // Awake establishes the real owner/handoff. Keeping the component disabled
            // before activation avoids starting sockets or a platform-dependent clock.
            var owner = NewObject("uchimizu test receiver");
            owner.SetActive(false);
            receiver = owner.AddComponent<GestureReceiverBehaviour>();
            receiver.enabled = false;
            owner.SetActive(true);
            Assert.That(receiver.IsOwner, Is.True);

            particleName = "uchimizu-test-" + Guid.NewGuid().ToString("N");
            var template = NewObject(particleName);
            template.SetActive(false);
            prefab = template.AddComponent<ParticleSystem>();
            var main = prefab.main;
            main.playOnAwake = false;
            main.stopAction = ParticleSystemStopAction.None;
            template.SetActive(true);

            // A rotated parent distinguishes world-space up from neck-local up.
            var parent = NewObject("uchimizu neck parent").transform;
            parent.SetPositionAndRotation(new Vector3(3, -2, 7), Quaternion.Euler(31, 57, 19));
            neck = NewObject("uchimizu neck").transform;
            neck.SetParent(parent, false);
            neck.localPosition = new Vector3(1, 2, -3);
            neck.localRotation = Quaternion.Euler(12, 34, 56);
            player = NewObject("uchimizu player").transform;
            player.position = new Vector3(-40, 20, 90);
        }

        [UnityTearDown]
        public IEnumerator TearDown()
        {
            // Instantiate creates root objects, so clean up only our unique copies.
            foreach (var copy in Copies()) Object.Destroy(copy.gameObject);
            for (int i = objects.Count - 1; i >= 0; --i)
                if (objects[i] != null) Object.Destroy(objects[i]);
            objects.Clear();
            yield return null; // Let OnDisable/OnDestroy retire the owned receiver first.
            if (ownsSession) ResetPlaySession();
            ownsSession = false;
            particleName = null;
        }

        [Test]
        public void HandoffAcceptsOneRealEffectAndDoesNotReplayDuplicateExpiredOrRamune()
        {
            var effect = CreateEffect();
            var handoff = Handoff();
            long token = handoff.BeginConnection();
            var occurrence = Occurrence(1);

            AssertAck(handoff, token, occurrence, Protocol.AckStatus.Accepted);
            Assert.That(Copies(), Has.Length.EqualTo(1));
            var first = Copies()[0];
            AssertPlacement(first, neck, 0.375f);

            // Retry on a fresh connection, as when the accepted ACK was lost.
            handoff.Disconnect(token);
            token = handoff.BeginConnection();
            AssertAck(handoff, token, occurrence, Protocol.AckStatus.Duplicate);
            Assert.That(Copies(), Is.EquivalentTo(new[] { first }));

            AssertAck(handoff, token, Occurrence(2, expiresAt: 10), Protocol.AckStatus.Expired);
            Assert.That(Copies(), Is.EquivalentTo(new[] { first }));
            AssertAck(handoff, token, Occurrence(3, Protocol.OccurrenceGesture.Ramune),
                Protocol.AckStatus.Ignored);
            Assert.That(Copies(), Is.EquivalentTo(new[] { first }));
            Assert.That(TryAcceptEvent(effect, null), Is.False);
            Assert.That(Copies(), Has.Length.EqualTo(1));
        }

        [TestCase("particlePrefab")]
        [TestCase("neck")]
        [TestCase("disabled")]
        [TestCase("inactive")]
        public void UnavailableEffectIsIgnoredAndManualPlayAlsoFails(string unavailable)
        {
            var effect = CreateEffect();
            if (unavailable == "disabled") effect.enabled = false;
            else if (unavailable == "inactive") effect.gameObject.SetActive(false);
            else Set(effect, unavailable, null);

            // Call the public handler directly as well: a stale reference must not accept.
            Assert.That(TryAcceptEvent(effect, Occurrence(1)), Is.False);
            Assert.That(TryPlay(effect), Is.False);
            var handoff = Handoff();
            long token = handoff.BeginConnection();
            AssertAck(handoff, token, Occurrence(2), Protocol.AckStatus.Ignored);
            Assert.That(Copies(), Is.Empty);
        }

        [Test]
        public void GestureOptOutIgnoresDeliveryButManualTryPlayStillUsesNeckPlacement()
        {
            var effect = CreateEffect();
            Set(effect, "receiveGestures", false);
            var handoff = Handoff();
            long token = handoff.BeginConnection();
            AssertAck(handoff, token, Occurrence(1), Protocol.AckStatus.Ignored);
            Assert.That(Copies(), Is.Empty);

            Assert.That(TryPlay(effect), Is.True);
            Assert.That(Copies(), Has.Length.EqualTo(1));
            var manual = Copies()[0];
            AssertPlacement(manual, neck, 0.375f);

            // Both entry points must read the current neck and offset, not cached data
            // or the retained legacy player field.
            neck.SetPositionAndRotation(new Vector3(-8, 4, 2), Quaternion.Euler(80, 15, 29));
            Set(effect, "heightOffset", -0.25f);
            Set(effect, "receiveGestures", true);
            AssertAck(handoff, token, Occurrence(2), Protocol.AckStatus.Accepted);
            Assert.That(Copies(), Has.Length.EqualTo(2));
            AssertPlacement(Copies().Single(copy => copy != manual), neck, -0.25f);
        }

        [Test]
        public void OptedOutOnEnableLeavesActiveEffectReceivingEvents()
        {
            CreateEffect();
            var optedOut = CreateEffect(false);
            var handoff = Handoff();
            long token = handoff.BeginConnection();
            AssertAck(handoff, token, Occurrence(1), Protocol.AckStatus.Accepted);
            Assert.That(Copies(), Has.Length.EqualTo(1));
            optedOut.enabled = false;
            AssertAck(handoff, token, Occurrence(2), Protocol.AckStatus.Accepted);
            Assert.That(Copies(), Has.Length.EqualTo(2));
        }

        [Test]
        public void ActiveEffectsBothReceiveAndDisablingOldOnlyRemovesOld()
        {
            var old = CreateEffect();
            var next = CreateEffect();
            var nextNeck = NewObject("next scene neck").transform;
            nextNeck.SetPositionAndRotation(new Vector3(20, 30, 40), Quaternion.Euler(7, 83, 21));
            Set(next, "neck", nextNeck);
            Assert.That(GestureReceiverBehaviour.GetOrCreate(), Is.SameAs(receiver));
            Assert.That(Object.FindObjectsByType<GestureReceiverBehaviour>(), Has.Length.EqualTo(1));
            var handoff = Handoff();
            long token = handoff.BeginConnection();
            AssertAck(handoff, token, Occurrence(1), Protocol.AckStatus.Accepted);
            Assert.That(Copies(), Has.Length.EqualTo(2));
            var firstCopies = Copies();
            AssertPlacement(firstCopies.Single(copy =>
                Vector3.Distance(copy.transform.position, neck.position + Vector3.up * 0.375f) < 0.0001f),
                neck, 0.375f);
            AssertPlacement(firstCopies.Single(copy =>
                Vector3.Distance(copy.transform.position, nextNeck.position + Vector3.up * 0.375f) < 0.0001f),
                nextNeck, 0.375f);

            old.enabled = false;
            AssertAck(handoff, token, Occurrence(2), Protocol.AckStatus.Accepted);
            Assert.That(Copies(), Has.Length.EqualTo(3));
            AssertPlacement(Copies().Single(copy => !firstCopies.Contains(copy)), nextNeck, 0.375f);

            next.enabled = false;
            Assert.That(GestureReceiverBehaviour.GetOrCreate(), Is.SameAs(receiver));
            AssertAck(handoff, token, Occurrence(3), Protocol.AckStatus.Ignored);
            Assert.That(Copies(), Has.Length.EqualTo(3));

            old.enabled = true;
            var beforeReenable = Copies();
            AssertAck(handoff, token, Occurrence(4), Protocol.AckStatus.Accepted);
            Assert.That(Copies(), Has.Length.EqualTo(4));
            AssertPlacement(Copies().Single(copy => !beforeReenable.Contains(copy)), neck, 0.375f);
        }

        [Test]
        public void NoSubscribersIgnoresEvent()
        {
            var handoff = Handoff();
            long token = handoff.BeginConnection();
            AssertAck(handoff, token, Occurrence(1), Protocol.AckStatus.Ignored);
            Assert.That(Copies(), Is.Empty);
        }

        [Test]
        public void RamuneSubscriberAndWaterEffectWorkIndependently()
        {
            CreateEffect();
            int ramuneCount = 0;
            Func<string, Protocol.Event, bool> ramune = (session, occurrence) => {
                if (occurrence.Gesture != Protocol.OccurrenceGesture.Ramune) return false;
                ramuneCount++;
                return true;
            };
            receiver.Events.Occurred += ramune;
            try
            {
                var handoff = Handoff();
                long token = handoff.BeginConnection();
                AssertAck(handoff, token, Occurrence(1), Protocol.AckStatus.Accepted);
                Assert.That(Copies(), Has.Length.EqualTo(1));
                Assert.That(ramuneCount, Is.Zero);
                AssertAck(handoff, token, Occurrence(2, Protocol.OccurrenceGesture.Ramune),
                    Protocol.AckStatus.Accepted);
                Assert.That(Copies(), Has.Length.EqualTo(1));
                Assert.That(ramuneCount, Is.EqualTo(1));
                AssertAck(handoff, token, Occurrence(3), Protocol.AckStatus.Accepted);
                Assert.That(Copies(), Has.Length.EqualTo(2));
                Assert.That(ramuneCount, Is.EqualTo(1));
            }
            finally { receiver.Events.Occurred -= ramune; }
        }

        [Test]
        public void ActiveSceneReceiverIsReusedWhenStaticOwnerIsUnset()
        {
            // Exercise scene discovery separately from the persistent-owner fast path.
            // Reset follows the same domain-reload-off lifecycle used by OwnershipTests.
            ResetPlaySession();
            Assert.That(receiver.IsOwner, Is.False);
            Assert.That(GestureReceiverBehaviour.GetOrCreate(), Is.SameAs(receiver));
            CreateEffect();
            Assert.That(Object.FindObjectsByType<GestureReceiverBehaviour>(), Has.Length.EqualTo(1));
            var handoff = Handoff();
            handoff.Resume();
            long token = handoff.BeginConnection();
            AssertAck(handoff, token, Occurrence(1), Protocol.AckStatus.Accepted);
            Assert.That(Copies(), Has.Length.EqualTo(1));
        }

        private GameObject NewObject(string name)
        {
            var go = new GameObject(name);
            objects.Add(go);
            return go;
        }

        private MonoBehaviour CreateEffect(bool receiveGestures = true)
        {
            var go = NewObject("uchimizu scene effect");
            go.SetActive(false);
            var effect = (MonoBehaviour)go.AddComponent(effectType);
            Assert.That(effectType.GetField("receiveGestures").GetValue(effect), Is.True,
                "Existing scenes must opt in without reserialization");
            Set(effect, "particlePrefab", prefab);
            Set(effect, "neck", neck);
            Set(effect, "player", player);
            Set(effect, "heightOffset", 0.375f);
            Set(effect, "receiveGestures", receiveGestures);
            go.SetActive(true);
            return effect;
        }

        private void Set(MonoBehaviour effect, string field, object value) =>
            effectType.GetField(field).SetValue(effect, value);

        private bool TryPlay(MonoBehaviour effect) =>
            (bool)effectType.GetMethod("TryPlay", Type.EmptyTypes).Invoke(effect, null);

        private bool TryAcceptEvent(MonoBehaviour effect, Protocol.Event occurrence) =>
            (bool)effectType.GetMethod("TryAcceptEvent").Invoke(effect, new object[] { "test", occurrence });

        private ParticleSystem[] Copies() => particleName == null ? new ParticleSystem[0] :
            Object.FindObjectsByType<ParticleSystem>(FindObjectsInactive.Include)
                .Where(particle => particle.name == particleName + "(Clone)").ToArray();

        private static void AssertPlacement(ParticleSystem copy, Transform origin, float offset)
        {
            Assert.That(Vector3.Distance(copy.transform.position, origin.position + Vector3.up * offset),
                Is.LessThan(0.0001f));
            Assert.That(Quaternion.Angle(copy.transform.rotation, origin.rotation), Is.LessThan(0.01f));
            Assert.That(copy.transform.parent, Is.Null);
        }

        private ReceiverHandoff Handoff() => (ReceiverHandoff)typeof(GestureReceiverBehaviour)
            .GetField("handoff", PrivateInstance).GetValue(receiver);

        private static void ResetPlaySession() => typeof(GestureReceiverBehaviour)
            .GetMethod("ResetPlaySession", BindingFlags.Static | BindingFlags.NonPublic).Invoke(null, null);

        private static Protocol.Event Occurrence(ulong id,
            Protocol.OccurrenceGesture gesture = Protocol.OccurrenceGesture.Uchimizu, double expiresAt = 11) =>
            new Protocol.Event { EventId = id, Gesture = gesture, OccurredAt = 9, ExpiresAt = expiresAt };

        private void AssertAck(ReceiverHandoff handoff, long token, Protocol.Event occurrence,
            Protocol.AckStatus expected)
        {
            Assert.That(handoff.Publish(token, new ReceivedMessage(new Protocol.GestureEnvelope {
                Version = 1, SessionId = "uchimizu-test", Event = occurrence
            }, 10)), Is.True);
            handoff.Tick(new Clock(), receiver.Events);
            var ack = handoff.TakeAck(token);
            Assert.That(ack, Is.Not.Null);
            Assert.That(ack.SessionId, Is.EqualTo("uchimizu-test"));
            Assert.That(ack.Ack.EventId, Is.EqualTo(occurrence.EventId));
            Assert.That(ack.Ack.Status, Is.EqualTo(expected));
            Assert.That(handoff.TakeAck(token), Is.Null);
        }
    }
}
