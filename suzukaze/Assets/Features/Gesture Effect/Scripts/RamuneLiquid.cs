using UnityEngine;

namespace Features.Gesture_Effect.Scripts
{
    /// <summary>
    ///     ラムネ瓶の動きから中身の揺れを計算し，RamuneGlass シェーダーの液面を傾ける
    /// </summary>
    [DisallowMultipleComponent]
    public class RamuneLiquid : MonoBehaviour
    {
        private const float Gravity = 9.81f;
        private static readonly int TiltId = Shader.PropertyToID("_LiquidTilt");

        [Tooltip("Bottle renderer using Suzukaze/RamuneGlass.")] [SerializeField]
        private Renderer target;

        [Header("Response")]
        [Tooltip("Multiplier on the surface slope caused by acceleration (1 = physically level with the " +
                 "effective gravity).")]
        [SerializeField]
        private float accelerationGain = 1f;

        [Tooltip("Surface slope per rad/s of the bottle spinning about a horizontal axis.")] [SerializeField]
        private float angularGain = 0.05f;

        [SerializeField] private float maxTilt = 0.6f;

        [Header("Slosh")] [Tooltip("Oscillation frequency of the sloshing (Hz).")] [SerializeField]
        private float frequency = 2.5f;

        [Tooltip("Damping ratio; 1 settles without overshoot.")] [Range(0f, 1f)] [SerializeField]
        private float damping = 0.15f;

        [Tooltip("Tilt speed that drives the surface waves to full strength.")] [SerializeField]
        private float motionForFullWaves = 1f;

        private MaterialPropertyBlock _block;
        private bool _hasHistory;
        private Vector3 _lastPosition;
        private Quaternion _lastRotation;
        private Vector3 _lastVelocity;
        private Vector2 _tilt;
        private Vector2 _tiltVelocity;

        private void Reset()
        {
            foreach (var r in GetComponentsInChildren<Renderer>(true))
            {
                if (r.sharedMaterial == null || r.sharedMaterial.shader.name != "Suzukaze/RamuneGlass") continue;
                target = r;
                return;
            }
        }

        private void LateUpdate()
        {
            if (target == null) return;

            var dt = Time.deltaTime;
            var bottle = target.transform;
            if (!_hasHistory || dt <= 0f)
            {
                if (!_hasHistory) RememberPose(bottle, Vector3.zero);
                return;
            }

            var velocity = (bottle.position - _lastPosition) / dt;
            var acceleration = (velocity - _lastVelocity) / dt;
            var delta = bottle.rotation * Quaternion.Inverse(_lastRotation);
            delta.ToAngleAxis(out var angle, out var axis);
            if (angle > 180f) angle -= 360f;
            var angularVelocity = float.IsFinite(axis.x) ? axis * (angle * Mathf.Deg2Rad / dt) : Vector3.zero;
            RememberPose(bottle, velocity);

            // The surface levels against the effective gravity (g - a); spinning about a
            // horizontal axis pushes the liquid sideways.
            var spin = Vector3.Cross(angularVelocity, Vector3.up);
            var goal = new Vector2(-acceleration.x, -acceleration.z) * (accelerationGain / Gravity)
                       + new Vector2(spin.x, spin.z) * angularGain;
            goal = Vector2.ClampMagnitude(goal, maxTilt);

            // Damped spring toward the goal slope.
            var omega = 2f * Mathf.PI * frequency;
            var force = (goal - _tilt) * (omega * omega) - _tiltVelocity * (2f * damping * omega);
            _tiltVelocity += force * dt;
            _tilt = Vector2.ClampMagnitude(_tilt + _tiltVelocity * dt, maxTilt);

            var motion = Mathf.Clamp01(_tiltVelocity.magnitude / Mathf.Max(motionForFullWaves, 1e-4f));
            Apply(new Vector4(_tilt.x, 0f, _tilt.y, motion));
        }

        private void OnEnable()
        {
            _block ??= new MaterialPropertyBlock();
            _hasHistory = false;
            _tilt = Vector2.zero;
            _tiltVelocity = Vector2.zero;
        }

        private void OnDisable()
        {
            Apply(Vector4.zero);
        }

        private void RememberPose(Transform bottle, Vector3 velocity)
        {
            _lastPosition = bottle.position;
            _lastRotation = bottle.rotation;
            _lastVelocity = velocity;
            _hasHistory = true;
        }

        private void Apply(Vector4 tilt)
        {
            if (target == null || _block == null) return;
            target.GetPropertyBlock(_block);
            _block.SetVector(TiltId, tilt);
            target.SetPropertyBlock(_block);
        }
    }
}
