using System.Diagnostics;

namespace Suzukaze.Gesture
{
    public class OSXMonotonicClock : IMonotonicClock
    {
        public double Now => Stopwatch.GetTimestamp();
    }
}