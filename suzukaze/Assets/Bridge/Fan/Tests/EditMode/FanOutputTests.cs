using System;
using NUnit.Framework;

namespace Suzukaze.Fan.Tests
{
    public class FanOutputTests
    {
        [Test]
        public void UsesTheMockWhileDisconnected()
        {
            var mock = new FanDeviceMock(() => 0);
            var output = new FanOutput(new FanDeviceMcu(), mock);
            output.Set(FanSide.Right, FanPosition.Front, mock.MaxValue);
            Assert.AreEqual(mock.MaxValue, output.Get(FanSide.Right, FanPosition.Front));
            Assert.AreEqual(mock.MinValue, output.Get(FanSide.Left, FanPosition.Front));
        }

        [Test]
        public void UsesTheActualValueWhileConnected()
        {
            var mcu = new FanDeviceMcu { Connected = true };
            var mock = new FanDeviceMock(() => 0);
            var output = new FanOutput(mcu, mock);
            var actual = (byte)(mcu.MaxValue / 2);
            output.Set(FanSide.Left, FanPosition.Side, mcu.MaxValue);
            mcu.SetActual(FanSide.Left, FanPosition.Side, actual);
            Assert.AreEqual(actual, output.Get(FanSide.Left, FanPosition.Side));
            mcu.Connected = false;
            Assert.AreEqual(mock.MinValue, output.Get(FanSide.Left, FanPosition.Side));
        }

        [Test]
        public void PercentUsesTheRangeOfTheCurrentDevice()
        {
            var mcu = new FanDeviceMcu { Connected = true };
            var mock = new FanDeviceMock(() => 0);
            var output = new FanOutput(mcu, mock);
            Assert.AreEqual(100, output.Percent(mcu.MaxValue));
            Assert.AreEqual(0, output.Percent(mcu.MinValue));
            Assert.AreEqual(50, output.Percent((byte)(mcu.MaxValue / 2 + 1)));
            mcu.Connected = false;
            Assert.AreEqual(100, output.Percent(mock.MaxValue));
        }

        [Test]
        public void RangeFollowsTheCurrentDevice()
        {
            var mcu = new FanDeviceMcu { Connected = true };
            var mock = new FanDeviceMock(() => 0);
            var output = new FanOutput(mcu, mock);
            Assert.AreEqual(mcu.MinValue, output.MinValue);
            Assert.AreEqual(mcu.MaxValue, output.MaxValue);
            mcu.Connected = false;
            Assert.AreEqual(mock.MinValue, output.MinValue);
            Assert.AreEqual(mock.MaxValue, output.MaxValue);
        }

        [Test]
        public void UnknownFanIsRejected() =>
            Assert.Throws<ArgumentOutOfRangeException>(() =>
                new FanOutput().Get((FanSide)2, FanPosition.Back));
    }
}
