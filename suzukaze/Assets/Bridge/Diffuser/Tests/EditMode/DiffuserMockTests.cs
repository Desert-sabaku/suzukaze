using NUnit.Framework;

namespace Suzukaze.Diffuser.Tests
{
    public class DiffuserMockTests
    {
        [Test]
        public void PressTogglesPerChannel()
        {
            var mock = new DiffuserMock();
            Assert.IsFalse(mock.IsOn(1));
            mock.Press(1);
            Assert.IsTrue(mock.IsOn(1));
            Assert.IsFalse(mock.IsOn(2));
            mock.Press(1);
            Assert.IsFalse(mock.IsOn(1));
        }
    }
}
