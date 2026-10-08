using UnityEngine;
using UnityEngine.InputSystem;

namespace Suzukaze.Diffuser
{
    // 動作確認用。D キーでディフューザー1のボタンを押す。
    // Editor と Development Build だけで動く。起動時に作るので、シーンは編集しない。
    public sealed class DiffuserKeyTester : MonoBehaviour
    {
        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.SubsystemRegistration)]
        private static void ResetPlaySession() => DiffuserMock.ResetInstance();

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.AfterSceneLoad)]
        private static void Create()
        {
            if (!Debug.isDebugBuild || FindAnyObjectByType<DiffuserKeyTester>()) return;
            var host = new GameObject("DiffuserKeyTester");
            host.AddComponent<DiffuserKeyTester>();
            DontDestroyOnLoad(host);
        }

        private void Update()
        {
            var keyboard = Keyboard.current;
            if (keyboard == null || !keyboard.dKey.wasPressedThisFrame) return;
            DiffuserMock.Instance.Press(1);
        }
    }
}
