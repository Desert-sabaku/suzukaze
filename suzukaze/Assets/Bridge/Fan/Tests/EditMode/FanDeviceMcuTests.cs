using System;
using NUnit.Framework;

namespace Suzukaze.Fan.Tests
{
    public class FanDeviceMcuTests
    {
        [Test]
        public void EveryFanKeepsItsOwnActualValue()
        {
            var mcu = new FanDeviceMcu();
            byte next = 1;
            foreach (FanSide side in Enum.GetValues(typeof(FanSide)))
                foreach (FanPosition position in Enum.GetValues(typeof(FanPosition)))
                    mcu.SetActual(side, position, next++);
            next = 1;
            foreach (FanSide side in Enum.GetValues(typeof(FanSide)))
                foreach (FanPosition position in Enum.GetValues(typeof(FanPosition)))
                    Assert.AreEqual(next++, mcu.Get(side, position));
        }

        [Test]
        public void CommandDoesNotChangeTheActualValue()
        {
            var mcu = new FanDeviceMcu();
            mcu.SetDuration(FanSide.Left, FanPosition.Side, mcu.MaxValue, 0);
            Assert.AreEqual(mcu.MinValue, mcu.Get(FanSide.Left, FanPosition.Side));
        }
    }
}
