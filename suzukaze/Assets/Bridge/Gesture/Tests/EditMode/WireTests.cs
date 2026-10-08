using System;
using System.Collections.Generic;
using System.IO;
using System.Net.WebSockets;
using System.Threading;
using System.Threading.Tasks;
using Google.Protobuf;
using NUnit.Framework;
using Suzukaze.Bridge.Protocol;
using Suzukaze.Gesture.Protocol;
using GestureAction = Suzukaze.Gesture.Protocol.Action;

namespace Suzukaze.Gesture.Tests
{
    public class WireTests
    {
        private sealed class FragmentSocket : WebSocket
        {
            private readonly Queue<byte[]> fragments = new Queue<byte[]>();
            public WebSocketMessageType Type = WebSocketMessageType.Binary;
            public System.Action Received;
            public FragmentSocket(params byte[][] parts) { foreach (var part in parts) fragments.Enqueue(part); }
            public override Task<WebSocketReceiveResult> ReceiveAsync(ArraySegment<byte> buffer, CancellationToken cancellation)
            {
                cancellation.ThrowIfCancellationRequested();
                var bytes = fragments.Dequeue();
                if (bytes.Length > buffer.Count) throw new Exception("Test fragment exceeds receive buffer");
                Array.Copy(bytes, 0, buffer.Array, buffer.Offset, bytes.Length);
                Received?.Invoke();
                return Task.FromResult(new WebSocketReceiveResult(bytes.Length, Type, fragments.Count == 0));
            }
            public override WebSocketCloseStatus? CloseStatus => null;
            public override string CloseStatusDescription => null;
            public override WebSocketState State => WebSocketState.Open;
            public override string SubProtocol => null;
            public override void Abort() { }
            public override void Dispose() { }
            public override Task CloseAsync(WebSocketCloseStatus status, string description, CancellationToken token) => Task.CompletedTask;
            public override Task CloseOutputAsync(WebSocketCloseStatus status, string description, CancellationToken token) => Task.CompletedTask;
            public override Task SendAsync(ArraySegment<byte> buffer, WebSocketMessageType type, bool end, CancellationToken token) => throw new NotSupportedException();
        }

        [Test]
        public async Task FragmentedMessageCapturesFinalReceiveTime()
        {
            byte[] bytes = WireMessage.Wrap(DeliveryTests.Occurrence().Envelope);
            var fragments = new byte[bytes.Length][];
            for (int i = 0; i < bytes.Length; i++) fragments[i] = new[] { bytes[i] };
            var clock = new TestClock();
            using (var socket = new FragmentSocket(fragments))
            {
                socket.Received = () => clock.Time += .01;
                var result = await WireMessage.ReceiveAsync(socket, clock, CancellationToken.None);
                Assert.That(result.Envelope.Event.EventId, Is.EqualTo(1));
                Assert.That(result.ReceivedAt, Is.EqualTo(clock.Time));
            }
        }

        [Test]
        public async Task ExactBoundAndEmptyFinalFragmentAreAllowed()
        {
            var envelope = DeliveryTests.Occurrence().Envelope;
            // Grow session until the wire message (BridgeEnvelope) is exactly the bound.
            envelope.SessionId = new string('s', 8153);
            while (WireMessage.Wrap(envelope).Length < 8192) envelope.SessionId += "s";
            while (WireMessage.Wrap(envelope).Length > 8192) envelope.SessionId = envelope.SessionId.Substring(1);
            using (var socket = new FragmentSocket(WireMessage.Wrap(envelope), new byte[0]))
            {
                var result = await WireMessage.ReceiveAsync(socket, new TestClock(), CancellationToken.None);
                Assert.That(WireMessage.Wrap(result.Envelope).Length, Is.EqualTo(8192));
            }
        }

        [Test]
        public void InvalidTransportInputsAreRejected()
        {
            foreach (var socket in new[] {
                new FragmentSocket(new byte[8192], new byte[1]),
                new FragmentSocket(new byte[8193]),
                new FragmentSocket(new byte[0]),
                new FragmentSocket(WireMessage.Wrap(DeliveryTests.Occurrence().Envelope)) { Type = WebSocketMessageType.Text }
            })
            using (socket)
                Assert.ThrowsAsync<InvalidDataException>(async () =>
                    await WireMessage.ReceiveAsync(socket, new TestClock(), CancellationToken.None));
            using (var socket = new FragmentSocket(new byte[] { 0x80 }))
                Assert.ThrowsAsync<InvalidProtocolBufferException>(async () =>
                    await WireMessage.ReceiveAsync(socket, new TestClock(), CancellationToken.None));
        }

