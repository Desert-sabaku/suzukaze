using Sirenix.OdinInspector;
using Suzukaze.Fan;
using Suzukaze.Gesture;
using Suzukaze.Gesture.Protocol;
using UnityEngine;
using UnityEngine.VFX;

namespace Features.Wind.Scripts
{
    /// <summary>
    ///     シーンに吹く風を決め、実機のファンと WindZone に反映する
    /// </summary>
    /// <remarks>
    ///     自然の風はときどき、吹くたびに違う向きから、ゆっくり滑らかな揺らぎで吹く。扇いでいる間は自然の風を止め、
    ///     扇ぎのエフェクトの向きから、揺らぎなしの最大の強さで吹かせる。
    ///     WindZone は自然の風だけに合わせる。
    /// </remarks>
    public class SceneWindDirector : MonoBehaviour
    {
        private const string FanningForceProperty = "Force";

        [Title("参照")] [SerializeField] [Required]
        private WindFanController fans;

        [Tooltip("扇ぎの葉のエフェクト。扇ぎの風は、葉に掛かる Force の向きに吹く")] [SerializeField] [Required]
        private VisualEffect aogiVfx;

        [Tooltip("自然の風に合わせる WindZone。未設定ならシーンから探し、無ければ何もしない")] [SerializeField]
        private WindZone windZone;

        [Title("自然の風")] [Tooltip("吹いている間に向きがふらつく幅 (±度)。向きそのものは吹くたびにランダムに決める")]
        [SerializeField] [Range(0f, 90f)]
        private float naturalWanderDegrees = 25f;

        [Tooltip("向きがふらつく速さ (Hz)")] [SerializeField] [Min(0.001f)]
        private float naturalWanderFrequency = 0.1f;

        [Tooltip("自然の風の揺らぎ。ゆっくり滑らかにうねる")] [SerializeField] [InlineProperty] [HideLabel]
        private YuragiProfile naturalYuragi = YuragiProfile.Natural;

        [Tooltip("シーン開始から最初に吹くまでの秒数 (最小, 最大)")] [SerializeField] [MinMaxSlider(0f, 60f, true)]
        private Vector2 firstGustDelay = new(3f, 8f);

        [Tooltip("吹き終わってから次に吹くまでの秒数 (最小, 最大)")] [SerializeField] [MinMaxSlider(0f, 120f, true)]
        private Vector2 calmSeconds = new(15f, 30f);

        [Tooltip("吹いている秒数 (最小, 最大)。吹き始めのフェードを含む")] [SerializeField] [MinMaxSlider(0f, 60f, true)]
        private Vector2 gustSeconds = new(6f, 12f);

        [SerializeField] [Min(0.01f)] private float naturalFadeInSeconds = 2f;
        [SerializeField] [Min(0.01f)] private float naturalFadeOutSeconds = 3f;

        [Title("扇ぎの風")] [SerializeField] [Min(0.01f)] private float fanningFadeInSeconds = 0.5f;
        [SerializeField] [Min(0.01f)] private float fanningFadeOutSeconds = 1.5f;

        [Title("WindZone")] [Tooltip("自然の風が止んでいるときの、シーンに置いた強さに対する割合")] [SerializeField] [Range(0f, 1f)]
        private float calmWindZoneScale = 0.3f;

        [Title("現在の状態")] [ReadOnly] [ShowInInspector]
        private bool _isFanning;

        [ReadOnly] [ShowInInspector] private bool _isGusting;
        [ReadOnly] [ShowInInspector] private float _naturalLevel;
        [ReadOnly] [ShowInInspector] private float _fanningLevel;

        private GestureReceiverBehaviour _gestureReceiver;
        private Transform _camera;

        // 次に吹き始める、または吹き終わる時刻
        private float _nextChange;
        private float _gustStart;
        private float _gustSeed;
        private float _gustAngle;

        private bool _hasWindZone;
        private float _windZoneMain;
        private float _windZoneTurbulence;
        private Quaternion _windZoneRotation;

        private void Start()
        {
            if (fans.ReferenceCamera == fans.transform && Camera.main) fans.ReferenceCamera = Camera.main.transform;
            _camera = fans.ReferenceCamera;
            _nextChange = Time.time + Random.Range(firstGustDelay.x, firstGustDelay.y);

            if (!windZone) windZone = FindAnyObjectByType<WindZone>();
            if (windZone)
            {
                _hasWindZone = true;
                _windZoneMain = windZone.windMain;
                _windZoneTurbulence = windZone.windTurbulence;
                _windZoneRotation = windZone.transform.rotation;
            }
        }

