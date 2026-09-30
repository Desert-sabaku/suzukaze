using System.Collections;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.TestTools;

namespace Suzukaze.Gesture.Delivery.Tests
{
    public class OwnershipTests
    {
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
