using System;
using System.Collections;
using System.Diagnostics;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using NUnit.Framework;
using Suzukaze.Gesture.Delivery;
using Suzukaze.Gesture.Protocol;

namespace GestureDelivery.Integration;

[TestFixture, NonParallelizable]
public sealed class DeliveryTests
{
    private Fixture fixture;
    private ReceiverHandoff handoff;
    private WebSocketReceiver receiver;
    private IMonotonicClock clock;
    private CancellationTokenSource stopping;
    private Task network;
    private Sink sink;

    [SetUp]
    public void Start()
    {
        clock = OperatingSystem.IsWindows() ? new WindowsQpcClock() : new LinuxClock();
        fixture = new Fixture();
        handoff = new ReceiverHandoff();
        sink = new Sink();
        stopping = new CancellationTokenSource();
        receiver = new WebSocketReceiver(handoff, clock);
        network = receiver.RunAsync(new Uri(fixture.Ready.GetProperty("uri").GetString()), stopping.Token);
    }

    [TearDown]
    public void Stop()
    {
        try
        {
            stopping?.Cancel();
            if (network != null) Assert.That(network.Wait(TimeSpan.FromSeconds(10)), Is.True,
                "Receiver did not stop within ten seconds");
        }
        finally
        {
            stopping?.Dispose();
            fixture?.Dispose();
        }
    }

    [TestCase(true, "accepted")]
    [TestCase(false, "ignored")]
    public void DecisionAndDuplicateAckReachPythonAndStopRetries(bool accept, string status)
    {
        sink.Accept = accept;
        // This brackets the Python monotonic sample with the actual platform clock.
        // On Windows this explicitly exercises production QPC, with no offset shim.
        double before = clock.Now;
        var published = fixture.Command("publish");
        double after = clock.Now;
        Assert.That(published.GetProperty("occurred_at").GetDouble(),
            Is.InRange(before - 0.001, after + 0.001), "Python and C# host clock epochs differ");

        // Withhold Update until a real retry is in the real main-thread queue.
        Until(() => PendingEvents() >= 2, "Two actual deliveries before Update");
        Assert.That(sink.EventCalls, Is.Zero);
        Assert.That(fixture.Command("snapshot").GetProperty("acks").GetArrayLength(), Is.Zero,
            "Receiving transport bytes must not ACK before main-thread adoption");
        handoff.Tick(clock, sink);
        Assert.That(sink.EventCalls, Is.EqualTo(1), "Duplicate must not reach scene twice");
        Assert.That(sink.State.Fresh && sink.State.Tracking, Is.True);
        Assert.That(sink.State.Gesture, Is.EqualTo(ContinuousGesture.Fanning));
        Assert.That(sink.Session, Is.EqualTo(fixture.Ready.GetProperty("session").GetString()));
        Assert.That(sink.Event.EventId, Is.EqualTo(1UL));
        Assert.That(sink.Event.Gesture, Is.EqualTo(OccurrenceGesture.Ramune));
        Assert.That(sink.Event.OccurredAt, Is.EqualTo(published.GetProperty("occurred_at").GetDouble()));

        JsonElement snapshot = default;
        Until(() =>
        {
            handoff.Tick(clock, sink);
            snapshot = fixture.Command("snapshot");
            return snapshot.GetProperty("acks").GetArrayLength() >= 2;
        }, "ACKs to travel WebSocket -> relay -> TCP -> outbox");
        var acks = snapshot.GetProperty("acks");
        AssertAck(acks[0], status, true);
        for (int i = 1; i < acks.GetArrayLength(); i++) AssertAck(acks[i], "duplicate", false);
        AssertRetriesStopped(snapshot);
        Assert.That(sink.EventCalls, Is.EqualTo(1));
    }

    [Test]
    public void MainThreadRechecksQueuedEventExpiryAndStateStaleness()
    {
        var published = fixture.Command("publish");
        Until(() => PendingEvents() >= 1 && PendingFreshState(), "Fresh state and live event queued");
        Assert.That(clock.Now, Is.LessThan(published.GetProperty("expires_at").GetDouble()),
            "Event must have arrived live, before main-thread delay");
        Assert.That(fixture.Command("snapshot").GetProperty("acks").GetArrayLength(), Is.Zero);

        // Simulate an Update stall without sleeping through the generous 60s TTL.
        // Network arrival still used the native host clock; only Update advances.
        var delayedUpdate = new FixedClock(published.GetProperty("expires_at").GetDouble() + 1);
        handoff.Tick(delayedUpdate, sink);
        Assert.That(sink.EventCalls, Is.Zero);
        Assert.That(sink.State.Fresh, Is.False);
        Assert.That(sink.State.Tracking, Is.False);
        Assert.That(sink.State.Gesture, Is.EqualTo(ContinuousGesture.None));
        JsonElement snapshot = default;
        Until(() =>
        {
            handoff.Tick(delayedUpdate, sink);
            snapshot = fixture.Command("snapshot");
            return snapshot.GetProperty("acks").GetArrayLength() > 0;
        }, "Expired main-thread decision to reach Python");
        AssertAck(snapshot.GetProperty("acks")[0], "expired", true);
        AssertRetriesStopped(snapshot);
    }

    private void AssertAck(JsonElement ack, string status, bool removed)
    {
        var message = ack.GetProperty("message");
        Assert.That(message.GetProperty("status").GetString(), Is.EqualTo(status));
        Assert.That(message.GetProperty("event_id").GetInt32(), Is.EqualTo(1));
        Assert.That(message.GetProperty("session_id").GetString(),
            Is.EqualTo(fixture.Ready.GetProperty("session").GetString()));
        Assert.That(ack.GetProperty("removed").GetBoolean(), Is.EqualTo(removed));
    }

