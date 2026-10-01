using System;
using System.Runtime.InteropServices;

namespace Suzukaze.Gesture.Delivery
{
    // CPython time.monotonic on Windows uses raw QPC / frequency as well.
    // Stopwatch elapsed time has a process-local origin and is not interchangeable.
    public sealed class WindowsQpcClock : IMonotonicClock
    {
        [DllImport("Kernel32.dll")]
        private static extern bool QueryPerformanceCounter(out long counter);
        [DllImport("Kernel32.dll")]
        private static extern bool QueryPerformanceFrequency(out long frequency);
        private readonly long frequency;

        public WindowsQpcClock()
        {
            if (!RuntimeInformation.IsOSPlatform(OSPlatform.Windows))
                throw new PlatformNotSupportedException("Gesture delivery requires Windows same-PC QPC");
            if (!QueryPerformanceFrequency(out frequency) || frequency <= 0)
                throw new InvalidOperationException("QPC frequency unavailable");
        }

        public double Now
        {
            get
            {
                if (!QueryPerformanceCounter(out long counter))
                    throw new InvalidOperationException("QPC unavailable");
                // Split the division like CPython to avoid losing low counter bits.
                return (double)(counter / frequency) + (double)(counter % frequency) / frequency;
            }
        }
    }
}
