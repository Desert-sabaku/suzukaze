using System;
using System.Diagnostics;

namespace Suzukaze.Fan
{
    // 実機の代わり。firmwareと同じく、指示ごとにデューティを0から値まで、durationMsかけて
    // ガンマカーブで上げる(firmware/cmd/pwm.go を参照)。
    public sealed class FanDeviceMock : IFanDevice
    {
        public const double Gamma = 2.2;

        // firmware の PwmFade.value と同じ 8bit。
        public byte MinValue => 0;
        public byte MaxValue => 255;

        private static readonly Stopwatch Clock = Stopwatch.StartNew();

        private readonly Func<double> seconds;
        private readonly byte[] values = new byte[FanOutput.FanCount];
        private readonly double[] startedAt = new double[FanOutput.FanCount];
        private readonly ulong[] durationsMs = new ulong[FanOutput.FanCount];

        public FanDeviceMock() : this(() => Clock.Elapsed.TotalSeconds) { }

        public FanDeviceMock(Func<double> seconds) => this.seconds = seconds;

        public void SetDuration(FanSide side, FanPosition position, byte value, ulong durationMs)
        {
            var index = FanOutput.Index(side, position);
            values[index] = value;
            durationsMs[index] = durationMs;
            startedAt[index] = seconds();
        }

        public byte Get(FanSide side, FanPosition position)
        {
            var index = FanOutput.Index(side, position);
            var t = durationsMs[index] == 0
                ? 1.0
                : Math.Min(1.0, (seconds() - startedAt[index]) * 1000.0 / durationsMs[index]);
            var duty = Math.Pow(t * values[index] / MaxValue, Gamma);
            return (byte)Math.Round(duty * MaxValue);
        }
    }
}
