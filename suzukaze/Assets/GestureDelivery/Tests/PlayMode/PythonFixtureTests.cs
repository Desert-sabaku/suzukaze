#if UNITY_EDITOR
using System;
using System.Collections;
using System.Diagnostics;
using System.IO;
using System.Reflection;
using System.Text;
using System.Threading.Tasks;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.TestTools;
using Object = UnityEngine.Object;

namespace Suzukaze.Gesture.Delivery.Tests
{
    public sealed class PythonFixtureTests
    {
        private Process fixture;
        private Task<string> stderr;
        private GameObject owner;
        private GestureReceiverBehaviour receiver;
        private double deadline;

        // Only the JSON-lines control protocol uses JsonUtility. Gesture delivery
        // still traverses the production protobuf TCP/relay/WebSocket path.
        [Serializable] private sealed class Command { public string command; }
        [Serializable] private sealed class AckMessage
        {
            public string session_id;
            public ulong event_id;
            public string status;
        }
        [Serializable] private sealed class Ack
        {
            public AckMessage message;
            public bool removed;
        }
        [Serializable] private sealed class SentEvent { public double expires_at; }
        [Serializable] private sealed class Response
        {
            public bool ready;
            public string uri;
            public string session;
            public double occurred_at;
            public double expires_at;
            public SentEvent[] sent;
            public Ack[] acks;
            public int polls;
            public double now;
        }

        [UnityTest]
        public IEnumerator UpdateAcceptsPythonEventAndAckStopsLiveRetries()
        {
            string python = Environment.GetEnvironmentVariable("GESTURE_E2E_PYTHON");
            string script = Environment.GetEnvironmentVariable("GESTURE_E2E_FIXTURE");
            if (string.IsNullOrWhiteSpace(python) || string.IsNullOrWhiteSpace(script))
                Assert.Ignore("Opt in with absolute GESTURE_E2E_PYTHON and GESTURE_E2E_FIXTURE paths");
            if (Application.platform != RuntimePlatform.WindowsEditor
                && !(Application.platform == RuntimePlatform.LinuxEditor && IntPtr.Size == 8))
                Assert.Ignore("Requires native Windows or 64-bit Linux Editor");
            Assert.That(Path.IsPathRooted(python) && File.Exists(python), Is.True, python);
            Assert.That(Path.IsPathRooted(script) && File.Exists(script), Is.True, script);

            deadline = Time.realtimeSinceStartupAsDouble + 20;
            fixture = Process.Start(new ProcessStartInfo {
                FileName = python,
                Arguments = "-u " + QuoteArgument(script),
                WorkingDirectory = Path.GetDirectoryName(script),
                UseShellExecute = false,
                CreateNoWindow = true,
                RedirectStandardInput = true,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
            });
            Assert.That(fixture, Is.Not.Null);
            stderr = fixture.StandardError.ReadToEndAsync();
            Response ready = null;
            yield return ReadResponse(value => ready = value);
            Assert.That(ready.ready, Is.True);
            Assert.That(ready.session, Is.Not.Null.And.Not.Empty);

            owner = new GameObject("Python fixture receiver");
            owner.SetActive(false);
            var sink = owner.AddComponent<GestureDiagnosticSink>();
            SetPrivate(sink, "acceptEvents", true);
            receiver = owner.AddComponent<GestureReceiverBehaviour>();
            SetPrivate(receiver, "endpoint", ready.uri);
            receiver.SetSink(sink);
            // Awake/OnEnable establish the persistent owner and native clock.
            // No direct Tick, Update, handoff injection, or clock replacement.
            owner.SetActive(true);
            yield return null;
            Assert.That(receiver.IsOwner, Is.True);
            Assert.That(owner.scene.name, Is.EqualTo("DontDestroyOnLoad"));

            Response published = null;
            yield return SendCommand("publish", value => published = value);
            Assert.That(published.expires_at - published.occurred_at,
                Is.EqualTo(60).Within(0.001));

            Response baseline = null;
            while (baseline == null)
            {
                CheckDeadline("Unity Update acceptance and Python ACK removal");
                Response snapshot = null;
                yield return SendCommand("snapshot", value => snapshot = value);
                if (snapshot.acks != null)
                {
                    foreach (var ack in snapshot.acks)
                    {
                        if (!ack.removed) continue;
                        Assert.That(ack.message.status, Is.EqualTo("accepted"));
                        Assert.That(ack.message.session_id, Is.EqualTo(ready.session));
                        Assert.That(ack.message.event_id, Is.EqualTo(1UL));
                        baseline = snapshot;
                    }
                }
                if (baseline == null) yield return null;
            }
            Assert.That(sink.EventCount, Is.EqualTo(1));
            Assert.That(baseline.sent, Is.Not.Null.And.Not.Empty);

            // Observe multiple real 0.2s retry periods, not scaled game time.
            double observeUntil = Time.realtimeSinceStartupAsDouble + 0.8;
            while (Time.realtimeSinceStartupAsDouble < observeUntil)
            {
                CheckDeadline("real-time retry observation");
                yield return null;
            }
            Response later = null;
            do
            {
                CheckDeadline("source to keep polling after ACK");
                yield return SendCommand("snapshot", value => later = value);
                yield return null;
            } while (later.polls < baseline.polls + 5 || later.now < baseline.now + 0.8);

            Assert.That(later.sent.Length, Is.EqualTo(baseline.sent.Length),
                "Accepted ACK must stop source retries");
            Assert.That(later.now, Is.LessThan(published.expires_at),
                "Event TTL must still be live during retry observation");
            Assert.That(later.now, Is.LessThan(baseline.sent[0].expires_at));
            Assert.That(sink.EventCount, Is.EqualTo(1));
            Assert.That(receiver.LastError, Is.Null);
        }

