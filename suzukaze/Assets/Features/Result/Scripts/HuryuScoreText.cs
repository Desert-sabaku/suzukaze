using TMPro;
using UnityEngine;

namespace Features.Result.Scripts
{
    /// <summary>
    ///     線香花火のスコア (0-1) を風流度 (1-10 の整数，四捨五入) としてテキストに表示する．
    ///     シーンに遷移した瞬間から表示するので，線香花火が Start でスコアを受け取った直後に書き込む．
    /// </summary>
    [DisallowMultipleComponent]
    [RequireComponent(typeof(TMP_Text))]
    [DefaultExecutionOrder(1)] // SenkoHanabiController.Start の後に Start を呼ぶ
    public class HuryuScoreText : MonoBehaviour
    {
        [SerializeField] private SenkoHanabiController hanabi;
        [SerializeField] private string format = "風流度　{0}";

        private void Start()
        {
            if (!hanabi)
            {
                Debug.LogError("Hanabiを設定してください。", this);
                return;
            }

            // Mathf.RoundToInt は偶数丸めなので，0.5 を足して切り捨てて四捨五入する
            var huryu = Mathf.FloorToInt(Mathf.Lerp(1f, 10f, hanabi.Score) + 0.5f);
            GetComponent<TMP_Text>().text = string.Format(format, huryu);
        }
    }
}
