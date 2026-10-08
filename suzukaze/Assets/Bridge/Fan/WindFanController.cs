using System;
using System.Collections.Generic;
using UnityEngine;
using Random = UnityEngine.Random;
#if UNITY_EDITOR
using UnityEditor;
#endif

namespace Suzukaze.Fan
{
    // Converts an in-game wind into the outputs (0-255) of the six real fans
    // around the player. A fan can only blow from where it stands toward the
    // player, so wind it cannot reproduce leaves it at 0.
    public sealed class WindFanController : MonoBehaviour
    {
        public const int FanCount = 6;
        private const int MaxOutput = 255;
        private const float MinFanDistance = 0.01f;

        // The same order as FanOutput (Left/Right x Back/Side/Front), so fan i
        // drives FanChannel i + 1.
        private static readonly float[] DefaultFanAngles = { -135f, -90f, -45f, 135f, 90f, 45f };
        private static readonly float[] DefaultFanDistances = { 1.5f, 1.5f, 1.5f, 1.5f, 1.5f, 1.5f };

        [SerializeField] [Tooltip("テスト計算とGizmo表示に使うプレイヤーカメラ。未設定ならこのTransform")]
        private Transform referenceCamera;

        [Header("Fans")] [SerializeField] [Range(-180f, 180f)] [Tooltip("カメラ正面を0度、右を90度、左を-90度とした水平角")]
        private float[] fanAngles = (float[])DefaultFanAngles.Clone();

        [SerializeField] [Min(MinFanDistance)] [Tooltip("プレイヤーからファンまでの距離")]
        private float[] fanDistance = (float[])DefaultFanDistances.Clone();

        [SerializeField] [Range(0, MaxOutput)]
        [Tooltip("風が吹くときの最小の出力。ファンが回り始める値にすると、弱い風でも揺らぎが伝わる。" +
                 "実機のデューティは (値/255)^2.2 で、例えば 20% は 122、30% は 148")]
        private int minimumOutput;

        [Header("Gizmo")] [SerializeField] private Vector3 fanBoxSize = new(0.3f, 0.3f, 0.1f);

        [Header("Test")] [SerializeField] [Tooltip("カメラ基準で風が進んでいく方向")]
        private Vector3 testWindDirection = Vector3.back;

        [SerializeField] [Range(0f, 1f)] private float testWindPower = 1f;

        // Written only by ApplyTestWind, so editing the test inputs alone does
        // not change what the gizmo shows.
        [SerializeField] [HideInInspector] private byte[] testResult = new byte[FanCount];
        [SerializeField] [HideInInspector] private Vector3 appliedTestWindDirection;
        [SerializeField] [HideInInspector] private float appliedTestWindPower;

        [Header("Preset")] [SerializeField] private WindPreset preset = WindPreset.Breeze;

        [SerializeField] [Tooltip("カメラ基準で風が進んでいく方向。吹いている間も変更できます")]
        private Vector3 presetWindDirection = Vector3.back;

        [Header("Output")] [SerializeField] [Tooltip("Play中、吹いている風を実機のファン(FanOutput)へ送る")]
        private bool driveFans = true;

        [SerializeField] [Min(0f)] [Tooltip("実機へ送る最短の間隔(秒)。変わったファンだけを送る")]
        private float sendInterval = 0.1f;

        [SerializeField] [Min(0.1f)]
        [Tooltip("変わっていないファンも含めて全部を送り直す間隔(秒)。前のPlayの値が残っていたり、途中で接続し直したりしても揃う")]
        private float resendAllInterval = 1f;

        private byte[] _currentOutput = new byte[FanCount];
        private Vector3 _windDirection;

        // The values the fans were last told. The real fans may still hold
        // values from before (a previous Play, a reconnect), so every fan is
        // told again from time to time, starting with the first send.
        private readonly byte[] _sentOutput = new byte[FanCount];
        private double _lastSendTime = double.NegativeInfinity;
        private double _lastResendAllTime = double.NegativeInfinity;

        // A running preset or SetWind keeps blowing until StopWind; it is not saved with the scene.
        private float _seed;
        private double _startTime;

        // True while a preset or SetWind blows.
        [field: NonSerialized] public bool IsBlowing { get; private set; }

        [field: NonSerialized] public bool IsPlayingPreset { get; private set; }

        [field: NonSerialized] public WindPreset ActivePreset { get; private set; }

        [field: NonSerialized] public float CurrentPower { get; private set; }

        // The latest fan outputs of the blowing wind; all zero while stopped.
        public IReadOnlyList<byte> CurrentOutput => _currentOutput;

        public Vector3 PresetWindDirection
        {
            get => presetWindDirection;
            set => presetWindDirection = value;
        }

        // The camera used by ApplyTestWind, presets and the gizmo; this Transform when unset.
        public Transform ReferenceCamera
        {
            get => referenceCamera ? referenceCamera : transform;
            set => referenceCamera = value;
        }

        private static double Now
        {
            get
            {
#if UNITY_EDITOR
                if (!Application.isPlaying) return EditorApplication.timeSinceStartup;
#endif
                return Time.timeAsDouble;
            }
        }

