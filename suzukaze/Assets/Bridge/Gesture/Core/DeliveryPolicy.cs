using System;
using System.Collections.Generic;
using Suzukaze.Gesture.Protocol;

namespace Suzukaze.Gesture.Receiver
{
    public interface IMonotonicClock { double Now { get; } }

    // All sink calls happen in the owner's Update. Returning true means the scene
    // has actually adopted the occurrence, not merely queued its transport bytes.
    public interface IGestureSink
    {
        void DeliverState(StateView state);
        bool TryAcceptEvent(string sessionId, Event occurrence);
    }

    public sealed class StateView
    {
        public string SessionId { get; internal set; }
        public ulong Sequence { get; internal set; }
        public double ReceivedAt { get; internal set; }
        public bool Fresh { get; internal set; }
        public bool Tracking { get; internal set; }
        public ContinuousGesture Gesture { get; internal set; } = ContinuousGesture.None;
        public string PhaseAction { get; internal set; }
        public string Phase { get; internal set; }
    }

    public sealed class DeliveryPolicy
    {
        private readonly int capacity;
        private readonly Dictionary<ulong, double> seen = new Dictionary<ulong, double>();
        private readonly List<ulong> expired = new List<ulong>();
        private string session;
        private ulong sequence;
        private State state;
        private double receivedAt;

        public DeliveryPolicy(int dedupCapacity = 1024)
        {
            if (dedupCapacity < 1) throw new ArgumentOutOfRangeException(nameof(dedupCapacity));
            capacity = dedupCapacity;
        }

        public void Disconnected() { state = null; }

        public void UseSession(string value)
        {
            if (value == session) return;
            session = value;
            sequence = 0;
            seen.Clear();
            state = null;
        }

        public void AdoptState(State value, double arrival)
        {
            if (value.Sequence <= sequence) return;
            sequence = value.Sequence;
            state = value.Clone();
            receivedAt = arrival;
        }

        public StateView Current(double now)
        {
            bool fresh = state != null && state.Fresh && state.HasObservedAt
                && state.ObservedAt <= now && state.SentAt <= now
                && now - state.ObservedAt < state.StaleTimeout
                && now - state.SentAt < state.StaleTimeout
                && now - receivedAt < state.StaleTimeout;
            bool tracking = fresh && state.Tracking;
            return new StateView {
                SessionId = session, Sequence = sequence, ReceivedAt = receivedAt,
                Fresh = fresh, Tracking = tracking,
                Gesture = tracking ? state.Gesture : ContinuousGesture.None,
                PhaseAction = tracking && state.HasPhaseAction ? state.PhaseAction : null,
                Phase = tracking && state.HasPhase ? state.Phase : null
            };
        }

        public GestureEnvelope AdoptEvent(Event value, double now, IGestureSink sink)
        {
            if (value.OccurredAt > now) throw new InvalidOperationException("Incompatible host clock");
            expired.Clear();
            foreach (var entry in seen)
                if (entry.Value <= now) expired.Add(entry.Key);
            foreach (ulong id in expired) seen.Remove(id);

            AckStatus status;
            if (now >= value.ExpiresAt) status = AckStatus.Expired;
            else if (seen.ContainsKey(value.EventId)) status = AckStatus.Duplicate;
            else
            {
                // Never evict a live decision: that could execute an occurrence twice.
                if (seen.Count >= capacity) throw new InvalidOperationException("Dedup capacity exceeded");
                // Reserve before calling application code. If it throws after an effect,
                // reconnect must not repeat the effect; no fabricated ACK is sent.
                seen.Add(value.EventId, value.ExpiresAt);
                status = sink != null && sink.TryAcceptEvent(session, value.Clone())
                    ? AckStatus.Accepted : AckStatus.Ignored;
            }
            return new GestureEnvelope {
                Version = 1, SessionId = session,
                Ack = new Ack { EventId = value.EventId, Status = status }
            };
        }
    }
}
