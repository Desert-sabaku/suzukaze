using System;
using System.Runtime.InteropServices;

namespace Suzukaze.Gesture
{
    public static class HostMonotonicClock
    {
        // Producer and receiver must run on the same native OS PC.
        public static IMonotonicClock Create()
        {
            if (RuntimeInformation.IsOSPlatform(OSPlatform.Windows))
                return new WindowsQpcClock();
            if (RuntimeInformation.IsOSPlatform(OSPlatform.Linux))
                return new LinuxMonotonicClock();
            if (RuntimeInformation.IsOSPlatform(OSPlatform.OSX))
                return new OSXMonotonicClock();
            throw new PlatformNotSupportedException(
                "Gesture delivery requires Windows QPC, 64-bit Linux CLOCK_MONOTONIC or macOS mach_absolute_time on the same PC");
        }
    }
}
