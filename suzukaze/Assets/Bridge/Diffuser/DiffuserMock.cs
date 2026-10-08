using System.Collections.Generic;

namespace Suzukaze.Diffuser
{
    // 実機の代わり。ディフューザーは単押しで電源が入るトグル式で状態を読めないので、
    // 押した回数の偶奇でチャンネル(1始まり)ごとの ON/OFF を覚える。
    public sealed class DiffuserMock
    {
        public static DiffuserMock Instance { get; private set; } = new();

        private readonly HashSet<uint> on = new();

        public static void ResetInstance() => Instance = new DiffuserMock();

        public void Press(uint channel)
        {
            if (!on.Remove(channel)) on.Add(channel);
        }

        public bool IsOn(uint channel) => on.Contains(channel);
    }
}