        private void Reset()
        {
            var main = Camera.main;
            if (main != null) referenceCamera = main.transform;
        }

        private void Update()
        {
            if (IsPlayingPreset) Tick();
        }

        // After every script has had its say this frame, e.g. through SetWind.
        private void LateUpdate()
        {
            SendToFans(false);
        }

        private void OnDisable()
        {
            if (IsBlowing) StopWind();
        }

        private void OnValidate()
        {
            EnsureLength(ref fanAngles, DefaultFanAngles);
            EnsureLength(ref fanDistance, DefaultFanDistances);
            EnsureLength(ref testResult, new byte[FanCount]);
        }

        public void PlayPreset()
        {
            PlayPreset(preset);
        }

        public void PlayPreset(WindPreset windPreset)
        {
            WindPresets.PowerRange(windPreset); // Rejects unknown presets before changing state.
            ActivePreset = windPreset;
            _startTime = Now;
            _seed = Random.Range(0f, 1000f);
#if UNITY_EDITOR
            // Update does not run every frame outside Play mode.
            EditorApplication.update -= EditorTick;
            if (!Application.isPlaying) EditorApplication.update += EditorTick;
#endif
            IsBlowing = true;
            IsPlayingPreset = true;
            Tick();
        }

        // Blows a wind that another script works out, typically every frame.
        // It replaces a running preset. windDir and power are as in CalculateFanPower.
        public void SetWind(Vector3 windDir, float power)
        {
            if (IsPlayingPreset) StopPreset();
            IsBlowing = true;
            Blow(windDir, power);
        }

        public void StopWind()
        {
            StopPreset();
            IsBlowing = false;
            CurrentPower = 0f;
            _currentOutput = new byte[FanCount];
            SendToFans(true); // Stopping must not wait for the interval.
#if UNITY_EDITOR
            SceneView.RepaintAll();
#endif
        }

        private void StopPreset()
        {
            IsPlayingPreset = false;
#if UNITY_EDITOR
            EditorApplication.update -= EditorTick;
#endif
        }

        private void Tick()
        {
            Blow(presetWindDirection, WindPresets.Power(ActivePreset, (float)(Now - _startTime), _seed));
        }

        private void Blow(Vector3 windDir, float power)
        {
            _windDirection = windDir;
            CurrentPower = Mathf.Clamp01(power);
            _currentOutput = CalculateFanPower(ReferenceCamera, windDir, CurrentPower);
        }

        // Sends the fans whose value changed, at most once per sendInterval
        // unless forced. Only in Play mode, so editing the scene never runs them.
        private void SendToFans(bool force)
        {
            if (!driveFans || !Application.isPlaying) return;
            var now = Time.unscaledTimeAsDouble;
            if (!force && now - _lastSendTime < sendInterval) return;

            var resendAll = now - _lastResendAllTime >= resendAllInterval;
            if (resendAll) _lastResendAllTime = now;
            var fans = FanOutput.Instance;
            var sent = false;
            for (var i = 0; i < FanCount; i++)
            {
                if (!resendAll && _currentOutput[i] == _sentOutput[i]) continue;
                // The firmware ramps every command up from 0, so the value is set
                // at once; the blades' own inertia smooths the steps.
                fans.Set((FanSide)(i / FanOutput.PositionCount), (FanPosition)(i % FanOutput.PositionCount),
                    _currentOutput[i]);
                _sentOutput[i] = _currentOutput[i];
                sent = true;
            }

            if (sent) _lastSendTime = now;
        }

        // windDir is relative to playerCamera (x: right, y: up, z: forward) and
        // points where the wind travels; only its direction is used. power is
        // 0-1, where 1 is the strongest wind. The fan best aligned with the
        // level wind blows at power even when the wind falls between two fans,
        // so the felt strength does not depend on the direction.
        public byte[] CalculateFanPower(Transform playerCamera, Vector3 windDir, float power)
        {
            if (!playerCamera) throw new ArgumentNullException(nameof(playerCamera));
            var output = new byte[FanCount];
            var desiredWindDirection = playerCamera.TransformDirection(windDir).normalized;
            var levelWindDirection = Vector3.ProjectOnPlane(desiredWindDirection, Vector3.up).normalized;
            if (levelWindDirection == Vector3.zero) return output;

            var dots = new float[FanCount];
            var bestAlignment = 0f;
            var playerPosition = playerCamera.position;
            for (var i = 0; i < FanCount; i++)
            {
                var fanDirection = (playerPosition - GetFanPosition(playerCamera, i)).normalized;
                dots[i] = Mathf.Max(0f, Vector3.Dot(desiredWindDirection, fanDirection));
                bestAlignment = Mathf.Max(bestAlignment, Vector3.Dot(levelWindDirection, fanDirection));
            }

            if (bestAlignment <= 0f) return output;
            var strength = Mathf.Clamp01(power) / bestAlignment;
            for (var i = 0; i < FanCount; i++)
                output[i] = ToOutput(strength * dots[i]);
            return output;
        }

