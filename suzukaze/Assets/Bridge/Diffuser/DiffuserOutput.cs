using System.Collections.Concurrent;
using Google.Protobuf;
using Suzukaze.Bridge.Protocol;
using Suzukaze.Diffuser.Protocol;

namespace Suzukaze.Diffuser
{
    // ディフューザーへの指示の窓口。bridge と mcu に接続している間は bridge へ送り、
    // それ以外は DiffuserMock に記録する。ピンは bridge が DiffuserChannel から決める。
    public sealed class DiffuserOutput
    {
        public static DiffuserOutput Instance { get; private set; } = new();

        private readonly ConcurrentQueue<byte[]> outgoing = new();

        public DiffuserMock Mock { get; } = new();

        // bridge と mcu の両方に接続しているか。GestureReceiverBehaviour が更新する。
        public bool Connected { get; set; }

        public static void ResetInstance() => Instance = new DiffuserOutput();

        /// <summary>
        /// ディフューザーの電源ボタンを[durationMs]ミリ秒押す(トグル式)。
        /// </summary>
        public void Press(DiffuserChannel channel, ulong durationMs = 200)
        {
            if (!Connected)
            {
                Mock.Press(channel);
                return;
            }
            outgoing.Enqueue(new BridgeEnvelope
            {
                DiffuserPress = new DiffuserPress { Channel = channel, DurationMs = durationMs }
            }.ToByteArray());
        }

        // bridge へ送る次の電文。なければ null。トランスポートが呼ぶ。
        public byte[] TakeOutgoing() => outgoing.TryDequeue(out var bytes) ? bytes : null;
    }
}
