using System;
using System.Net.WebSockets;
using System.Threading;
using System.Threading.Tasks;

namespace Suzukaze.Core
{
    public sealed class Transceiver
    {
        private readonly ITransceiverHandler handler;
        public string LastError => Volatile.Read(ref lastError);
        private string lastError;

        public Transceiver(ITransceiverHandler handler)
        { this.handler = handler; }

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
                        token = handler.Begin();
                        if (token == 0) return;
                        Volatile.Write(ref lastError, null);
                        var receive = ReceiveLoop(socket, token, connection.Token);
                        var send = SendLoop(socket, token, connection.Token);
                        // Also wake if Update overflows while both socket operations
                        // are blocked. No dependence on another network packet.
                        await Task.WhenAny(receive, send, handler.WaitForEndAsync(token)).ConfigureAwait(false);
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
                        if (token != 0) handler.End(token);
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
            while (handler.IsConnected(token))
            {
                if (!await handler.ReceiveAsync(socket, token, cancellation).ConfigureAwait(false)) return;
            }
        }

        private async Task SendLoop(WebSocket socket, long token, CancellationToken cancellation)
        {
            // The only SendAsync caller. Polling also notices main-thread overflow
            // while ReceiveAsync is idle, without an unbounded task/signal queue.
            while (handler.IsConnected(token))
            {
                var bytes = handler.TakeOutgoing(token);
                if (bytes == null) { await Task.Delay(10, cancellation).ConfigureAwait(false); continue; }
                await socket.SendAsync(new ArraySegment<byte>(bytes), WebSocketMessageType.Binary,
                    true, cancellation).ConfigureAwait(false);
            }
        }
    }
}
