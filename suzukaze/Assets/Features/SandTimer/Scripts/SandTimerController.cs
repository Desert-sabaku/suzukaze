using UnityEngine;
using UnityEngine.Formats.Alembic.Importer;

[DisallowMultipleComponent]
public class SandTimerController : MonoBehaviour
{
    [Header("Alembic")]
    [SerializeField] private AlembicStreamPlayer alembicPlayer;

    [Header("Progress Bar (optional)")]
    [SerializeField] private UnityEngine.UI.Image progressImage;
    [SerializeField] private UnityEngine.UI.Slider progressSlider;
    [SerializeField, Tooltip("Show remaining time: full at 0, empty at 1.")]
    private bool showRemainingTime;

    [Header("Progress")]
    [SerializeField, Range(0f, 1f)] private float progress;

    public float Progress => progress;

    private void Start()
    {
        SetProgress(progress);
    }

    /// <summary>
    /// Updates the sand and optional bars. 0 is the start, 1 is the end.
    /// Uses the AlembicStreamPlayer's configured StartTime/EndTime range.
    /// </summary>
    public void SetProgress(float value)
    {
        if (float.IsNaN(value) || float.IsInfinity(value)) return;

        progress = Mathf.Clamp01(value);

        if (alembicPlayer != null)
        {
            // CurrentTime is relative to StartTime, not an absolute timestamp.
            alembicPlayer.UpdateImmediately(progress * alembicPlayer.Duration);
        }

        UpdateBars();
    }

    private void UpdateBars()
    {
        float barValue = showRemainingTime ? 1f - progress : progress;

        if (progressImage != null)
            progressImage.fillAmount = barValue;

        if (progressSlider != null)
        {
            // Supports any slider range and avoids triggering input callbacks.
            progressSlider.SetValueWithoutNotify(
                Mathf.Lerp(progressSlider.minValue, progressSlider.maxValue, barValue));
        }
    }

    private void OnValidate()
    {
        progress = Mathf.Clamp01(progress);
        // Apply display changes during Play mode from the main thread instead.
    }

#if UNITY_EDITOR
    private void Update()
    {
        // Allows the Inspector's Progress slider to preview during Play mode.
        SetProgress(progress);
    }
#endif
}