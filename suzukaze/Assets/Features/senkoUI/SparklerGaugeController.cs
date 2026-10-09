using UnityEngine;
using UnityEngine.UI;
using UnityEngine.VFX;

namespace Features.senkoUI
{
    public class SparklerGaugeController : MonoBehaviour
    {
        [Header("References")] [SerializeField]
        private Image ashImage;

        [SerializeField] private VisualEffect gaugeVfx;

        [Header("Progress")] [Range(0f, 1f)] [SerializeField]
        private float progress;

        [Header("Transition Times")] [Min(0f)] [SerializeField]
        private float startTransitionSeconds = 1f;

        [Min(0f)] [SerializeField] private float endTransitionSeconds = 3f;

        [Header("VFX Parameters")] [Min(0.01f)] [SerializeField]
        private float burnDuration = 20f;

        [Min(0f)] [SerializeField] private float burningElapsed = 8f;
        [Min(0f)] [SerializeField] private float endingElapsed = 20f;

        [Header("VFX Position")] [Tooltip("Progressが0のときのローカルY座標")] [SerializeField]
        private float startY;

        [Tooltip("Progressが1のときのローカルY座標")] [SerializeField]
        private float endY = 300f;

        private BurnState _state;
        private float _transitionFrom;
        private float _transitionLength;
        private float _transitionTime;
        private float _transitionTo;

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
            if (_state != BurnState.Starting &&
                _state != BurnState.Ending)
                return;

            _transitionTime += Time.deltaTime;

            var t = _transitionLength <= 0f
                ? 1f
                : Mathf.Clamp01(_transitionTime / _transitionLength);

            gaugeVfx.SetFloat(
                "Elapsed",
                Mathf.Lerp(_transitionFrom, _transitionTo, t));

            if (_state == BurnState.Ending) gaugeVfx.SetFloat("BallSize", Mathf.Lerp(1f, 0f, t));

            if (t < 1f)
                return;

            if (_state == BurnState.Ending)
            {
                // 残った火花は寿命まで表示する。
                gaugeVfx.Stop();
                _state = BurnState.Idle;
            }
            else
            {
                _state = BurnState.Burning;
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
            if (!enabled || _state == BurnState.Idle ||
                _state == BurnState.Ending)
                return;

            BeginTransition(
                BurnState.Ending,
                gaugeVfx.GetFloat("Elapsed"),
                endingElapsed,
                endTransitionSeconds);
        }

        public void SetProgress(float value)
        {
            progress = Mathf.Clamp01(value);

            if (ashImage && gaugeVfx)
                ApplyProgress();
        }

        private void BeginTransition(
            BurnState nextState,
            float from,
            float to,
            float seconds)
        {
            _state = nextState;
            _transitionTime = 0f;
            _transitionLength = Mathf.Max(0f, seconds);
            _transitionFrom = from;
            _transitionTo = to;
        }

        private float GetFillAmount()
        {
            return Mathf.Lerp(1f, 0.335f, Mathf.Clamp01(progress));
        }

        private void ApplyProgress()
        {
            progress = Mathf.Clamp01(progress);
            ashImage.fillAmount = GetFillAmount();

            var position = gaugeVfx.transform.localPosition;
            position.y = Mathf.Lerp(startY, endY, progress);
            gaugeVfx.transform.localPosition = position;
        }

        private enum BurnState
        {
            Idle,
            Starting,
            Burning,
            Ending
        }
    }
}