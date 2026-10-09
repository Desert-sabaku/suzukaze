using System.Collections.Generic;
using NUnit.Framework;
using Suzukaze.Diffuser.Protocol;

namespace Suzukaze.Diffuser.Tests
{
    public class ScentSchedulerTests
    {
        private readonly List<DiffuserChannel> presses = new();
        private ScentScheduler scheduler;

        [SetUp]
        public void SetUp()
        {
            presses.Clear();
            scheduler = new ScentScheduler(presses.Add);
        }

        [Test]
        public void PressesOnceToStartAndOnceToStop()
        {
            scheduler.Emit(DiffuserChannel.Ramune, 0, 10);
            scheduler.Update(0);
            scheduler.Update(5);
            Assert.IsTrue(scheduler.IsOn(DiffuserChannel.Ramune));
            Assert.AreEqual(new[] { DiffuserChannel.Ramune }, presses);

            scheduler.Update(10);
            Assert.IsFalse(scheduler.IsOn(DiffuserChannel.Ramune));
            Assert.AreEqual(new[] { DiffuserChannel.Ramune, DiffuserChannel.Ramune }, presses);
        }

        [Test]
        public void EmittingAgainExtendsWithoutPressing()
        {
            scheduler.Emit(DiffuserChannel.Forest, 0, 3);
            scheduler.Update(0);
            scheduler.Emit(DiffuserChannel.Forest, 2, 3);
            scheduler.Emit(DiffuserChannel.Forest, 2, 1); // 短い指示で縮めない
            scheduler.Update(4);
            Assert.IsTrue(scheduler.IsOn(DiffuserChannel.Forest));
            Assert.AreEqual(1, presses.Count);
            scheduler.Update(5);
            Assert.IsFalse(scheduler.IsOn(DiffuserChannel.Forest));
        }

        [Test]
        public void ChannelsAreIndependent()
        {
            scheduler.Emit(DiffuserChannel.Ramune, 0, 10);
            scheduler.Emit(DiffuserChannel.Forest, 0, 2);
            scheduler.Update(3);
            Assert.IsTrue(scheduler.IsOn(DiffuserChannel.Ramune));
            Assert.IsFalse(scheduler.IsOn(DiffuserChannel.Forest));
            Assert.AreEqual(new[] { DiffuserChannel.Ramune }, presses);
        }

        [Test]
        public void StopAllPressesOnlyTheChannelsThatAreOn()
        {
            scheduler.Emit(DiffuserChannel.Ramune, 0, 10);
            scheduler.Update(0);
            scheduler.Emit(DiffuserChannel.Forest, 5, 10);
            scheduler.StopAll();
            Assert.AreEqual(new[] { DiffuserChannel.Ramune, DiffuserChannel.Ramune }, presses);
            scheduler.Update(6);
            Assert.AreEqual(2, presses.Count);
        }
    }
}
