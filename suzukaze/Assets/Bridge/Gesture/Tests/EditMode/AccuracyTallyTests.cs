using NUnit.Framework;
using Suzukaze.Gesture.Protocol;

namespace Suzukaze.Gesture.Tests
{
    public class AccuracyTallyTests
    {
        private static Event Occurrence(OccurrenceGesture gesture, double? accuracy)
        {
            var occurrence = new Event { EventId = 1, Gesture = gesture };
            if (accuracy.HasValue) occurrence.ActionAccuracy = accuracy.Value;
            return occurrence;
        }

        [Test]
        public void EmptyTallyHasNoOverall()
        {
            Assert.That(new AccuracyTally().Overall, Is.Null);
        }

        [Test]
        public void ContinuousGestureIsWeightedByTime()
        {
            var tally = new AccuracyTally();
            tally.AddState(ContinuousGesture.Fanning, 1, 3);
            tally.AddState(ContinuousGesture.Fanning, 0, 1);
            Assert.That(tally.Overall, Is.EqualTo(.75).Within(1e-9));
        }

        [Test]
        public void GesturesAreWeightedEquallyRegardlessOfAmount()
        {
            var tally = new AccuracyTally();
            tally.AddState(ContinuousGesture.Relaxing, .8, 30);
            tally.AddOccurrence(Occurrence(OccurrenceGesture.Ramune, .2));
            tally.AddOccurrence(Occurrence(OccurrenceGesture.Uchimizu, .4));
            tally.AddOccurrence(Occurrence(OccurrenceGesture.Uchimizu, .6));
            Assert.That(tally.Overall, Is.EqualTo((.8 + .2 + .5) / 3).Within(1e-9));
        }

        [Test]
        public void IgnoresBowUnevaluatedAndInvalidSamples()
        {
            var tally = new AccuracyTally();
            tally.AddState(ContinuousGesture.Bow, 0, 1);
            tally.AddState(ContinuousGesture.Fanning, null, 1);
            tally.AddState(ContinuousGesture.Fanning, 0, 0);
            tally.AddState(ContinuousGesture.Fanning, 0, double.NaN);
            tally.AddOccurrence(Occurrence(OccurrenceGesture.Ramune, null));
            tally.AddOccurrence(null);
            Assert.That(tally.Overall, Is.Null);

            tally.AddState(ContinuousGesture.Fanning, .9, 1);
            Assert.That(tally.Overall, Is.EqualTo(.9).Within(1e-9));
        }

        [Test]
        public void ResetClearsSamples()
        {
            var tally = new AccuracyTally();
            tally.AddOccurrence(Occurrence(OccurrenceGesture.Ramune, 1));
            tally.Reset();
            Assert.That(tally.Overall, Is.Null);
        }
    }
}
