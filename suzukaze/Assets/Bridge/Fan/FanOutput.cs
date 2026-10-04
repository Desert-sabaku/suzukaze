using System;

namespace Suzukaze.Fan
{
    public enum FanSide { Left, Right }
    public enum FanPosition { Back, Side, Front }

    // Latest value (0-255) commanded to each of the six fans. The mock only
    // records and displays them; sending to the microcontroller comes later.
    public sealed class FanOutput
    {
        public static FanOutput Instance { get; private set; } = new FanOutput();

        private readonly byte[] values = new byte[2 * 3];

        public static void ResetInstance() => Instance = new FanOutput();

        public byte Get(FanSide side, FanPosition position) => values[Index(side, position)];

        public void Set(FanSide side, FanPosition position, byte value) =>
            values[Index(side, position)] = value;

        public static int Percent(byte value) => (value * 100 + 127) / 255;

        private static int Index(FanSide side, FanPosition position)
        {
            if (!Enum.IsDefined(typeof(FanSide), side) || !Enum.IsDefined(typeof(FanPosition), position))
                throw new ArgumentOutOfRangeException(nameof(side), "Unknown fan");
            return (int)side * 3 + (int)position;
        }
    }
}
