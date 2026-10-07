using System;
using Google.Protobuf;
using NUnit.Framework;
using Suzukaze.Bridge.Protocol;
using FanChannel = Suzukaze.Fan.Protocol.FanChannel;

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

        [Test]
        public void CommandIsQueuedForTheBridge()
        {
            var mcu = new FanDeviceMcu();
            mcu.SetDuration(FanSide.Right, FanPosition.Side, 200, 1500);
            var command = BridgeEnvelope.Parser.ParseFrom(mcu.TakeOutgoing()).FanCommand;
            Assert.AreEqual(FanChannel.RightSide, command.Channel);
            Assert.AreEqual(200u, command.Value);
            Assert.AreEqual(1500UL, command.DurationMs);
            Assert.IsNull(mcu.TakeOutgoing());
        }

        [Test]
        public void FanStateUpdatesTheActualValue()
        {
            var mcu = new FanDeviceMcu();
            var state = new FanState();
            state.Readings.Add(new FanReading { Channel = FanChannel.LeftFront, Value = 77 });
            state.Readings.Add(new FanReading { Channel = FanChannel.Unspecified, Value = 5 });
            mcu.Apply(state);
            Assert.AreEqual(77, mcu.Get(FanSide.Left, FanPosition.Front));
            Assert.AreEqual(0, mcu.Get(FanSide.Left, FanPosition.Back));
        }
    }
}
