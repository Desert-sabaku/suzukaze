using UnityEngine;
using UnityEngine.InputSystem;

namespace Suzukaze.Fan
{
    // 動作確認用。キーでファンを回す。Editor と Development Build だけで動く。
    // 1-3: 左の奥/横/前、4-6: 右の奥/横/前。押すたびに 0 と最大値を切り替える。0: 全部止める。
    // 起動時に作るので、シーンは編集しない。
    public sealed class FanKeyTester : MonoBehaviour
    {
        private const ulong RampMs = 1000;

        private static readonly Key[] Keys =
            { Key.Digit1, Key.Digit2, Key.Digit3, Key.Digit4, Key.Digit5, Key.Digit6 };

        // 押したあとの目標値。FanOutput.Get は途中の値なので、切り替えには使わない。
        private readonly bool[] on = new bool[FanOutput.FanCount];

        // Play のたびに作り直す。Domain Reload を切っていても、前の Play の値を残さない。
        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.SubsystemRegistration)]
        private static void ResetPlaySession() => FanOutput.ResetInstance();

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.AfterSceneLoad)]
        private static void Create()
        {
            if (!Debug.isDebugBuild || FindAnyObjectByType<FanKeyTester>()) return;
            var host = new GameObject("FanKeyTester");
            host.AddComponent<FanKeyTester>();
            DontDestroyOnLoad(host);
        }

        private void Update()
        {
            var keyboard = Keyboard.current;
            if (keyboard == null) return;
            var output = FanOutput.Instance;
            for (var i = 0; i < Keys.Length; i++)
            {
                if (!keyboard[Keys[i]].wasPressedThisFrame) continue;
                on[i] = !on[i];
                Apply(output, i);
            }
            if (!keyboard.digit0Key.wasPressedThisFrame) return;
            for (var i = 0; i < on.Length; i++)
            {
                on[i] = false;
                Apply(output, i);
            }
        }

        private void Apply(FanOutput output, int index)
        {
            var side = (FanSide)(index / FanOutput.PositionCount);
            var position = (FanPosition)(index % FanOutput.PositionCount);
            output.SetDuration(side, position, on[index] ? output.MaxValue : output.MinValue, RampMs);
        }
    }
}
