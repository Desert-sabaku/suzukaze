using Sirenix.OdinInspector;
using UnityEngine;
using UnityEngine.VFX;

namespace Features.Gesture_Effect.Scripts
{
    /// <summary>
    ///     ラムネの開栓演出．ビー玉を口から玉止めまで落とし，瓶内の泡を一時的に増やして VFX を再生する
    /// </summary>
    [DisallowMultipleComponent]
    public class RamuneOpenEffect : MonoBehaviour
    {
        private static readonly int MarbleCenterId = Shader.PropertyToID("_MarbleCenter");
        private static readonly int BubbleDensityId = Shader.PropertyToID("_BubbleDensity");
        private static readonly int BubbleSpeedId = Shader.PropertyToID("_BubbleSpeed");

        [Tooltip("Bottle renderer using Suzukaze/RamuneGlass.")] [SerializeField]
        private Renderer target;

        [SerializeField] private VisualEffect openVfx;

        [Header("Marble (object units along the bottle axis)")]
        [Tooltip("Where the marble seals the mouth before opening.")]
        [SerializeField]
        private float closedCenter = 1.32f;

        [Tooltip("Where the dents stop the marble after opening.")] [SerializeField]
        private float openCenter = 0.56f;

        [Tooltip("Downward speed given by the push that opens the bottle.")] [SerializeField]
        private float pushSpeed = 2.5f;

        [SerializeField] private float gravity = 20f;

        [Tooltip("Fraction of speed kept on each bounce off the stop.")] [Range(0f, 1f)] [SerializeField]
        private float bounciness = 0.4f;

        [Tooltip("Bounces slower than this settle the marble.")] [SerializeField]
        private float settleSpeed = 0.8f;

        [Header("Fizz inside the bottle")] [SerializeField]
        private float fizzBubbleDensity = 0.7f;

        [SerializeField] private float fizzBubbleSpeed = 1.6f;

        [Tooltip("Seconds for the bubbles to calm back to the material's values.")] [SerializeField]
        private float fizzDuration = 3f;

        private float _baseBubbleDensity;
        private float _baseBubbleSpeed;
        private MaterialPropertyBlock _block;
        private float _fizzTime = float.PositiveInfinity;
        private float _marble;
        private bool _marbleMoving;
        private float _marbleVelocity;

        [ShowInInspector] [ReadOnly] public bool IsOpen { get; private set; }

        private void Reset()
        {
            foreach (var r in GetComponentsInChildren<Renderer>(true))
            {
                if (r.sharedMaterial == null || r.sharedMaterial.shader.name != "Suzukaze/RamuneGlass") continue;
                target = r;
                break;
            }

            openVfx = GetComponentInChildren<VisualEffect>(true);
        }

        private void Awake()
        {
            Close();
        }

        private void Update()
        {
            if (target == null) return;
            var dt = Time.deltaTime;

            if (_marbleMoving)
            {
                _marbleVelocity -= gravity * dt;
                _marble += _marbleVelocity * dt;
                if (_marble <= openCenter)
                {
                    _marble = openCenter;
                    _marbleVelocity = -_marbleVelocity * bounciness;
                    if (_marbleVelocity < settleSpeed)
                    {
                        _marbleVelocity = 0f;
                        _marbleMoving = false;
                    }
                }
            }

            _fizzTime += dt;
            // Full fizz right after opening, then ease back to the material's values.
            var fizz = 1f - Mathf.SmoothStep(0f, 1f, _fizzTime / Mathf.Max(fizzDuration, 1e-4f));

            target.GetPropertyBlock(_block);
            _block.SetFloat(MarbleCenterId, _marble);
            _block.SetFloat(BubbleDensityId, Mathf.Lerp(_baseBubbleDensity, fizzBubbleDensity, fizz));
            _block.SetFloat(BubbleSpeedId, Mathf.Lerp(_baseBubbleSpeed, fizzBubbleSpeed, fizz));
            target.SetPropertyBlock(_block);
        }

        private void OnEnable()
        {
            _block ??= new MaterialPropertyBlock();
            if (target == null) return;
            var material = target.sharedMaterial;
            _baseBubbleDensity = material.GetFloat(BubbleDensityId);
            _baseBubbleSpeed = material.GetFloat(BubbleSpeedId);
        }

        /// <summary>
        ///     開栓する．すでに開いていれば何もしない
        /// </summary>
        [Button]
        public void Open()
        {
            if (IsOpen) return;
            IsOpen = true;
            _marble = closedCenter;
            _marbleVelocity = -pushSpeed;
            _marbleMoving = true;
            _fizzTime = 0f;
            if (openVfx != null) openVfx.Play();
        }

        /// <summary>
        ///     ビー玉を口に戻して未開栓の状態にする
        /// </summary>
        [Button]
        public void Close()
        {
            IsOpen = false;
            _marble = closedCenter;
            _marbleVelocity = 0f;
            _marbleMoving = false;
            _fizzTime = float.PositiveInfinity;
            if (openVfx != null) openVfx.Reinit();
        }
    }
}
