using System;
using System.ComponentModel;
using System.Runtime.InteropServices;

namespace Suzukaze.Gesture
{
    // Same native Linux host and epoch as CPython time.monotonic().
    // CLOCK_MONOTONIC excludes suspend time; CLOCK_BOOTTIME is not interchangeable.
    public sealed class LinuxMonotonicClock : IMonotonicClock
    {
        private const int ClockMonotonic = 1;

        // Linux LP64: both time_t and C long are signed 64-bit values.
        [StructLayout(LayoutKind.Sequential)]
        private struct Timespec
        {
            public long Seconds;
            public long Nanoseconds;
        }

        [DllImport("libc", EntryPoint = "clock_gettime", SetLastError = true)]
        private static extern int ClockGetTime(int clockId, out Timespec time);

        public LinuxMonotonicClock()
        {
            if (!RuntimeInformation.IsOSPlatform(OSPlatform.Linux) || IntPtr.Size != 8)
                throw new PlatformNotSupportedException(
                    "Gesture delivery requires 64-bit Linux (LP64) for CLOCK_MONOTONIC");
        }

        public double Now
        {
            get
            {
                if (ClockGetTime(ClockMonotonic, out var time) == 0)
                    return time.Seconds + time.Nanoseconds / 1_000_000_000.0;
                int errno = Marshal.GetLastWin32Error();
                throw new Win32Exception(errno,
                    "clock_gettime(CLOCK_MONOTONIC) failed; errno=" + errno);
            }
        }
    }
}
