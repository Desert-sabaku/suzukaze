using System;
using System.Net.WebSockets;
using System.Threading;
using System.Threading.Tasks;
using Google.Protobuf;
using Suzukaze.Bridge.Protocol;
using Suzukaze.Core;

namespace Suzukaze.Gesture
{
    // Transceiver に、ジェスチャーの受け渡し(ReceiverHandoff)と電文の検証(WireMessage)をつなぐ。
    public sealed class GestureConnection : ITransceiverHandler
    {
        private readonly ReceiverHandoff handoff;
        private readonly IMonotonicClock clock;

        // ファンは同じ WebSocket に載る。ファンの出入りは、呼び出し側が渡す関数で受け渡す。
        private readonly Action<bool> onConnected;
        private readonly Action<FanState> onFanState;
        private readonly Func<byte[]> takeFanOutgoing;

        public GestureConnection(ReceiverHandoff handoff, IMonotonicClock clock,
            Action<bool> onConnected = null, Action<FanState> onFanState = null,
            Func<byte[]> takeFanOutgoing = null)
        {
            this.handoff = handoff; this.clock = clock;
            this.onConnected = onConnected; this.onFanState = onFanState;
            this.takeFanOutgoing = takeFanOutgoing;
        }

        public long Begin()
        {
            var token = handoff.BeginConnection();
            if (token != 0) onConnected?.Invoke(true);
            return token;
        }

        public bool IsConnected(long token) => handoff.IsConnected(token);

        public void End(long token)
        {
            handoff.Disconnect(token);
            onConnected?.Invoke(false);
        }

        public Task WaitForEndAsync(long token) => handoff.WaitForDisconnectAsync(token);

        public async Task<bool> ReceiveAsync(WebSocket socket, long token, CancellationToken cancellation)
        {
            var message = await WireMessage.ReceiveAsync(socket, clock, cancellation).ConfigureAwait(false);
            if (message == null) return false;
            if (message.FanState != null)
            {
                onFanState?.Invoke(message.FanState);
                return true;
            }
            return handoff.Publish(token, message);
        }

        public byte[] TakeOutgoing(long token)
        {
            var ack = handoff.TakeAck(token);
            if (ack == null) return takeFanOutgoing?.Invoke();
            var bytes = WireMessage.Wrap(ack);
            if (bytes.Length > WireMessage.MaxBytes) throw new InvalidOperationException("ACK too large");
            return bytes;
        }
    }
}
