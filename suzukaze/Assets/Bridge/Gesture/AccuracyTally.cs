using System.Collections.Generic;
using Suzukaze.Gesture.Protocol;

namespace Suzukaze.Gesture
{
    // 1プレイ分の所作の正確性を集計する。継続所作は評価できた時間で重み付けした平均、
    // 単発所作は各回の平均を所作ごとに出し、行った所作どうしを等しい重みで平均する。
    // 礼はプレイの開始・終了の合図なので数えない。未評価(accuracy なし)の値は無視する。
    public sealed class AccuracyTally
    {
        private readonly Dictionary<Action, (double Sum, double Weight)> totals = new();

        // seconds はこの状態が続いた時間。フレームごとに呼ぶ
        public void AddState(ContinuousGesture gesture, double? accuracy, double seconds)
        {
            if (accuracy is not { } value || !(seconds > 0) || double.IsInfinity(seconds)) return;
            switch (gesture)
            {
                case ContinuousGesture.Fanning:
                    Add(Action.Fanning, value, seconds);
                    break;
                case ContinuousGesture.Relaxing:
                    Add(Action.Relaxing, value, seconds);
                    break;
            }
        }

        public void AddOccurrence(Event occurrence)
        {
            if (occurrence is not { HasActionAccuracy: true }) return;
            switch (occurrence.Gesture)
            {
                case OccurrenceGesture.Ramune:
                    Add(Action.Ramune, occurrence.ActionAccuracy, 1);
                    break;
                case OccurrenceGesture.Uchimizu:
                    Add(Action.Uchimizu, occurrence.ActionAccuracy, 1);
                    break;
            }
        }

        // プレイ全体の正確性(0〜1)。評価できた所作が1つもなければ null
        public double? Overall
        {
            get
            {
                if (totals.Count == 0) return null;
                double sum = 0;
                foreach (var total in totals.Values) sum += total.Sum / total.Weight;
                return sum / totals.Count;
            }
        }

        public void Reset() { totals.Clear(); }

        private void Add(Action action, double accuracy, double weight)
        {
            totals.TryGetValue(action, out var total);
            totals[action] = (total.Sum + accuracy * weight, total.Weight + weight);
        }
    }
}
