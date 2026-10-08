using System.Linq;
using NUnit.Framework;
using UnityEngine;

namespace Suzukaze.Fan.Tests
{
    public class YuragiProfileTests
    {
        private static readonly YuragiProfile[] Profiles = { YuragiProfile.Natural, YuragiProfile.Fanning };

        private static float[] Sample(YuragiProfile profile, float seed) =>
            Enumerable.Range(0, 1200).Select(i => profile.Power(i * 0.05f, seed)).ToArray();

        // The average change from one sample to the next.
        private static float Restlessness(YuragiProfile profile) =>
            Sample(profile, 12.3f).Zip(Sample(profile, 12.3f).Skip(1), (a, b) => Mathf.Abs(b - a)).Average();

        [TestCaseSource(nameof(Profiles))]
        public void PowerStaysInsideTheRange(YuragiProfile profile)
        {
            foreach (float power in Sample(profile, 12.3f))
                Assert.That(power, Is.InRange(profile.powerRange.x, profile.powerRange.y));
        }

        [TestCaseSource(nameof(Profiles))]
        public void PowerUsesAFairPartOfTheRange(YuragiProfile profile)
        {
            float[] powers = Sample(profile, 12.3f);
            Assert.That(powers.Max() - powers.Min(),
                Is.GreaterThan(0.3f * (profile.powerRange.y - profile.powerRange.x)));
        }

        [TestCaseSource(nameof(Profiles))]
        public void SameSeedRepeatsAndOtherSeedDiffers(YuragiProfile profile)
        {
            CollectionAssert.AreEqual(Sample(profile, 12.3f), Sample(profile, 12.3f));
            CollectionAssert.AreNotEqual(Sample(profile, 12.3f), Sample(profile, 456.7f));
        }

        [Test]
        public void FanningIsStrongerThanNaturalWind() =>
            Assert.That(YuragiProfile.Fanning.powerRange.x, Is.GreaterThanOrEqualTo(YuragiProfile.Natural.powerRange.y));

        [Test]
        public void FanningChangesFasterThanNaturalWind()
        {
            var natural = YuragiProfile.Natural;
            var fanning = YuragiProfile.Fanning;
            // Compare the shape alone, on the same range.
            fanning.powerRange = natural.powerRange;
            Assert.That(Restlessness(fanning), Is.GreaterThan(2f * Restlessness(natural)));
        }

        [Test]
        public void LowerRoughnessIsSmoother()
        {
            var rough = new YuragiProfile(new Vector2(0f, 1f), 0.1f, 6, 1f, 1f);
            var smooth = new YuragiProfile(new Vector2(0f, 1f), 0.1f, 6, 0.3f, 1f);
            Assert.That(Restlessness(smooth), Is.LessThan(Restlessness(rough)));
        }
    }
}
