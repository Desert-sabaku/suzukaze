namespace Suzukaze.Fan
{
    // ファン6本への指示の出口と、いまの出力の入口。実機は FanDeviceMcu、実機がないときは FanDeviceMock。
    public interface IFanDevice
    {
        // SetDuration の value と Get の戻り値がとる範囲。デバイスごとに決まる。
        byte MinValue { get; }
        byte MaxValue { get; }

        // value(MinValue-MaxValue)まで、デューティを durationMs かけて上げる。
        void SetDuration(FanSide side, FanPosition position, byte value, ulong durationMs);

        // いまの出力(MinValue-MaxValue)。指示した値ではない。
        byte Get(FanSide side, FanPosition position);
    }
}
