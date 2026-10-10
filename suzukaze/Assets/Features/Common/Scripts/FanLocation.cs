using System;
using Suzukaze.Fan;

namespace Features.Common.Scripts
{
    /// <summary>
    ///     実機のファン 1 台の場所。左右と、前・横・後ろで決める
    /// </summary>
    [Serializable]
    public struct FanLocation
    {
        public FanSide side;
        public FanPosition position;

        public FanLocation(FanSide side, FanPosition position)
        {
            this.side = side;
            this.position = position;
        }
    }
}
