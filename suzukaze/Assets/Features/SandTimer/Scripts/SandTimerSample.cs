using UnityEngine;

public class SandTimerSample : MonoBehaviour
{
    [SerializeField] private SandTimerController sandTimer;
    [SerializeField, Min(0.01f)] private float durationSeconds = 60f;

    private float elapsed;
    private bool running;

    private void Start()
    {
        Play(durationSeconds);
    }

    // 外部から秒数を指定して開始・再開始できます。
    public void Play(float seconds)
    {
        if (sandTimer == null)
        {
            Debug.LogError("Sand Timerを設定してください。", this);
            return;
        }

        if (float.IsNaN(seconds) || float.IsInfinity(seconds)
                                 || seconds <= 0f)
        {
            Debug.LogError("秒数には正の有限値を指定してください。", this);
            return;
        }

        durationSeconds = seconds;
        elapsed = 0f;
        running = true;
        sandTimer.SetProgress(0f);
    }

    private void Update()
    {
        if (!running) return;

        elapsed += Time.deltaTime;
        float progress = Mathf.Clamp01(elapsed / durationSeconds);

        sandTimer.SetProgress(progress);

        if (progress >= 1f)
            running = false;
    }
}