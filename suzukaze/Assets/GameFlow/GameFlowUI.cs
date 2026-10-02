using TMPro;
using UnityEngine;
using UnityEngine.UI;

// GameFlowManager の画面(残り時間・リザルト)をコードで組み立てる。スタート画面は既存の Scene_ch を使う。
// 既存シーンに手を入れないよう、最前面のオーバーレイ Canvas として重ねる。
public class GameFlowUI
{
    readonly TMP_FontAsset font;
    readonly GameObject hudPanel;
    readonly GameObject resultPanel;
    readonly TextMeshProUGUI timerText;
    readonly TextMeshProUGUI scoreText;
    readonly TextMeshProUGUI countText;
    readonly TextMeshProUGUI resultFooter;
    readonly string resultFooterFormat;

    public GameFlowUI(Transform parent, TMP_FontAsset font, string startKeyName)
    {
        this.font = font;

        var canvasObject = new GameObject("GameFlowCanvas", typeof(Canvas), typeof(CanvasScaler));
        canvasObject.transform.SetParent(parent, false);
        var canvas = canvasObject.GetComponent<Canvas>();
        canvas.renderMode = RenderMode.ScreenSpaceOverlay;
        canvas.sortingOrder = 100;
        var scaler = canvasObject.GetComponent<CanvasScaler>();
        scaler.uiScaleMode = CanvasScaler.ScaleMode.ScaleWithScreenSize;
        scaler.referenceResolution = new Vector2(1920, 1080);
        scaler.matchWidthOrHeight = 0.5f;
        var root = canvasObject.transform;

        // 残り時間は右上の小さな帯に出す(マップの見た目を邪魔しない)
        hudPanel = new GameObject("Hud", typeof(RectTransform), typeof(Image));
        hudPanel.transform.SetParent(root, false);
        var hudRect = (RectTransform)hudPanel.transform;
        hudRect.anchorMin = hudRect.anchorMax = hudRect.pivot = Vector2.one;
        hudRect.anchoredPosition = new Vector2(-40, -40);
        hudRect.sizeDelta = new Vector2(320, 100);
        hudPanel.GetComponent<Image>().color = new Color(0f, 0f, 0f, 0.45f);
        timerText = Label(hudPanel.transform, "", 56, new Vector2(0.5f, 0.5f));
        ((RectTransform)timerText.transform).sizeDelta = hudRect.sizeDelta;

        resultPanel = Panel(root, "Result", new Color(0f, 0f, 0f, 0.7f));
        Label(resultPanel.transform, "風流度", 72, new Vector2(0.5f, 0.72f));
        scoreText = Label(resultPanel.transform, "", 220, new Vector2(0.5f, 0.52f));
        countText = Label(resultPanel.transform, "", 48, new Vector2(0.5f, 0.34f));
        resultFooter = Label(resultPanel.transform, "", 36, new Vector2(0.5f, 0.16f));
        resultFooter.color = new Color(1f, 1f, 1f, 0.7f);
        resultFooterFormat = "{0}秒後にスタート画面へ戻ります(［" + startKeyName + "］ですぐ戻る)";
    }

    public void Show(GameFlowManager.FlowState state)
    {
        hudPanel.SetActive(state == GameFlowManager.FlowState.Playing);
        resultPanel.SetActive(state == GameFlowManager.FlowState.Result);
    }

    public void SetRemaining(GameFlowManager.FlowState state, float seconds)
    {
        int shown = Mathf.Max(0, Mathf.CeilToInt(seconds));
        if (state == GameFlowManager.FlowState.Playing)
            timerText.text = $"残り {shown}";
        else if (state == GameFlowManager.FlowState.Result)
            resultFooter.text = string.Format(resultFooterFormat, shown);
    }

    public void SetResult(FuryuScore score)
    {
        scoreText.text = score.Value.ToString();
        countText.text = $"所作 {score.GestureCount} 回";
    }

    static GameObject Panel(Transform parent, string name, Color color)
    {
        var panel = new GameObject(name, typeof(RectTransform), typeof(Image));
        Stretch(panel.transform, parent);
        panel.GetComponent<Image>().color = color;
        return panel;
    }

    static void Stretch(Transform child, Transform parent)
    {
        child.SetParent(parent, false);
        var rect = (RectTransform)child;
        rect.anchorMin = Vector2.zero;
        rect.anchorMax = Vector2.one;
        rect.offsetMin = Vector2.zero;
        rect.offsetMax = Vector2.zero;
    }

    TextMeshProUGUI Label(Transform parent, string text, float size, Vector2 anchor)
    {
        var labelObject = new GameObject("Label", typeof(RectTransform));
        labelObject.transform.SetParent(parent, false);
        var rect = (RectTransform)labelObject.transform;
        rect.anchorMin = rect.anchorMax = anchor;
        rect.sizeDelta = new Vector2(1600, size * 1.5f);

        var label = labelObject.AddComponent<TextMeshProUGUI>();
        if (font != null) label.font = font;
        label.text = text;
        label.fontSize = size;
        label.alignment = TextAlignmentOptions.Center;
        label.color = Color.white;
        label.raycastTarget = false;
        return label;
    }
}
