using Suzukaze.Gesture.Receiver;
using UnityEngine;
using GestureEvent = Suzukaze.Gesture.Protocol.Event;

// 風流度の仮実装。
// 資料の算出方法(所作の滑らかさ P と理想軌道 E による評価関数)が入るまでは、
// 遊戯中に成立した所作の回数から点数を出す。差し替えるときは Value を書き換える。
public class FuryuScore
{
    public const int PointsPerGesture = 10;
    public const int MaxScore = 100;

    public int GestureCount { get; private set; }
    public bool Counting { get; set; }
    public int Value => Mathf.Min(MaxScore, GestureCount * PointsPerGesture);

    GestureEvents events;

    public void Attach(GestureEvents source)
    {
        Detach();
        events = source;
        events.Occurred += OnOccurred;
    }

    public void Detach()
    {
        if (events != null) events.Occurred -= OnOccurred;
        events = null;
    }

    public void Reset() => GestureCount = 0;

    public void CountManual()
    {
        if (Counting) GestureCount++;
    }

    // 数えるだけの観測者なので、演出の採用(ACK)には関与しない
    bool OnOccurred(string sessionId, GestureEvent occurrence)
    {
        if (Counting && occurrence != null) GestureCount++;
        return false;
    }
}
