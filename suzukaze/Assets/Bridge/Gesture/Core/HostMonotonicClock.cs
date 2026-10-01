using System;
using System.Runtime.InteropServices;

namespace Suzukaze.Gesture.Receiver
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
            throw new PlatformNotSupportedException(
                "Gesture delivery requires Windows QPC or 64-bit Linux CLOCK_MONOTONIC on the same PC");
        }
    }
}
