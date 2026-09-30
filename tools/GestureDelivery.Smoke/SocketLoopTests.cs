using System;
using System.Net;
using System.Net.Sockets;
using System.Net.WebSockets;
using System.Threading;
using System.Threading.Tasks;
using Google.Protobuf;
using NUnit.Framework;
using Suzukaze.Gesture.Delivery;
using Suzukaze.Gesture.Delivery.Tests;
using Suzukaze.Gesture.Protocol;

public class SocketLoopTests
{
    [TestCase(false)]
    [TestCase(true)]
    public async Task RealClientReconnectsDeduplicatesAndCancelsIdleReceive(bool invalidText)
    {
        var portProbe = new TcpListener(IPAddress.Loopback, 0);
        portProbe.Start(); int port = ((IPEndPoint)portProbe.LocalEndpoint).Port; portProbe.Stop();
        using var listener = new HttpListener();
        listener.Prefixes.Add($"http://127.0.0.1:{port}/"); listener.Start();
        using var stop = new CancellationTokenSource(TimeSpan.FromSeconds(15));
        var handoff = new ReceiverHandoff(); var clock = new TestClock(); var sink = new TestSink();
        var receiver = new WebSocketReceiver(handoff, clock);
        Task worker = receiver.RunAsync(new Uri($"ws://127.0.0.1:{port}/"), stop.Token);
        try
        {
            for (int attempt = 0; attempt < 2; attempt++)
            {
                HttpListenerContext context;
                try { context = await listener.GetContextAsync().WaitAsync(stop.Token); }
                catch (OperationCanceledException)
                { throw new AssertionException($"Connection {attempt} timed out; receiver: {receiver.LastError}"); }
                using var server = (await context.AcceptWebSocketAsync(null)).WebSocket;
                byte[] payload = DeliveryTests.Occurrence().Envelope.ToByteArray();
                await server.SendAsync(new ArraySegment<byte>(payload, 0, 3), WebSocketMessageType.Binary, false, stop.Token);
                await server.SendAsync(new ArraySegment<byte>(payload, 3, payload.Length - 3), WebSocketMessageType.Binary, true, stop.Token);
                var ackBytes = new byte[8192];
                Task<WebSocketReceiveResult> received = server.ReceiveAsync(new ArraySegment<byte>(ackBytes), stop.Token);
                while (!received.IsCompleted)
                {
                    handoff.Tick(clock, sink);
                    await Task.Delay(5, stop.Token);
                }
                var result = await received;
                Assert.That(result.MessageType, Is.EqualTo(WebSocketMessageType.Binary));
                Assert.That(result.EndOfMessage, Is.True);
                var ack = GestureEnvelope.Parser.ParseFrom(ackBytes, 0, result.Count);
                Assert.That(ack.Ack.Status, Is.EqualTo(attempt == 0 ? AckStatus.Accepted : AckStatus.Duplicate));
                Assert.That(sink.Calls, Is.EqualTo(1));
                if (attempt == 0)
                {
                    if (invalidText)
                        await server.SendAsync(new ArraySegment<byte>(new byte[] { 65 }), WebSocketMessageType.Text, true, stop.Token);
                    else
                        await server.CloseOutputAsync(WebSocketCloseStatus.NormalClosure, "reconnect test", stop.Token);
                }
                else
                {
                    // Client is blocked in ReceiveAsync, no further server traffic.
                    stop.Cancel();
                    await worker.WaitAsync(TimeSpan.FromSeconds(2));
                }
            }
        }
        finally
        {
            stop.Cancel(); listener.Stop();
            await worker.WaitAsync(TimeSpan.FromSeconds(2));
        }
    }
}
