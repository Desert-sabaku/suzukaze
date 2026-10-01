using System;
using System.IO;
using System.Net.WebSockets;
using System.Threading;
using System.Threading.Tasks;
using Suzukaze.Gesture.Protocol;

namespace Suzukaze.Gesture.Delivery
{
    public static class WireMessage
    {
        public const int MaxBytes = 8192;
        private static bool Finite(double x) => !double.IsNaN(x) && !double.IsInfinity(x);

        public static void Validate(GestureEnvelope message)
        {
            if (message.Version != 1 || string.IsNullOrEmpty(message.SessionId))
                throw new InvalidDataException("Unsupported envelope");
            var s = message.State;
            var e = message.Event;
            if (s != null)
            {
                if (s.Sequence == 0 || !Finite(s.SentAt) || !Finite(s.StaleTimeout)
                    || s.StaleTimeout <= 0 || (int)s.Gesture < 1 || (int)s.Gesture > 3
                    || (s.HasObservedAt && !Finite(s.ObservedAt))
                    || (s.HasSourceTimestamp && !Finite(s.SourceTimestamp)))
                    throw new InvalidDataException("Invalid state");
            }
            else if (e != null)
            {
                if (e.EventId == 0 || (int)e.Gesture < 1 || (int)e.Gesture > 2
                    || !Finite(e.OccurredAt) || !Finite(e.ExpiresAt) || e.ExpiresAt <= e.OccurredAt
                    || (e.HasSourceTimestamp && !Finite(e.SourceTimestamp)))
                    throw new InvalidDataException("Invalid event");
            }
            else throw new InvalidDataException("Receiver expects state or event");
        }

        // One protobuf envelope per binary WebSocket message; no TCP length header.
        // Timestamp is captured immediately after the final ReceiveAsync completes.
        public static async Task<ReceivedMessage> ReceiveAsync(
            WebSocket socket, IMonotonicClock clock, CancellationToken cancellation)
        {
            // One sentinel byte detects oversize while permitting an empty final
            // continuation after exactly MaxBytes bytes of non-final fragments.
            var bytes = new byte[MaxBytes + 1];
            int length = 0;
            while (true)
            {
                var part = await socket.ReceiveAsync(
                    new ArraySegment<byte>(bytes, length, bytes.Length - length), cancellation)
                    .ConfigureAwait(false);
                double arrival = clock.Now;
                if (part.MessageType == WebSocketMessageType.Close) return null;
                if (part.MessageType != WebSocketMessageType.Binary)
                    throw new InvalidDataException("Expected binary WebSocket message");
                length += part.Count;
                if (length > MaxBytes) throw new InvalidDataException("Message exceeds 8192 bytes");
                if (part.EndOfMessage)
                {
                    if (length == 0) throw new InvalidDataException("Empty message");
                    var envelope = GestureEnvelope.Parser.ParseFrom(bytes, 0, length);
                    Validate(envelope);
                    return new ReceivedMessage(envelope, arrival);
                }
            }
        }
    }

    public sealed class ReceivedMessage
    {
        public GestureEnvelope Envelope { get; }
        public double ReceivedAt { get; }
        public ReceivedMessage(GestureEnvelope envelope, double receivedAt)
        { Envelope = envelope; ReceivedAt = receivedAt; }
    }
}