        [Test]
        public async Task CloseAndCancellationAreHandled()
        {
            using (var socket = new FragmentSocket(new byte[0]) { Type = WebSocketMessageType.Close })
                Assert.That(await WireMessage.ReceiveAsync(socket, new TestClock(), CancellationToken.None), Is.Null);
            using (var socket = new FragmentSocket(new byte[0]))
                Assert.CatchAsync<OperationCanceledException>(async () =>
                    await WireMessage.ReceiveAsync(socket, new TestClock(), new CancellationToken(true)));
        }

        [Test]
        public void EnvelopeValidationRejectsUnknownEnumsAndNonFiniteMetadata()
        {
            var message = DeliveryTests.State().Envelope;
            message.State.Gesture = (ContinuousGesture)99;
            Assert.Throws<InvalidDataException>(() => WireMessage.Validate(message));
            message = DeliveryTests.State().Envelope; message.State.ObservedAt = double.NaN;
            Assert.Throws<InvalidDataException>(() => WireMessage.Validate(message));
            message = DeliveryTests.Occurrence().Envelope; message.Event.SourceTimestamp = double.PositiveInfinity;
            Assert.Throws<InvalidDataException>(() => WireMessage.Validate(message));
            message = DeliveryTests.Occurrence().Envelope; message.Version = 2;
            Assert.Throws<InvalidDataException>(() => WireMessage.Validate(message));
            message = new GestureEnvelope { Version = 1, SessionId = "s", Ack = new Ack() };
            Assert.Throws<InvalidDataException>(() => WireMessage.Validate(message));
        }

        [Test]
        public void BowStateIsAccepted()
        {
            var message = DeliveryTests.State().Envelope;
            message.State.Gesture = ContinuousGesture.Bow;
            Assert.DoesNotThrow(() => WireMessage.Validate(message));
        }

        [TestCase(0)]
        [TestCase(.5)]
        [TestCase(1)]
        public void AccuracyPreservesPresence(double accuracy)
        {
            var message = DeliveryTests.State().Envelope;
            message.State.Gesture = ContinuousGesture.Bow;
            Assert.That(message.State.HasActionAccuracy, Is.False);
            message.State.ActionAccuracy = accuracy;
            var restored = GestureEnvelope.Parser.ParseFrom(message.ToByteArray());
            WireMessage.Validate(restored);
            Assert.That(restored.State.HasActionAccuracy, Is.True);
            Assert.That(restored.State.ActionAccuracy, Is.EqualTo(accuracy));
            restored.State.Gesture = ContinuousGesture.None;
            Assert.Throws<InvalidDataException>(() => WireMessage.Validate(restored));
        }

        [TestCase(-.1)]
        [TestCase(1.1)]
        [TestCase(double.NaN)]
        [TestCase(double.PositiveInfinity)]
        public void InvalidAccuracyIsRejected(double accuracy)
        {
            var message = DeliveryTests.State().Envelope;
            message.State.Gesture = ContinuousGesture.Bow;
            message.State.ActionAccuracy = accuracy;
            Assert.Throws<InvalidDataException>(() => WireMessage.Validate(message));
            message = DeliveryTests.Occurrence().Envelope;
            message.Event.ActionAccuracy = accuracy;
            Assert.Throws<InvalidDataException>(() => WireMessage.Validate(message));
        }

        [Test]
        public void PhaseRequiresBothFieldsAndFreshTracking()
        {
            var message = DeliveryTests.State().Envelope;
            message.State.Action = GestureAction.Ramune;
            Assert.Throws<InvalidDataException>(() => WireMessage.Validate(message));
            message.State.Phase = Phase.Ready;
            Assert.DoesNotThrow(() => WireMessage.Validate(message));
            message.State.Tracking = false;
            Assert.Throws<InvalidDataException>(() => WireMessage.Validate(message));
        }

