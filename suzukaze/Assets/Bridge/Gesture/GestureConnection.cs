using System;
using System.Net.WebSockets;
using System.Threading;
using System.Threading.Tasks;
using Google.Protobuf;
using Suzukaze.Core;

namespace Suzukaze.Gesture
{
    // Transceiver に、ジェスチャーの受け渡し(ReceiverHandoff)と電文の検証(WireMessage)をつなぐ。
    public sealed class GestureConnection : ITransceiverHandler
    {
        private readonly ReceiverHandoff handoff;
        private readonly IMonotonicClock clock;

        public GestureConnection(ReceiverHandoff handoff, IMonotonicClock clock)
        { this.handoff = handoff; this.clock = clock; }

        public long Begin() => handoff.BeginConnection();

        public bool IsConnected(long token) => handoff.IsConnected(token);

        public void End(long token) => handoff.Disconnect(token);

        public Task WaitForEndAsync(long token) => handoff.WaitForDisconnectAsync(token);

        public async Task<bool> ReceiveAsync(WebSocket socket, long token, CancellationToken cancellation)
        {
            var message = await WireMessage.ReceiveAsync(socket, clock, cancellation).ConfigureAwait(false);
            return message != null && handoff.Publish(token, message);
        }

        public byte[] TakeOutgoing(long token)
        {
            var ack = handoff.TakeAck(token);
            if (ack == null) return null;
            var bytes = ack.ToByteArray();
            if (bytes.Length > WireMessage.MaxBytes) throw new InvalidOperationException("ACK too large");
            return bytes;
        }
    }
}