    private void AssertRetriesStopped(JsonElement baseline)
    {
        int sent = baseline.GetProperty("sent").GetArrayLength();
        int polls = baseline.GetProperty("polls").GetInt32();
        double now = baseline.GetProperty("now").GetDouble();
        JsonElement later = default;
        Until(() =>
        {
            later = fixture.Command("snapshot");
            // Verify the server kept polling across multiple retry intervals.
            return later.GetProperty("polls").GetInt32() >= polls + 5
                && later.GetProperty("now").GetDouble() >= now + 0.8;
        }, "Source to continue polling after ACK");
        Assert.That(later.GetProperty("sent").GetArrayLength(), Is.EqualTo(sent),
            "ACK must stop resends while the Python-side event TTL is still live");
        Assert.That(later.GetProperty("now").GetDouble(),
            Is.LessThan(baseline.GetProperty("sent")[0].GetProperty("expires_at").GetDouble()),
            "Source expiry must not be mistaken for ACK stopping retries");
        Assert.That(receiver.LastError, Is.Null);
    }

    // Read-only test probes synchronize with the real handoff lock. This avoids
    // timing sleeps or a substitute Publish implementation in application code.
    private object Field(string name) => typeof(ReceiverHandoff)
        .GetField(name, BindingFlags.Instance | BindingFlags.NonPublic).GetValue(handoff);
    private int PendingEvents() { lock (Field("gate")) return ((ICollection)Field("events")).Count; }
    private bool PendingFreshState()
    {
        lock (Field("gate")) return (Field("state") as ReceivedMessage)?.Envelope.State.Fresh == true;
    }

    private void Until(Func<bool> condition, string description)
    {
        var timer = Stopwatch.StartNew();
        while (!condition())
        {
            if (timer.Elapsed > TimeSpan.FromSeconds(20))
                Assert.Fail(description + ": timed out; receiver=" + receiver.LastError);
            Thread.Sleep(10);
        }
    }

    private sealed class Sink : IGestureSink
    {
        private readonly int owner = Environment.CurrentManagedThreadId;
        public bool Accept = true;
        public int EventCalls;
        public StateView State;
        public Event Event;
        public string Session;
        public void DeliverState(StateView state)
        {
            Assert.That(Environment.CurrentManagedThreadId, Is.EqualTo(owner));
            State = state;
        }
        public bool TryAcceptEvent(string sessionId, Event occurrence)
        {
            Assert.That(Environment.CurrentManagedThreadId, Is.EqualTo(owner));
            EventCalls++;
            Session = sessionId;
            Event = occurrence;
            return Accept;
        }
    }

    private sealed class FixedClock(double now) : IMonotonicClock { public double Now => now; }

    private sealed class LinuxClock : IMonotonicClock
    {
        [StructLayout(LayoutKind.Sequential)]
        private struct Timespec { public long Seconds; public long Nanoseconds; }
        [DllImport("libc", SetLastError = true)]
        private static extern int clock_gettime(int id, out Timespec time);
        public double Now
        {
            get
            {
                if (!OperatingSystem.IsLinux() || clock_gettime(1, out var time) != 0)
                    throw new InvalidOperationException("Linux CLOCK_MONOTONIC unavailable");
                return time.Seconds + time.Nanoseconds / 1e9;
            }
        }
    }

    private sealed class Fixture : IDisposable
    {
        private readonly Process process;
        private readonly Task<string> stderr;
        public JsonElement Ready { get; }
        public Fixture()
        {
            string python = Environment.GetEnvironmentVariable("GESTURE_E2E_PYTHON")
                ?? throw new InvalidOperationException("Set GESTURE_E2E_PYTHON to the fixture venv Python");
            string script = Environment.GetEnvironmentVariable("GESTURE_E2E_FIXTURE")
                ?? throw new InvalidOperationException("Set GESTURE_E2E_FIXTURE to fixture.py (absolute path)");
            var start = new ProcessStartInfo(python) {
                UseShellExecute = false, RedirectStandardInput = true,
                RedirectStandardOutput = true, RedirectStandardError = true,
            };
            start.ArgumentList.Add("-u");
            start.ArgumentList.Add(script);
            process = Process.Start(start);
            stderr = process.StandardError.ReadToEndAsync();
            try
            {
                Ready = Read();
                Assert.That(Ready.GetProperty("ready").GetBoolean(), Is.True);
            }
            catch { Dispose(); throw; }
        }
        private JsonElement Read()
        {
            string line = process.StandardOutput.ReadLineAsync()
                .WaitAsync(TimeSpan.FromSeconds(20)).GetAwaiter().GetResult();
            if (line == null) throw new InvalidOperationException("Fixture exited: " +
                stderr.WaitAsync(TimeSpan.FromSeconds(5)).GetAwaiter().GetResult());
            using var document = JsonDocument.Parse(line);
            return document.RootElement.Clone();
        }
        public JsonElement Command(string command)
        {
            process.StandardInput.WriteLine(JsonSerializer.Serialize(new { command }));
            process.StandardInput.Flush();
            return Read();
        }
        public void Dispose()
        {
            try
            {
                process.StandardInput.Close(); // EOF shuts down relay and source.
                if (!process.WaitForExit(5000))
                {
                    process.Kill(entireProcessTree: true);
                    if (!process.WaitForExit(5000)) throw new TimeoutException("Fixture cleanup timed out");
                    Assert.Fail("Fixture required forced termination");
                }
                string errors = stderr.WaitAsync(TimeSpan.FromSeconds(5)).GetAwaiter().GetResult();
                Assert.That(process.ExitCode, Is.Zero, errors);
                if (errors.Length > 0) TestContext.Progress.WriteLine(errors);
            }
            finally { process.Dispose(); }
        }
    }
}
