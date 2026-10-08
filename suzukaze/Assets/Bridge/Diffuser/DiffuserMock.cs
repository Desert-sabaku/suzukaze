using System.Collections.Generic;
using Suzukaze.Diffuser.Protocol;

namespace Suzukaze.Diffuser
{
    // 実機の代わり。ディフューザーは単押しで電源が入るトグル式で状態を読めないので、
    // 押した回数の偶奇でチャンネルごとの ON/OFF を覚える。
    public sealed class DiffuserMock
    {
        private readonly HashSet<DiffuserChannel> on = new();

        public void Press(DiffuserChannel channel)
        {
            if (!on.Remove(channel)) on.Add(channel);
        }

        public bool IsOn(DiffuserChannel channel) => on.Contains(channel);
    }
}
