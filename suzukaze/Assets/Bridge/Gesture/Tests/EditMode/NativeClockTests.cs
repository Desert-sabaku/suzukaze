using System;
using System.Runtime.InteropServices;
using System.Threading;
using System.Threading.Tasks;
using NUnit.Framework;

namespace Suzukaze.Gesture.Tests
{
    public class NativeClockTests
    {
        private static bool IsWindows => RuntimeInformation.IsOSPlatform(OSPlatform.Windows);
        private static bool IsLinux64 => RuntimeInformation.IsOSPlatform(OSPlatform.Linux)
            && IntPtr.Size == 8;

        [Test]
        public void FactorySelectsNativeClockOrRejectsUnsupportedHost()
        {
            if (IsWindows)
                Assert.That(HostMonotonicClock.Create(), Is.TypeOf<WindowsQpcClock>());
            else if (IsLinux64)
                Assert.That(HostMonotonicClock.Create(), Is.TypeOf<LinuxMonotonicClock>());
            else
                Assert.Throws<PlatformNotSupportedException>(() => HostMonotonicClock.Create());
        }

        [Test]
        public void LinuxClockReadsNativeTimeOrRejectsUnsupportedAbiBeforePInvoke()
        {
            if (IsLinux64)
                AssertValid(new LinuxMonotonicClock().Now);
            else
                Assert.Throws<PlatformNotSupportedException>(() => new LinuxMonotonicClock());
        }

        [Test]
        public void WindowsClockReadsNativeTimeOrRejectsOtherOperatingSystemsBeforePInvoke()
        {
            if (IsWindows)
                AssertValid(new WindowsQpcClock().Now);
            else
                Assert.Throws<PlatformNotSupportedException>(() => new WindowsQpcClock());
        }

        [TestCase(false)]
        [TestCase(true)]
        public void ClockIsNondecreasingAndProgressesInSeconds(bool useFactory)
        {
            var clock = CreateClock(useFactory);
            double start = clock.Now;
            AssertValid(start);
            double previous = start;
            for (int i = 0; i < 1024; i++)
            {
                double now = clock.Now;
                Assert.That(now, Is.GreaterThanOrEqualTo(previous));
                previous = now;
            }
            Thread.Sleep(20);
            double elapsed = clock.Now - start;
            // Loose bounds allow scheduler jitter but catch frozen clocks and
            // millisecond/nanosecond values mistakenly returned as seconds.
            Assert.That(elapsed, Is.InRange(0.005, 10.0));
        }

        [TestCase(false)]
        [TestCase(true)]
        public void SharedClockAndNewInstancesKeepOneEpochAcrossThreads(bool useFactory)
        {
            var shared = CreateClock(useFactory);
            double before = shared.Now;
            var workers = new Task<double[]>[4];
            for (int worker = 0; worker < workers.Length; worker++)
            {
                workers[worker] = Task.Run(() =>
                {
                    var local = CreateClock(useFactory);
                    var samples = new double[1024];
                    for (int i = 0; i < samples.Length; i++)
                        samples[i] = (i % 2 == 0 ? shared : local).Now;
                    return samples;
                });
            }
            Assert.That(Task.WaitAll(workers, TimeSpan.FromSeconds(10)), Is.True,
                "Native clock reads must finish within a bounded interval");
            double after = shared.Now;
            foreach (var worker in workers)
            {
                double previous = before;
                foreach (double sample in worker.Result)
                {
                    AssertValid(sample);
                    Assert.That(sample, Is.InRange(previous, after),
                        "Instances and threads must share the native host epoch");
                    previous = sample;
                }
            }
        }

        private static IMonotonicClock CreateClock(bool useFactory)
        {
            if (!IsWindows && !IsLinux64)
                Assert.Ignore("Native clock progression requires Windows or 64-bit Linux");
            if (useFactory) return HostMonotonicClock.Create();
            if (IsWindows) return new WindowsQpcClock();
            return new LinuxMonotonicClock();
        }

        private static void AssertValid(double value)
        {
            Assert.That(double.IsNaN(value) || double.IsInfinity(value), Is.False);
            Assert.That(value, Is.GreaterThanOrEqualTo(0));
        }
    }
}
