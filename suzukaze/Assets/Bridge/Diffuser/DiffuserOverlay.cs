using Suzukaze.Diffuser.Protocol;
using UnityEngine;

namespace Suzukaze.Diffuser
{
    // DiffuserMock の状態(押した回数の偶奇)を Game 画面の下の中央に出す。実機の状態ではない。
    // Editor と Development Build だけで動く。起動時に作るので、シーンは編集しない。
    public sealed class DiffuserOverlay : MonoBehaviour
    {
        private static readonly (DiffuserChannel Channel, string Name)[] Rows =
        {
            (DiffuserChannel.Ramune, "ラムネ"),
            (DiffuserChannel.Forest, "森"),
        };

        private const int FontSize = 39;
        private const float Width = 380f;
        private const float RowHeight = 52f;
        private const float Margin = 10f;

        private GUIStyle style;

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.AfterSceneLoad)]
        private static void Create()
        {
            if (!Debug.isDebugBuild || FindAnyObjectByType<DiffuserOverlay>()) return;
            var host = new GameObject("DiffuserOverlay");
            host.AddComponent<DiffuserOverlay>();
            DontDestroyOnLoad(host);
        }

        // private void OnGUI()
        // {
        //     var output = DiffuserOutput.Instance;
        //     style ??= new GUIStyle(GUI.skin.label) { fontSize = FontSize, alignment = TextAnchor.MiddleCenter };
        //     for (var i = 0; i < Rows.Length; i++)
        //     {
        //         var y = Screen.height - Margin - RowHeight * (Rows.Length - i);
        //         var row = new Rect((Screen.width - Width) / 2f, y, Width, RowHeight);
        //         GUI.Box(row, GUIContent.none);
        //         GUI.Label(row, Rows[i].Name + ": " + (output.Mock.IsOn(Rows[i].Channel) ? "ON" : "OFF"), style);
        //     }
        // }
    }
}
