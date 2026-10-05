using System;
using NUnit.Framework;

namespace Suzukaze.Fan.Tests
{
    public class FanDeviceMockTests
    {
        private static byte Gamma(FanDeviceMock mock, double t, byte value) =>
            (byte)Math.Round(mock.MaxValue * Math.Pow(t * value / mock.MaxValue, FanDeviceMock.Gamma));

        [Test]
        public void FansAreIndependentAndStartAtZero()
        {
            var mock = new FanDeviceMock(() => 0);
            mock.SetDuration(FanSide.Right, FanPosition.Front, mock.MaxValue, 0);
            Assert.AreEqual(mock.MaxValue, mock.Get(FanSide.Right, FanPosition.Front));
            Assert.AreEqual(mock.MinValue, mock.Get(FanSide.Left, FanPosition.Front));
            Assert.AreEqual(mock.MinValue, mock.Get(FanSide.Right, FanPosition.Back));
        }

        [Test]
        public void ZeroDurationJumpsToTheGammaCurvedValue()
        {
            var mock = new FanDeviceMock(() => 0);
            var value = (byte)(mock.MaxValue / 2);
            mock.SetDuration(FanSide.Left, FanPosition.Side, value, 0);
            Assert.AreEqual(Gamma(mock, 1, value), mock.Get(FanSide.Left, FanPosition.Side));
        }

        [Test]
        public void OutputRampsFromZeroOverTheDurationAlongTheGammaCurve()
        {
            const ulong durationMs = 1000;
            const double durationSeconds = durationMs / 1000.0;
            const double start = 10;
            double now = start;
            var mock = new FanDeviceMock(() => now);
            mock.SetDuration(FanSide.Right, FanPosition.Back, mock.MaxValue, durationMs);
            Assert.AreEqual(mock.MinValue, mock.Get(FanSide.Right, FanPosition.Back));
            now = start + durationSeconds / 2;
            Assert.AreEqual(Gamma(mock, 0.5, mock.MaxValue), mock.Get(FanSide.Right, FanPosition.Back));
            now = start + durationSeconds * 2;
            Assert.AreEqual(mock.MaxValue, mock.Get(FanSide.Right, FanPosition.Back));
        }
    }
}
