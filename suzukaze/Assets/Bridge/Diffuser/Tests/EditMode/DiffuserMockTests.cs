using Google.Protobuf;
using NUnit.Framework;
using Suzukaze.Bridge.Protocol;
using Suzukaze.Diffuser.Protocol;

namespace Suzukaze.Diffuser.Tests
{
    public class DiffuserMockTests
    {
        [Test]
        public void PressTogglesPerChannel()
        {
            var mock = new DiffuserMock();
            Assert.IsFalse(mock.IsOn(DiffuserChannel.Ramune));
            mock.Press(DiffuserChannel.Ramune);
            Assert.IsTrue(mock.IsOn(DiffuserChannel.Ramune));
            Assert.IsFalse(mock.IsOn(DiffuserChannel.Forest));
            mock.Press(DiffuserChannel.Ramune);
            Assert.IsFalse(mock.IsOn(DiffuserChannel.Ramune));
        }

        [Test]
        public void PressIsRecordedByTheMockWhileDisconnected()
        {
            var output = new DiffuserOutput();
            output.Press(DiffuserChannel.Forest);
            Assert.IsTrue(output.Mock.IsOn(DiffuserChannel.Forest));
            Assert.IsNull(output.TakeOutgoing());
        }

        [Test]
        public void PressIsQueuedForTheBridgeWhileConnected()
        {
            var output = new DiffuserOutput { Connected = true };
            output.Press(DiffuserChannel.Forest, 300);
            var press = BridgeEnvelope.Parser.ParseFrom(output.TakeOutgoing()).DiffuserPress;
            Assert.AreEqual(DiffuserChannel.Forest, press.Channel);
            Assert.AreEqual(300UL, press.DurationMs);
            Assert.IsFalse(output.Mock.IsOn(DiffuserChannel.Forest));
        }
    }
}
