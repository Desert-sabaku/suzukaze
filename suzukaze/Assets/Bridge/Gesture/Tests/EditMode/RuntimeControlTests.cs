using System.IO;
using NUnit.Framework;
using Suzukaze.Bridge.Protocol;

namespace Suzukaze.Gesture.Tests
{
    public class RuntimeControlTests
    {
        private static BridgeEnvelope Take(RuntimeControl control) =>
            BridgeEnvelope.Parser.ParseFrom(control.TakeOutgoing());

        [Test]
        public void DefaultsUntilBridgeSendsSettings()
        {
            var control = new RuntimeControl();
            Assert.That(control.DiffuserEnabled, Is.True);
            Assert.That(control.TimeScaleMultiplier, Is.EqualTo(1));
            control.Apply(new RuntimeSettings { DiffuserEnabled = false, TimeScaleMultiplier = 2.5 });
            Assert.That(control.DiffuserEnabled, Is.False);
            Assert.That(control.TimeScaleMultiplier, Is.EqualTo(2.5));
        }

        [Test]
        public void InvalidSettingsAreRejected()
        {
            var control = new RuntimeControl();
            foreach (var multiplier in new[] { -1, 101, double.NaN, double.PositiveInfinity })
                Assert.Throws<InvalidDataException>(() =>
                    control.Apply(new RuntimeSettings { DiffuserEnabled = false, TimeScaleMultiplier = multiplier }));
            Assert.That(control.DiffuserEnabled, Is.True);
        }

        [Test]
        public void OnlyLatestStatusIsSentAndCarriesAppliedSettings()
        {
            var control = new RuntimeControl { EffectiveTimeScale = 2, CurrentHour = 18.5 };
            control.Apply(new RuntimeSettings { DiffuserEnabled = false, TimeScaleMultiplier = 2 });
            control.ReportStatus("Old", 30);
            control.ReportStatus("Forest", 60);
            var status = Take(control).RuntimeStatus;
            Assert.That(status.Scene, Is.EqualTo("Forest"));
            Assert.That(status.Settings.DiffuserEnabled, Is.False);
            Assert.That(status.CurrentHour, Is.EqualTo(18.5));
            Assert.That(control.TakeOutgoing(), Is.Null);

            control.CurrentHour = null;
            control.ReportStatus("Sea", 60);
            Assert.That(Take(control).RuntimeStatus.HasCurrentHour, Is.False);
        }

        [Test]
        public void LogsFitInOneWireMessageAndAreBounded()
        {
            var control = new RuntimeControl();
            control.ReportLog(UnityLogLevel.Exception, new string('あ', 10000), new string('い', 10000));
            Assert.That(control.TakeOutgoing().Length, Is.LessThanOrEqualTo(WireMessage.MaxBytes));
            for (int i = 0; i < RuntimeControl.MaxPendingLogs + 5; i++)
                control.ReportLog(UnityLogLevel.Error, "error " + i, "");
            int count = 0;
            while (control.TakeOutgoing() != null) count++;
            Assert.That(count, Is.EqualTo(RuntimeControl.MaxPendingLogs));
        }
    }
}