        // Real fans barely turn below some duty, so any wind starts there.
        private byte ToOutput(float share)
        {
            var value = Mathf.Clamp(Mathf.RoundToInt(MaxOutput * share), 0, MaxOutput);
            if (value == 0) return 0;
            return (byte)Mathf.RoundToInt(Mathf.Lerp(minimumOutput, MaxOutput, value / (float)MaxOutput));
        }

        public Vector3 GetFanPosition(Transform playerCamera, int index)
        {
            if (!playerCamera) throw new ArgumentNullException(nameof(playerCamera));
            if (index is < 0 or >= FanCount) throw new ArgumentOutOfRangeException(nameof(index));
            var offset = Quaternion.Euler(0f, fanAngles[index], 0f) * Vector3.forward * fanDistance[index];
            return playerCamera.position + Heading(playerCamera) * offset;
        }

        public void ApplyTestWind()
        {
            testResult = CalculateFanPower(ReferenceCamera, testWindDirection, testWindPower);
            appliedTestWindDirection = testWindDirection;
            appliedTestWindPower = Mathf.Clamp01(testWindPower);
        }

        // Clears the test so the gizmo shows every fan off and no arrow.
        public void StopTestWind()
        {
            testResult = new byte[FanCount];
            appliedTestWindDirection = Vector3.zero;
            appliedTestWindPower = 0f;
        }

        // The real fans stand on a level circle around the player, so only the
        // camera's heading turns them; looking up or down does not tilt them.
        private static Quaternion Heading(Transform camera)
        {
            var forward = Vector3.ProjectOnPlane(camera.forward, Vector3.up);
            if (forward.sqrMagnitude < 1e-6f)
                forward = Vector3.Cross(camera.right, Vector3.up); // Looking straight up or down.
            return Quaternion.LookRotation(forward, Vector3.up);
        }

        // The arrays always hold one entry per fan, even if resized in the Inspector.
        private static void EnsureLength<T>(ref T[] array, T[] defaults)
        {
            var length = array?.Length ?? 0;
            if (length == FanCount) return;
            Array.Resize(ref array, FanCount);
            for (var i = length; i < FanCount; i++) array[i] = defaults[i];
        }

#if UNITY_EDITOR
        private static readonly Color PlayerColor = Color.yellow;
        private static readonly Color IdleFanColor = Color.gray;
        private const float PlayerGizmoRadius = 0.15f;
        private const float ArrowThickness = 3f;

        // Blue when weak, through green and yellow, to red when strong.
        private static Color StrengthColor(float strength)
        {
            return Color.HSVToRGB(Mathf.Lerp(2f / 3f, 0f, Mathf.Clamp01(strength)), 1f, 1f);
        }

        private void EditorTick()
        {
            if (this == null || Application.isPlaying)
            {
                EditorApplication.update -= EditorTick;
                return;
            }

            Tick();
            SceneView.RepaintAll();
        }

        // While the wind blows, the gizmo follows it; otherwise it shows the last test.
        private void OnDrawGizmos()
        {
            var playerCamera = ReferenceCamera;
            var values = IsBlowing ? _currentOutput : testResult;
            var player = playerCamera.position;
            Gizmos.color = PlayerColor;
            Gizmos.DrawWireSphere(player, PlayerGizmoRadius);

            var averageDistance = 0f;
            for (var i = 0; i < FanCount; i++)
            {
                var fan = GetFanPosition(playerCamera, i);
                var value = values[i];
                averageDistance += fanDistance[i] / FanCount;

                Gizmos.color = value == 0 ? IdleFanColor : StrengthColor(value / (float)MaxOutput);
                Gizmos.DrawLine(fan, player);
                Gizmos.matrix = Matrix4x4.TRS(fan, Quaternion.LookRotation(player - fan, Vector3.up), Vector3.one);
                Gizmos.DrawWireCube(Vector3.zero, fanBoxSize);
                Gizmos.matrix = Matrix4x4.identity;
                Handles.Label(fan + Vector3.up * fanBoxSize.y, $"{i}: {value}");
            }

            // The arrow runs through the player along the shown wind; full power
            // spans the fan circle.
            var shownDirection = IsBlowing ? _windDirection : appliedTestWindDirection;
            var shownPower = IsBlowing ? CurrentPower : appliedTestWindPower;
            var wind = playerCamera.TransformDirection(shownDirection).normalized;
            var length = averageDistance * 2f * shownPower;
            if (wind == Vector3.zero || length <= 0f) return;
            var tail = player - wind * (length / 2f);
            var tip = player + wind * (length / 2f);
            var headSize = Mathf.Min(length * 0.3f, averageDistance * 0.15f);
            Handles.color = StrengthColor(shownPower);
            Handles.DrawLine(tail, tip - wind * (headSize * 0.5f), ArrowThickness);
            Handles.ConeHandleCap(0, tip - wind * (headSize * 0.5f), Quaternion.LookRotation(wind), headSize,
                EventType.Repaint);
        }
#endif
    }
}