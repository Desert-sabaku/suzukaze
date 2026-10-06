using System;
using System.Linq;
using NUnit.Framework;
using UnityEngine;
using Object = UnityEngine.Object;

namespace Suzukaze.Fan.Tests
{
    public class WindPresetsTests
    {
        private static readonly WindPreset[] Presets = (WindPreset[])Enum.GetValues(typeof(WindPreset));

        private static float[] Sample(WindPreset preset, float seed) =>
            Enumerable.Range(0, 1200).Select(i => WindPresets.Power(preset, i * 0.05f, seed)).ToArray();

        [TestCaseSource(nameof(Presets))]
        public void PowerStaysInsideThePresetRange(WindPreset preset)
        {
            Vector2 range = WindPresets.PowerRange(preset);
            foreach (float power in Sample(preset, 12.3f))
                Assert.That(power, Is.InRange(range.x, range.y));
        }

        [TestCaseSource(nameof(Presets))]
        public void PowerKeepsChanging(WindPreset preset)
        {
            float[] powers = Sample(preset, 12.3f);
            Vector2 range = WindPresets.PowerRange(preset);
            // Over a minute the wind should use a fair part of its range.
            Assert.That(powers.Max() - powers.Min(), Is.GreaterThan(0.3f * (range.y - range.x)));
        }

        [TestCaseSource(nameof(Presets))]
        public void SameSeedRepeatsAndOtherSeedDiffers(WindPreset preset)
        {
            CollectionAssert.AreEqual(Sample(preset, 12.3f), Sample(preset, 12.3f));
            CollectionAssert.AreNotEqual(Sample(preset, 12.3f), Sample(preset, 456.7f));
        }

        [Test]
        public void FanningStrokesAboutOnceASecond()
        {
            float[] powers = Sample(WindPreset.Fanning, 12.3f);
            Vector2 range = WindPresets.PowerRange(WindPreset.Fanning);
            float middle = (range.x + range.y) / 2f;
            int rises = 0;
            for (int i = 1; i < powers.Length; i++)
                if (powers[i - 1] < middle && powers[i] >= middle) rises++;
            Assert.That(rises, Is.InRange(40, 90)); // 60 seconds sampled.
        }

        [Test]
        public void FanningPuffsRiseQuicklyAndFadeSlowly()
        {
            float[] powers = Enumerable.Range(0, 6000)
                .Select(i => WindPresets.Power(WindPreset.Fanning, i * 0.01f, 12.3f)).ToArray();
            int rising = 0, falling = 0;
            for (int i = 1; i < powers.Length; i++)
            {
                if (powers[i] > powers[i - 1]) rising++;
                else if (powers[i] < powers[i - 1]) falling++;
            }
            Assert.That(falling, Is.GreaterThan(3 * rising));
        }

        [Test]
        public void UnknownPresetIsRejected() =>
            Assert.Throws<ArgumentOutOfRangeException>(() => WindPresets.Power((WindPreset)99, 0f, 0f));

        [Test]
        public void PresetBlowsUntilStopped()
        {
            var controller = new GameObject("WindFanController").AddComponent<WindFanController>();
            try
            {
                controller.ReferenceCamera = controller.transform;
                controller.PresetWindDirection = Vector3.back;
                controller.PlayPreset(WindPreset.Strong);
                Assert.IsTrue(controller.IsBlowing);
                Assert.That(controller.CurrentPower, Is.InRange(0.8f, 1f));
                // Wind from the front: the front fan (0 degrees) blows.
                Assert.That(controller.CurrentOutput[0], Is.GreaterThanOrEqualTo(204));

                controller.StopWind();
                Assert.IsFalse(controller.IsBlowing);
                CollectionAssert.AreEqual(new byte[6], controller.CurrentOutput.ToArray());
            }
            finally
            {
                Object.DestroyImmediate(controller.gameObject);
            }
        }
    }
}
