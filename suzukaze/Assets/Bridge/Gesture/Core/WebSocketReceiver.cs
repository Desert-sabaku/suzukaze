using System;
using System.Net.WebSockets;
using System.Threading;
using System.Threading.Tasks;
using Google.Protobuf;

namespace Suzukaze.Gesture.Receiver
{
    public sealed class WebSocketReceiver
    {
        private readonly ReceiverHandoff handoff;
        private readonly IMonotonicClock clock;
        public string LastError => Volatile.Read(ref lastError);
        private string lastError;

        public WebSocketReceiver(ReceiverHandoff handoff, IMonotonicClock clock)
        { this.handoff = handoff; this.clock = clock; }

        public async Task RunAsync(Uri uri, CancellationToken stopping)
        {
            if (!uri.IsLoopback || (uri.Scheme != "ws" && uri.Scheme != "wss"))
                throw new ArgumentException("Use a same-PC loopback WebSocket endpoint", nameof(uri));
            while (!stopping.IsCancellationRequested)
            {
                long token = 0;
                using (var socket = new ClientWebSocket())
                using (var connection = CancellationTokenSource.CreateLinkedTokenSource(stopping))
                {
                    try
                    {
                        connection.CancelAfter(TimeSpan.FromSeconds(5));
                        await socket.ConnectAsync(uri, connection.Token).ConfigureAwait(false);
                        connection.CancelAfter(Timeout.Infinite);
                        token = handoff.BeginConnection();
                        if (token == 0) return;
                        Volatile.Write(ref lastError, null);
                        Task receive = ReceiveLoop(socket, token, connection.Token);
                        Task send = SendLoop(socket, token, connection.Token);
                        // Also wake if Update overflows while both socket operations
                        // are blocked. No dependence on another network packet.
                        await Task.WhenAny(receive, send, handoff.WaitForDisconnectAsync(token)).ConfigureAwait(false);
                        connection.Cancel();
                        socket.Abort();
                        // Observe both tasks before disposing the socket/CTS.
                        await Task.WhenAll(receive, send).ConfigureAwait(false);
                    }
                    catch (Exception error)
                    {
                        if (!stopping.IsCancellationRequested)
                            Volatile.Write(ref lastError, error.GetType().Name + ": " + error.Message);
                    }
                    finally
                    {
                        if (token != 0) handoff.Disconnect(token);
                        connection.Cancel();
                        socket.Abort();
                    }
                }
                try { await Task.Delay(500, stopping).ConfigureAwait(false); }
                catch (OperationCanceledException) { break; }
            }
        }

        private async Task ReceiveLoop(WebSocket socket, long token, CancellationToken cancellation)
        {
            while (handoff.IsConnected(token))
            {
                var message = await WireMessage.ReceiveAsync(socket, clock, cancellation).ConfigureAwait(false);
                if (message == null || !handoff.Publish(token, message)) return;
            }
        }

        private async Task SendLoop(WebSocket socket, long token, CancellationToken cancellation)
        {
            // The only SendAsync caller. Polling also notices main-thread overflow
            // while ReceiveAsync is idle, without an unbounded task/signal queue.
            while (handoff.IsConnected(token))
            {
                var ack = handoff.TakeAck(token);
                if (ack == null) { await Task.Delay(10, cancellation).ConfigureAwait(false); continue; }
                byte[] bytes = ack.ToByteArray();
                if (bytes.Length > WireMessage.MaxBytes) throw new InvalidOperationException("ACK too large");
                await socket.SendAsync(new ArraySegment<byte>(bytes), WebSocketMessageType.Binary,
                    true, cancellation).ConfigureAwait(false);
            }
        }
    }
}
