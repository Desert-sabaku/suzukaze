using System.Diagnostics;

namespace Suzukaze.Gesture.Receiver
{
    public class OSXMonotonicClock : IMonotonicClock
    {
        public double Now => Stopwatch.GetTimestamp();
    }
}