using System;
using UnityEngine;
using UnityEngine.VFX;

public class SparklerGaugeController : MonoBehaviour
{
    [Header("References")]
    [SerializeField] private UnityEngine.UI.Image ashImage;
    [SerializeField] private VisualEffect gaugeVfx;

    [Header("Progress")]
    [Range(0f, 1f)] [SerializeField] private float progress;

    [Header("Transition Times")]
    [Min(0f)] [SerializeField] private float startTransitionSeconds = 1f;
    [Min(0f)] [SerializeField] private float endTransitionSeconds = 3f;

    [Header("VFX Parameters")]
    [Min(0.01f)] [SerializeField] private float burnDuration = 20f;
    [Min(0f)] [SerializeField] private float burningElapsed = 8f;
    [Min(0f)] [SerializeField] private float endingElapsed = 20f;
    
    [Header("VFX Position")]
    [Tooltip("Progressが0のときのローカルY座標")]
    [SerializeField] private float startY = 0f;

    [Tooltip("Progressが1のときのローカルY座標")]
    [SerializeField] private float endY = 300f;

    private enum BurnState
    {
        Idle,
        Starting,
        Burning,
        Ending
    }

    private BurnState state;
    private float transitionTime;
    private float transitionLength;
    private float transitionFrom;
    private float transitionTo;
    private float endingBallSize;

    public float Progress
    {
        get => progress;
        set => SetProgress(value);
    }

    private void Awake()
    {
        if (ashImage == null || gaugeVfx == null)
        {
            Debug.LogError(
                "Ash ImageとGauge VFXを設定してください。", this);
            enabled = false;
            return;
        }

        gaugeVfx.SetFloat("BurnDuration", burnDuration);
        gaugeVfx.SetFloat("Elapsed", 0f);
        gaugeVfx.SetFloat("DropTime", 99999f);
        gaugeVfx.SetFloat("BallSize", 1f);

        gaugeVfx.Reinit();
        gaugeVfx.Stop();
        ApplyProgress();
    }

    private void Update()
    {
        if (state != BurnState.Starting &&
            state != BurnState.Ending)
            return;

        transitionTime += Time.deltaTime;

        float t = transitionLength <= 0f
            ? 1f
            : Mathf.Clamp01(transitionTime / transitionLength);

        gaugeVfx.SetFloat(
            "Elapsed",
            Mathf.Lerp(transitionFrom, transitionTo, t));

        if (state == BurnState.Ending)
        {
            gaugeVfx.SetFloat("BallSize", Mathf.Lerp(1f, 0f, t));
        }

        if (t < 1f)
            return;

        if (state == BurnState.Ending)
        {
            // 残った火花は寿命まで表示する。
            gaugeVfx.Stop();
            state = BurnState.Idle;
        }
        else
        {
            state = BurnState.Burning;
        }
    }

    private void LateUpdate()
    {
        ApplyProgress();
    }

    public void StartBurning()
    {
        if (!enabled)
            return;

        gaugeVfx.SetFloat("BurnDuration", burnDuration);
        gaugeVfx.SetFloat("Elapsed", 0f);
        gaugeVfx.SetFloat("DropTime", 99999f);
        gaugeVfx.SetFloat("BallSize", 1f);

        gaugeVfx.Reinit();
        gaugeVfx.Play();

        BeginTransition(
            BurnState.Starting,
            0f,
            burningElapsed,
            startTransitionSeconds);
    }

    public void EndBurning()
    {
        if (!enabled || state == BurnState.Idle ||
            state == BurnState.Ending)
            return;

        endingBallSize = 1f;

        BeginTransition(
            BurnState.Ending,
            gaugeVfx.GetFloat("Elapsed"),
            endingElapsed,
            endTransitionSeconds);
    }

    public void SetProgress(float value)
    {
        progress = Mathf.Clamp01(value);

        if (ashImage != null && gaugeVfx != null)
            ApplyProgress();
    }

    private void BeginTransition(
        BurnState nextState,
        float from,
        float to,
        float seconds)
    {
        state = nextState;
        transitionTime = 0f;
        transitionLength = Mathf.Max(0f, seconds);
        transitionFrom = from;
        transitionTo = to;
    }

    private float GetFillAmount()
    {
        return Mathf.Lerp(1f, 0.335f, Mathf.Clamp01(progress));
    }

    private void ApplyProgress()
    {
        progress = Mathf.Clamp01(progress);
        ashImage.fillAmount = GetFillAmount();

        Vector3 position = gaugeVfx.transform.localPosition;
        position.y = Mathf.Lerp(startY, endY, progress);
        gaugeVfx.transform.localPosition = position;
    }
}