        private void Update()
        {
            UpdateGust();

            _naturalLevel = Mathf.MoveTowards(_naturalLevel, _isGusting && !_isFanning ? 1f : 0f,
                Time.deltaTime / (_isGusting && !_isFanning ? naturalFadeInSeconds : naturalFadeOutSeconds));
            _fanningLevel = Mathf.MoveTowards(_fanningLevel, _isFanning ? 1f : 0f,
                Time.deltaTime / (_isFanning ? fanningFadeInSeconds : fanningFadeOutSeconds));

            var naturalPower = _naturalLevel * naturalYuragi.Power(Time.time - _gustStart, _gustSeed);
            // 扇ぎの風は揺らがせず、フェードし終えたら常に最大で吹かせる
            var fanningPower = _fanningLevel;

            // 切り替わりで重なる間は、2 つの風を足し合わせる
            var naturalDirection = NaturalWorldDirection();
            var wind = naturalPower * naturalDirection + fanningPower * FanningWorldDirection();
            fans.SetWind(_camera.InverseTransformDirection(wind), wind.magnitude);

            if (_hasWindZone && windZone)
            {
                // 木や草が、ファンと同じ向きになびくようにする。止んでいる間は最後の向きのまま
                if (_naturalLevel > 0f) windZone.transform.rotation = Quaternion.LookRotation(naturalDirection, Vector3.up);
                var scale = Mathf.Lerp(calmWindZoneScale, 1f, naturalPower / naturalYuragi.powerRange.y);
                windZone.windMain = _windZoneMain * scale;
                windZone.windTurbulence = _windZoneTurbulence * scale;
            }
        }

        private void OnEnable()
        {
            _gestureReceiver = GestureReceiverBehaviour.GetOrCreate();
            _gestureReceiver.Events.StateChanged += OnGestureStateChanged;
            OnGestureStateChanged(_gestureReceiver.Events.CurrentState);
        }

        private void OnDisable()
        {
            if (_gestureReceiver)
            {
                _gestureReceiver.Events.StateChanged -= OnGestureStateChanged;
                _gestureReceiver = null;
            }

            if (fans) fans.StopWind();
            // WindZone はシーンの物なので、置いたときの状態に戻す
            if (_hasWindZone && windZone)
            {
                windZone.windMain = _windZoneMain;
                windZone.windTurbulence = _windZoneTurbulence;
                windZone.transform.rotation = _windZoneRotation;
            }
        }

        private void OnGestureStateChanged(StateView state)
        {
            // 追跡が切れると Gesture は None になるため、ここで自然に止まる
            SetFanning(state.Gesture == ContinuousGesture.Fanning);
        }

        [Button("扇ぎの風を切り替え")]
        private void ToggleFanning()
        {
            SetFanning(!_isFanning);
        }

        [Button("自然の風を今吹かせる")]
        private void GustNow()
        {
            _isGusting = false;
            _nextChange = Time.time;
        }

        private void SetFanning(bool fanning)
        {
            _isFanning = fanning;
        }

        // 扇いでいる間は次の自然の風を待たせ、扇ぎ終わってから静かな間を置く
        private void UpdateGust()
        {
            if (_isFanning)
            {
                _isGusting = false;
                _nextChange = Time.time + Random.Range(calmSeconds.x, calmSeconds.y);
                return;
            }

            if (Time.time < _nextChange) return;
            _isGusting = !_isGusting;
            if (_isGusting)
            {
                _gustStart = Time.time;
                _gustSeed = Random.Range(0f, 1000f);
                _gustAngle = Random.Range(0f, 360f);
                _nextChange = Time.time + Random.Range(gustSeconds.x, gustSeconds.y);
            }
            else
            {
                _nextChange = Time.time + Random.Range(calmSeconds.x, calmSeconds.y);
            }
        }

        private Vector3 NaturalWorldDirection()
        {
            var wander = 2f * Mathf.PerlinNoise((Time.time - _gustStart) * naturalWanderFrequency, _gustSeed + 100f) - 1f;
            return Quaternion.Euler(0f, _gustAngle + naturalWanderDegrees * Mathf.Clamp(wander, -1f, 1f), 0f) *
                   Vector3.forward;
        }

        // 葉は VFX のローカル空間で Force の向きに流れる
        private Vector3 FanningWorldDirection()
        {
            if (!aogiVfx) return Vector3.zero;
            var force = aogiVfx.HasVector3(FanningForceProperty)
                ? aogiVfx.GetVector3(FanningForceProperty)
                : Vector3.right;
            return Level(aogiVfx.transform.TransformDirection(force));
        }

        // 実機のファンは水平に並んでいるので、水平な成分だけを使う
        private static Vector3 Level(Vector3 direction)
        {
            return Vector3.ProjectOnPlane(direction, Vector3.up).normalized;
        }
    }
}
