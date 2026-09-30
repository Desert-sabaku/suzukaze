using System;
using System.Collections.Generic;
using System.IO;
using System.Net.WebSockets;
using System.Threading;
using System.Threading.Tasks;
using Google.Protobuf;
using NUnit.Framework;
using Suzukaze.Gesture.Protocol;

namespace Suzukaze.Gesture.Delivery.Tests
{
    public class WireTests
    {
        private sealed class FragmentSocket : WebSocket
        {
            private readonly Queue<byte[]> fragments = new Queue<byte[]>();
            public WebSocketMessageType Type = WebSocketMessageType.Binary;
            public Action Received;
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
            byte[] bytes = DeliveryTests.Occurrence().Envelope.ToByteArray();
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
            // Grow session until the serialized envelope is exactly the bound.
            envelope.SessionId = new string('s', 8153);
            while (envelope.CalculateSize() < 8192) envelope.SessionId += "s";
            while (envelope.CalculateSize() > 8192) envelope.SessionId = envelope.SessionId.Substring(1);
            using (var socket = new FragmentSocket(envelope.ToByteArray(), new byte[0]))
            {
                var result = await WireMessage.ReceiveAsync(socket, new TestClock(), CancellationToken.None);
                Assert.That(result.Envelope.CalculateSize(), Is.EqualTo(8192));
            }
        }

        [Test]
        public void InvalidTransportInputsAreRejected()
        {
            foreach (var socket in new[] {
                new FragmentSocket(new byte[8192], new byte[1]),
                new FragmentSocket(new byte[8193]),
                new FragmentSocket(new byte[0]),
                new FragmentSocket(DeliveryTests.Occurrence().Envelope.ToByteArray()) { Type = WebSocketMessageType.Text }
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
                Assert.ThrowsAsync<OperationCanceledException>(async () =>
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
    }
}
