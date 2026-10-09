using Features.senkoUI;
using UnityEngine;

public class SparklerGaugeSample : MonoBehaviour
{
    [SerializeField]
    private SparklerGaugeController sparklerGauge;

    [Header("Burning Commands")]
    [SerializeField]
    private bool startBurning;

    [SerializeField]
    private bool endBurning;

    [Header("Progress")]
    [Range(0f, 1f)]
    [SerializeField]
    private float targetProgress;

    private void Start()
    {
        if (sparklerGauge == null)
        {
            Debug.LogError(
                "Sparkler Gaugeを設定してください。", this);
            enabled = false;
            return;
        }

        sparklerGauge.SetProgress(targetProgress);
    }

    private void Update()
    {
        // 両方オンの場合は終了を優先する。
        if (endBurning)
        {
            endBurning = false;
            startBurning = false;
            sparklerGauge.EndBurning();
        }
        else if (startBurning)
        {
            startBurning = false;
            sparklerGauge.StartBurning();
        }

        targetProgress = Mathf.Clamp01(targetProgress);
        sparklerGauge.SetProgress(targetProgress);
    }
}