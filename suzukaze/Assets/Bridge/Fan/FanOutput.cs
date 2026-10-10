using System;

namespace Suzukaze.Fan
{
    public enum FanSide { Left, Right }
    public enum FanPosition { Back, Side, Front }

    // ファンへの指示の窓口。bridge と mcu に接続している間は FanDeviceMcu、
    // それ以外は FanDeviceMock に振り分ける。
    public sealed class FanOutput
    {
        public static readonly int SideCount = Enum.GetValues(typeof(FanSide)).Length;
        public static readonly int PositionCount = Enum.GetValues(typeof(FanPosition)).Length;
        public static readonly int FanCount = SideCount * PositionCount;
        
        public static FanOutput Instance { get; private set; } = new();

        private readonly FanDeviceMcu mcu;
        private readonly FanDeviceMock mock;

        // ファンごとに、最後に指示された値と、それに関わらず保つ下限
        private readonly byte[] requested = new byte[FanCount];
        private readonly byte[] floors = new byte[FanCount];

        public FanOutput() : this(new FanDeviceMcu(), new FanDeviceMock()) { }

        public FanOutput(FanDeviceMcu mcu, FanDeviceMock mock)
        {
            this.mcu = mcu;
            this.mock = mock;
        }

        public static void ResetInstance() => Instance = new FanOutput();

        public FanDeviceMcu Mcu => mcu;

        private IFanDevice Device => mcu.Connected ? mcu : mock;
        
        public byte MinValue => Device.MinValue;
        public byte MaxValue => Device.MaxValue;

        /// <summary>
        /// ファンの出力を即時変化
        /// </summary>
        public void Set(FanSide side, FanPosition position, byte value) =>
            SetDuration(side, position, value, 0);
        
        /// <summary>
        /// ファンの出力を[durationMs]ミリ秒で[value]に変化させる。下限より弱くはしない
        /// </summary>
        public void SetDuration(FanSide side, FanPosition position, byte value, ulong durationMs)
        {
            var index = Index(side, position);
            requested[index] = value;
            Device.SetDuration(side, position, Math.Max(value, floors[index]), durationMs);
        }

        /// <summary>
        /// ほかの指示に関わらず、ファンを[value]以上で回し続ける。0 で解除する
        /// </summary>
        public void SetFloor(FanSide side, FanPosition position, byte value)
        {
            var index = Index(side, position);
            if (floors[index] == value) return;
            floors[index] = value;
            Device.SetDuration(side, position, Math.Max(requested[index], value), 0);
        }

        public byte GetFloor(FanSide side, FanPosition position) => floors[Index(side, position)];

        /// <summary>
        /// 現在のファンの出力
        /// </summary>
        public byte Get(FanSide side, FanPosition position) => Device.Get(side, position);

        public int DutyPercent(FanSide side, FanPosition position) =>
            Percent(Get(side, position));

        public int Percent(byte value) => (value * 100 + MaxValue / 2) / MaxValue;

        internal static int Index(FanSide side, FanPosition position)
        {
            if (!Enum.IsDefined(typeof(FanSide), side) || !Enum.IsDefined(typeof(FanPosition), position))
                throw new ArgumentOutOfRangeException(nameof(side), "Unknown fan");
            return (int)side * PositionCount + (int)position;
        }
    }
}
