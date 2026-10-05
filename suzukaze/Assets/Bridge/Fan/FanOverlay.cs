using UnityEngine;

namespace Suzukaze.Fan
{
    // Shows the commanded fan values on the Game view while no real fan is
    // driven. Created at startup so no scene has to be edited.
    // Left fans sit on the left edge, right fans on the right edge; back,
    // side and front go top, middle and bottom.
    public sealed class FanOverlay : MonoBehaviour
    {
        private static readonly string[] PositionNames = { "奥", "横", "前" };
        private const int FontSize = 39;
        private const float Margin = 10f;
        private const float RowWidth = 190f;
        private const float RowHeight = 52f;
        private const float NameWidth = 62f;
        private const float Padding = 12f;

        private GUIStyle nameStyle;
        private GUIStyle valueStyle;

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.AfterSceneLoad)]
        private static void Create()
        {
            if (FindAnyObjectByType<FanOverlay>()) return;
            var host = new GameObject("FanOverlay");
            host.AddComponent<FanOverlay>();
            DontDestroyOnLoad(host);
        }

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.SubsystemRegistration)]
        private static void ResetPlaySession()
        {
            FanOutput.ResetInstance();
        }

        private void OnGUI()
        {
            // if (!Debug.isDebugBuild) return;
            nameStyle ??= new GUIStyle(GUI.skin.label) { fontSize = FontSize, alignment = TextAnchor.MiddleLeft };
            // The value is right-aligned, so "%" stays put whatever the digit count.
            valueStyle ??= new GUIStyle(nameStyle) { alignment = TextAnchor.MiddleRight };
            var output = FanOutput.Instance;
            for (var side = 0; side < FanOutput.SideCount; side++)
            {
                var x = side == (int)FanSide.Left ? Margin : Screen.width - RowWidth - Margin;
                for (var position = 0; position < PositionNames.Length; position++)
                {
                    var y = position == (int)FanPosition.Back ? Margin
                        : position == (int)FanPosition.Side ? (Screen.height - RowHeight) / 2f
                        : Screen.height - RowHeight - Margin;
                    var row = new Rect(x, y, RowWidth, RowHeight);
                    var percent = output.DutyPercent((FanSide)side, (FanPosition)position);
                    GUI.Box(row, GUIContent.none);
                    GUI.Label(new Rect(row.x + Padding, row.y, NameWidth, RowHeight), PositionNames[position] + ":", nameStyle);
                    GUI.Label(new Rect(row.x + NameWidth, row.y, RowWidth - NameWidth - Padding, RowHeight), percent + "%", valueStyle);
                }
            }
        }
    }
}
