using System;
using NUnit.Framework;

namespace Suzukaze.Fan.Tests
{
    public class FanOutputTests
    {
        [Test]
        public void FansAreIndependentAndStartAtZero()
        {
            var output = new FanOutput();
            output.Set(FanSide.Right, FanPosition.Front, 255);
            Assert.AreEqual(255, output.Get(FanSide.Right, FanPosition.Front));
            Assert.AreEqual(0, output.Get(FanSide.Left, FanPosition.Front));
            Assert.AreEqual(0, output.Get(FanSide.Right, FanPosition.Back));
        }

        [Test]
        public void EveryFanKeepsItsOwnValue()
        {
            var output = new FanOutput();
            byte next = 1;
            foreach (FanSide side in Enum.GetValues(typeof(FanSide)))
                foreach (FanPosition position in Enum.GetValues(typeof(FanPosition)))
                    output.Set(side, position, next++);
            next = 1;
            foreach (FanSide side in Enum.GetValues(typeof(FanSide)))
                foreach (FanPosition position in Enum.GetValues(typeof(FanPosition)))
                    Assert.AreEqual(next++, output.Get(side, position));
        }

        [TestCase(0, 0)]
        [TestCase(255, 100)]
        [TestCase(128, 50)]
        public void PercentRoundsToNearest(int value, int percent) =>
            Assert.AreEqual(percent, FanOutput.Percent((byte)value));

        [Test]
        public void UnknownFanIsRejected() =>
            Assert.Throws<ArgumentOutOfRangeException>(() =>
                new FanOutput().Get((FanSide)2, FanPosition.Back));
    }
}
