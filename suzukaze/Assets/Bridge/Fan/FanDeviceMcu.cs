namespace Suzukaze.Fan
{
    // 実機。unity_bridge 経由でマイコンに指示を送り、マイコンが返した、いまの出力を保つ。
    public sealed class FanDeviceMcu : IFanDevice
    {
        private readonly byte[] actual = new byte[FanOutput.FanCount];

        // firmware の PwmFade.value と同じ 8bit。
        public byte MinValue => 0;
        public byte MaxValue => 255;

        // bridge と mcu の両方に接続しているか。未実装なので、いまは常に false(テストだけが書き換える)。
        // TODO: 接続状態の変化で更新する
        public bool Connected { get; set; } = false;

        public void SetDuration(FanSide side, FanPosition position, byte value, ulong durationMs)
        {
            FanOutput.Index(side, position);
            // TODO: Fan(channel, value, durationMs)を bridge へ送る
        }

        public byte Get(FanSide side, FanPosition position) => actual[FanOutput.Index(side, position)];

        // TODO: mcu から bridge 経由で受け取った、いまの出力(0-255)をここに渡す
        public void SetActual(FanSide side, FanPosition position, byte value) =>
            actual[FanOutput.Index(side, position)] = value;
    }
}
