using UnityEngine;
using DG.Tweening;

public class RawImageSway : MonoBehaviour
{
    [SerializeField] private RectTransform rectTransform;

    [Header("揺れ設定")]
    [SerializeField] private float amplitude = 20f;  // 揺れ幅(px)
    [SerializeField] private float duration = 1f;    // 片道にかかる秒数

    void Start()
    {
        // 未設定なら自分自身のRectTransformを使う
        if (rectTransform == null)
            rectTransform = GetComponent<RectTransform>();

        float baseX = rectTransform.anchoredPosition.x;

        rectTransform
            .DOAnchorPosX(baseX + amplitude, duration)
            .SetLoops(-1, LoopType.Yoyo)   // -1で無限ループ、Yoyoで往復
            .SetEase(Ease.InOutSine)       // 滑らかな揺れ
            .SetLink(gameObject);          // オブジェクト破棄時にTweenも自動停止
    }
}