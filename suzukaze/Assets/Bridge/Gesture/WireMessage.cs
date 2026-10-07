using System;
using System.IO;
using System.Net.WebSockets;
using System.Threading;
using System.Threading.Tasks;
using Google.Protobuf;
using Suzukaze.Bridge.Protocol;
using Suzukaze.Gesture.Protocol;
using GestureAction = Suzukaze.Gesture.Protocol.Action;

namespace Suzukaze.Gesture
{
    public static class WireMessage
    {
        public const int MaxBytes = 8192;
        private static bool Finite(double x) => !double.IsNaN(x) && !double.IsInfinity(x);

        public static bool ValidPhase(GestureAction action, Phase phase) => action switch
        {
            GestureAction.Ramune => phase == Phase.Forming || phase == Phase.Ready
                || phase == Phase.Opened || phase == Phase.WaitRelease,
            GestureAction.Uchimizu => phase == Phase.Ready || phase == Phase.Swing,
            GestureAction.Fanning or GestureAction.Relaxing => phase == Phase.Active,
            GestureAction.Bow => phase == Phase.Hold,
            _ => false
        };

        public static void Validate(GestureEnvelope message)
        {
            if (message.Version != 1 || string.IsNullOrEmpty(message.SessionId))
                throw new InvalidDataException("Unsupported envelope");
            var s = message.State;
            var e = message.Event;
            if (s != null)
            {
                if (s.Sequence == 0 || !Finite(s.SentAt) || !Finite(s.StaleTimeout)
                    || s.StaleTimeout <= 0 || s.Gesture == ContinuousGesture.Unspecified
                    || !Enum.IsDefined(typeof(ContinuousGesture), s.Gesture)
                    || (s.HasObservedAt && !Finite(s.ObservedAt))
                    || (s.HasSourceTimestamp && !Finite(s.SourceTimestamp)))
                    throw new InvalidDataException("Invalid state");
                if (s.HasAction != s.HasPhase || (s.HasPhase &&
                    (!s.Fresh || !s.Tracking || !ValidPhase(s.Action, s.Phase))))
                    throw new InvalidDataException("Invalid phase");
            }
            else if (e != null)
            {
                if (e.EventId == 0 || e.Gesture == OccurrenceGesture.Unspecified
                    || !Enum.IsDefined(typeof(OccurrenceGesture), e.Gesture)
                    || !Finite(e.OccurredAt) || !Finite(e.ExpiresAt) || e.ExpiresAt <= e.OccurredAt
                    || (e.HasSourceTimestamp && !Finite(e.SourceTimestamp)))
                    throw new InvalidDataException("Invalid event");
            }
            else throw new InvalidDataException("Receiver expects state or event");
        }

        // GestureEnvelope を、WebSocket に流す BridgeEnvelope に包む。
        public static byte[] Wrap(GestureEnvelope envelope) =>
            new BridgeEnvelope { Gesture = envelope }.ToByteArray();

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
                if (!part.EndOfMessage) continue;
                if (length == 0) throw new InvalidDataException("Empty message");
                var bridge = BridgeEnvelope.Parser.ParseFrom(bytes, 0, length);
                if (bridge.PayloadCase == BridgeEnvelope.PayloadOneofCase.FanState)
                    return new ReceivedMessage(bridge.FanState, arrival);
                if (bridge.PayloadCase != BridgeEnvelope.PayloadOneofCase.Gesture)
                    throw new InvalidDataException("Receiver expects gesture or fan state");
                Validate(bridge.Gesture);
                return new ReceivedMessage(bridge.Gesture, arrival);
            }
        }
    }

    public sealed class ReceivedMessage
    {
        // ジェスチャーのときだけ Envelope、ファンの状態のときだけ FanState が入る。
        public GestureEnvelope Envelope { get; }
        public FanState FanState { get; }
        public double ReceivedAt { get; }
        public ReceivedMessage(GestureEnvelope envelope, double receivedAt)
        { Envelope = envelope; ReceivedAt = receivedAt; }
        public ReceivedMessage(FanState fanState, double receivedAt)
        { FanState = fanState; ReceivedAt = receivedAt; }
    }
}
