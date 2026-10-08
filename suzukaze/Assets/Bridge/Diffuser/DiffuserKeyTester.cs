using Suzukaze.Diffuser.Protocol;
using UnityEngine;
using UnityEngine.InputSystem;

namespace Suzukaze.Diffuser
{
    // 動作確認用。R: ラムネ、F: 森のディフューザーのボタンを押す。
    // Editor と Development Build だけで動く。起動時に作るので、シーンは編集しない。
    public sealed class DiffuserKeyTester : MonoBehaviour
    {
        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.SubsystemRegistration)]
        private static void ResetPlaySession() => DiffuserOutput.ResetInstance();

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
            if (keyboard == null) return;
            if (keyboard.rKey.wasPressedThisFrame) DiffuserOutput.Instance.Press(DiffuserChannel.Ramune);
            if (keyboard.fKey.wasPressedThisFrame) DiffuserOutput.Instance.Press(DiffuserChannel.Forest);
        }
    }
}