        [TestCase(GestureAction.Ramune, Phase.Unspecified)]
        [TestCase(GestureAction.Ramune, Phase.Idle)]
        [TestCase(GestureAction.Ramune, Phase.Active)]
        [TestCase(GestureAction.Uchimizu, Phase.Opened)]
        [TestCase(GestureAction.Fanning, Phase.Ready)]
        [TestCase(GestureAction.Relaxing, Phase.Hold)]
        [TestCase(GestureAction.Bow, Phase.Ready)]
        [TestCase(GestureAction.Ramune, (Phase)99)]
        [TestCase(GestureAction.None, Phase.Ready)]
        [TestCase(GestureAction.Unspecified, Phase.Ready)]
        [TestCase((GestureAction)99, Phase.Ready)]
        [TestCase(GestureAction.Fanning, Phase.Position)]
        [TestCase(GestureAction.Relaxing, Phase.Dwell)]
        [TestCase(GestureAction.Bow, Phase.Bending)]
        [TestCase(GestureAction.Bow, Phase.Returning)]
        public void InvalidActionPhasePairsAreRejected(GestureAction action, Phase phase)
        {
            var message = DeliveryTests.State().Envelope;
            message.State.Action = action;
            message.State.Phase = phase;
            Assert.Throws<InvalidDataException>(() => WireMessage.Validate(message));
        }

        [TestCase(GestureAction.Ramune, Phase.Forming)]
        [TestCase(GestureAction.Ramune, Phase.Ready)]
        [TestCase(GestureAction.Ramune, Phase.Opened)]
        [TestCase(GestureAction.Ramune, Phase.WaitRelease)]
        [TestCase(GestureAction.Uchimizu, Phase.Ready)]
        [TestCase(GestureAction.Uchimizu, Phase.Swing)]
        [TestCase(GestureAction.Fanning, Phase.Active)]
        [TestCase(GestureAction.Relaxing, Phase.Active)]
        [TestCase(GestureAction.Bow, Phase.Hold)]
        public void ValidActionPhasePairsAreAccepted(GestureAction action, Phase phase)
        {
            var message = DeliveryTests.State().Envelope;
            message.State.Action = action;
            message.State.Phase = phase;
            Assert.DoesNotThrow(() => WireMessage.Validate(message));
        }

        [Test]
        public void PythonGoldenEventProducesGoldenAcceptedAck()
        {
            // Copied from schema-owned messages.json. Full fixture parity is also
            // exercised by the portable runner without Unity JSON number coercion.
            var bytes = Hex("08011207666978747572655a1608011001190000000000002440210000000000002640");
            var message = GestureEnvelope.Parser.ParseFrom(bytes);
            WireMessage.Validate(message);
            var policy = new DeliveryPolicy(); policy.UseSession(message.SessionId);
            var ack = policy.AdoptEvent(message.Event, 10, new TestSink());
            Assert.That(ack.ToByteArray(), Is.EqualTo(Hex("0801120766697874757265620408011001")));
        }

        public static byte[] Hex(string text)
        {
            var result = new byte[text.Length / 2];
            for (int i = 0; i < result.Length; i++) result[i] = Convert.ToByte(text.Substring(i * 2, 2), 16);
            return result;
        }

        [Test]
        public async Task FanStateIsReceivedWithoutAGestureEnvelope()
        {
            var state = new FanState();
            state.Readings.Add(new FanReading { Channel = Suzukaze.Fan.Protocol.FanChannel.RightFront, Value = 9 });
            var bytes = new BridgeEnvelope { FanState = state }.ToByteArray();
            using (var socket = new FragmentSocket(bytes))
            {
                var result = await WireMessage.ReceiveAsync(socket, new TestClock(), CancellationToken.None);
                Assert.That(result.Envelope, Is.Null);
                Assert.That(result.FanState.Readings[0].Value, Is.EqualTo(9));
            }
        }

        [Test]
        public void FanCommandIsNotAcceptedByTheReceiver()
        {
            var bytes = new BridgeEnvelope { FanCommand = new Suzukaze.Fan.Protocol.Fan() }.ToByteArray();
            using (var socket = new FragmentSocket(bytes))
                Assert.ThrowsAsync<InvalidDataException>(async () =>
                    await WireMessage.ReceiveAsync(socket, new TestClock(), CancellationToken.None));
        }
    }
}
