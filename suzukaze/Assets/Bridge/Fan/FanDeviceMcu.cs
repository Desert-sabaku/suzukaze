using System.Collections.Concurrent;
using Google.Protobuf;
using Suzukaze.Bridge.Protocol;
using FanChannel = Suzukaze.Fan.Protocol.FanChannel;
using FanCommand = Suzukaze.Fan.Protocol.Fan;

namespace Suzukaze.Fan
{
    // 実機。unity_bridge 経由でマイコンに指示を送り、マイコンが返した、いまの出力を保つ。
    public sealed class FanDeviceMcu : IFanDevice
    {
        private readonly byte[] actual = new byte[FanOutput.FanCount];
        private readonly ConcurrentQueue<byte[]> outgoing = new();

        // firmware の PwmFade.value と同じ 8bit。
        public byte MinValue => 0;
        public byte MaxValue => 255;

        // bridge と mcu の両方に接続しているか。未実装なので、いまは常に false(テストだけが書き換える)。
        // TODO: 接続状態の変化で更新する
        public bool Connected { get; set; } = false;

        public void SetDuration(FanSide side, FanPosition position, byte value, ulong durationMs)
        {
            var command = new FanCommand
            {
                Channel = Channel(side, position),
                Value = value,
                DurationMs = durationMs
            };
            outgoing.Enqueue(new BridgeEnvelope { FanCommand = command }.ToByteArray());
        }

        // bridge へ送る次の電文。なければ null。トランスポートが呼ぶ。
        public byte[] TakeOutgoing() => outgoing.TryDequeue(out var bytes) ? bytes : null;

        // bridge から届いた、いまの出力を反映する。
        public void Apply(FanState state)
        {
            foreach (var output in state.Readings)
            {
                if (!TryIndex(output.Channel, out var side, out var position)) continue;
                SetActual(side, position, (byte)System.Math.Min(output.Value, 255u));
            }
        }

        // FanSide x FanPosition の並び(Left/Right x Back/Side/Front)は FanChannel の 1-6 と同じ。
        private static FanChannel Channel(FanSide side, FanPosition position) =>
            (FanChannel)(FanOutput.Index(side, position) + 1);

        private static bool TryIndex(FanChannel channel, out FanSide side, out FanPosition position)
        {
            var index = (int)channel - 1;
            side = default;
            position = default;
            if (index < 0 || index >= FanOutput.FanCount) return false;
            side = (FanSide)(index / FanOutput.PositionCount);
            position = (FanPosition)(index % FanOutput.PositionCount);
            return true;
        }

        public byte Get(FanSide side, FanPosition position) => actual[FanOutput.Index(side, position)];

        public void SetActual(FanSide side, FanPosition position, byte value) =>
            actual[FanOutput.Index(side, position)] = value;
    }
}