        private IEnumerator SendCommand(string command, Action<Response> receive)
        {
            var write = fixture.StandardInput.WriteLineAsync(
                JsonUtility.ToJson(new Command { command = command }));
            yield return Await(write, "fixture stdin write");
            yield return Await(fixture.StandardInput.FlushAsync(), "fixture stdin flush");
            yield return ReadResponse(receive);
        }

        private IEnumerator ReadResponse(Action<Response> receive)
        {
            var read = fixture.StandardOutput.ReadLineAsync();
            yield return Await(read, "fixture stdout response");
            Assert.That(read.Result, Is.Not.Null, "Fixture stdout closed. " + Errors());
            var response = JsonUtility.FromJson<Response>(read.Result);
            Assert.That(response, Is.Not.Null, "Invalid fixture response: " + read.Result);
            receive(response);
        }

        private IEnumerator Await(Task task, string description)
        {
            double limit = Math.Min(deadline, Time.realtimeSinceStartupAsDouble + 5);
            while (!task.IsCompleted)
            {
                if (Time.realtimeSinceStartupAsDouble >= limit)
                    Assert.Fail(description + " timed out. " + Errors());
                yield return null;
            }
            task.GetAwaiter().GetResult();
        }

        private void CheckDeadline(string description)
        {
            if (Time.realtimeSinceStartupAsDouble >= deadline)
                Assert.Fail(description + " timed out; receiver=" + receiver?.LastError + ". " + Errors());
        }

        private string Errors() => stderr != null && stderr.Status == TaskStatus.RanToCompletion
            ? stderr.Result : "Fixture stderr not yet closed";

        [UnityTearDown]
        public IEnumerator Stop()
        {
            if (owner != null) Object.Destroy(owner);
            yield return null; // OnDisable/OnDestroy cancel and retire the real worker.
            owner = null;
            receiver = null;
            if (fixture == null) yield break;

            var process = fixture;
            fixture = null;
            // Closing stdin gives the fixture EOF. All blocking process waits run
            // off the Unity thread; forced termination targets only this child.
            var cleanup = Task.Run(() => {
                try
                {
                    try { process.StandardInput.Close(); }
                    finally
                    {
                        // Even a broken stdin pipe must not leave a child alive.
                        bool forced = !process.WaitForExit(3000);
                        if (forced)
                        {
                            process.Kill();
                            if (!process.WaitForExit(3000))
                                throw new TimeoutException("Fixture did not exit after kill");
                        }
                        if (forced) throw new TimeoutException("Fixture required forced termination");
                    }
                    if (process.ExitCode != 0)
                        throw new InvalidOperationException("Fixture exit code " + process.ExitCode);
                }
                finally { process.Dispose(); }
            });
            deadline = Time.realtimeSinceStartupAsDouble + 10;
            // Cleanup gets up to eight seconds (two bounded three-second waits).
            while (!cleanup.IsCompleted)
            {
                if (Time.realtimeSinceStartupAsDouble >= deadline - 2)
                    Assert.Fail("Fixture cleanup timed out. " + Errors());
                yield return null;
            }
            cleanup.GetAwaiter().GetResult();
            yield return Await(stderr, "fixture stderr drain");
            if (!string.IsNullOrEmpty(stderr.Result)) TestContext.Progress.WriteLine(stderr.Result);
            var retiring = (Task)typeof(GestureReceiverBehaviour).GetField("retiring",
                BindingFlags.Static | BindingFlags.NonPublic).GetValue(null);
            while (!retiring.IsCompleted)
            {
                CheckDeadline("receiver cancellation");
                yield return null;
            }
            Assert.That(retiring.IsFaulted, Is.False, retiring.Exception?.ToString());
            stderr = null;
        }

        private static void SetPrivate(object target, string name, object value) =>
            target.GetType().GetField(name, BindingFlags.Instance | BindingFlags.NonPublic)
                .SetValue(target, value);

        // ProcessStartInfo.ArgumentList is not supported by all Unity Mono versions.
        private static string QuoteArgument(string value)
        {
            var result = new StringBuilder("\"");
            int slashes = 0;
            foreach (char character in value)
            {
                if (character == '\\') { slashes++; continue; }
                result.Append('\\', character == '"' ? slashes * 2 + 1 : slashes);
                result.Append(character);
                slashes = 0;
            }
            result.Append('\\', slashes * 2);
            return result.Append('"').ToString();
        }
    }
}
#endif
