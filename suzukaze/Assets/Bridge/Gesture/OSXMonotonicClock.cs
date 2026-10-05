using System;
using System.Runtime.InteropServices;

namespace Suzukaze.Gesture
{
    // CPython time.monotonic on macOS: mach_absolute_time() ticks converted to
    // nanoseconds with mach_timebase_info (Python/pytime.c). Same clock and epoch.
    // Stopwatch.GetTimestamp is a tick count of unspecified unit, not seconds.
    public sealed class OSXMonotonicClock : IMonotonicClock
    {
        private const ulong NanosecondsPerSecond = 1_000_000_000;

        [StructLayout(LayoutKind.Sequential)]
        private struct TimebaseInfo
        {
            public uint Numerator;
            public uint Denominator;
        }

        [DllImport("libSystem.dylib", EntryPoint = "mach_absolute_time")]
        private static extern ulong MachAbsoluteTime();

        [DllImport("libSystem.dylib", EntryPoint = "mach_timebase_info")]
        private static extern int MachTimebaseInfo(out TimebaseInfo info);

        private readonly ulong numerator;
        private readonly ulong denominator;

        public OSXMonotonicClock()
        {
            if (!RuntimeInformation.IsOSPlatform(OSPlatform.OSX))
                throw new PlatformNotSupportedException("Gesture delivery requires macOS mach_absolute_time");
            if (MachTimebaseInfo(out var info) != 0 || info.Denominator == 0)
                throw new InvalidOperationException("mach_timebase_info unavailable");
            numerator = info.Numerator;
            denominator = info.Denominator;
        }

        public double Now
        {
            get
            {
                var ticks = MachAbsoluteTime();
                // Split the division like CPython to avoid overflowing ticks * numerator.
                var nanoseconds = ticks / denominator * numerator + ticks % denominator * numerator / denominator;
                return nanoseconds / NanosecondsPerSecond
                    + (nanoseconds % NanosecondsPerSecond) / (double)NanosecondsPerSecond;
            }
        }
    }
}
