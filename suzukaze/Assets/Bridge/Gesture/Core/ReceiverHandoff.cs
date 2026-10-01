using System;
using System.Collections.Generic;
using System.Threading.Tasks;
using Suzukaze.Gesture.Protocol;

namespace Suzukaze.Gesture.Receiver
{
    // Network threads only publish and take ACKs. Tick is exclusively main-thread.
    // Generation guards also cover late disconnects from a superseded connection.
    public sealed class ReceiverHandoff
    {
        private readonly object gate = new object();
        private readonly Queue<ReceivedMessage> events = new Queue<ReceivedMessage>();
        private readonly Queue<GestureEnvelope> acks = new Queue<GestureEnvelope>();
        private readonly DeliveryPolicy policy;
        private readonly int capacity;
        private ReceivedMessage state;
        private string session;
        private long generation;
        private bool connected;
        private bool resetState = true;
        private bool suspended;
        private TaskCompletionSource<bool> disconnected;

        public ReceiverHandoff(int pendingCapacity = 64, int dedupCapacity = 1024)
            : this(new DeliveryPolicy(dedupCapacity), pendingCapacity)
        {
        }

        // History can outlive a connection owner. Its policy methods still belong
        // exclusively to the main thread; pending queues remain owner-local.
        public ReceiverHandoff(DeliveryPolicy history, int pendingCapacity = 64)
        {
            if (pendingCapacity < 1) throw new ArgumentOutOfRangeException(nameof(pendingCapacity));
            capacity = pendingCapacity;
            policy = history ?? throw new ArgumentNullException(nameof(history));
        }

        public long BeginConnection()
        {
            lock (gate)
            {
                if (suspended) return 0;
                disconnected?.TrySetResult(true);
                disconnected = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
                Clear();
                connected = true;
                session = null;
                return ++generation;
            }
        }

        private void Clear()
        { events.Clear(); acks.Clear(); state = null; resetState = true; }

        public void Suspend()
        {
            lock (gate) { suspended = true; ++generation; StopConnection(); }
        }

        public void Resume() { lock (gate) suspended = false; }

        public void Disconnect(long token)
        {
            lock (gate) if (token == generation) StopConnection();
        }

        private void StopConnection()
        {
            connected = false;
            Clear();
            disconnected?.TrySetResult(true);
        }

        public Task WaitForDisconnectAsync(long token)
        {
            lock (gate) return token == generation && connected
                ? disconnected.Task : Task.CompletedTask;
        }

        public bool IsConnected(long token)
        { lock (gate) return token == generation && connected; }

        public bool Publish(long token, ReceivedMessage message)
        {
            lock (gate)
            {
                if (token != generation || !connected) return false;
                WireMessage.Validate(message.Envelope);
                if (session != message.Envelope.SessionId)
                {
                    Clear();
                    session = message.Envelope.SessionId;
                }
                if (message.Envelope.State != null)
                {
                    if (state == null || message.Envelope.State.Sequence > state.Envelope.State.Sequence)
                        state = new ReceivedMessage(message.Envelope.Clone(), message.ReceivedAt);
                }
                else
                {
                    if (events.Count >= capacity) { StopConnection(); return false; }
                    events.Enqueue(new ReceivedMessage(message.Envelope.Clone(), message.ReceivedAt));
                }
                return true;
            }
        }

        public GestureEnvelope TakeAck(long token)
        {
            lock (gate) return token == generation && connected && acks.Count > 0
                ? acks.Dequeue() : null;
        }

        public void Tick(IMonotonicClock clock, IGestureSink sink)
        {
            lock (gate)
            {
                if (resetState) { policy.Disconnected(); resetState = false; }
                if (connected && session != null) policy.UseSession(session);
                try
                {
                    if (connected && state != null)
                    {
                        policy.AdoptState(state.Envelope.State, state.ReceivedAt);
                        state = null;
                    }
                    sink?.DeliverState(policy.Current(clock.Now));
                    while (connected && events.Count > 0)
                    {
                        // Reserve ACK capacity before asking the scene to adopt anything.
                        if (acks.Count >= capacity) throw new InvalidOperationException("ACK queue overflow");
                        var next = events.Dequeue();
                        acks.Enqueue(policy.AdoptEvent(next.Envelope.Event, clock.Now, sink));
                    }
                }
                catch
                {
                    StopConnection();
                    policy.Disconnected();
                    throw;
                }
            }
        }
    }
}
