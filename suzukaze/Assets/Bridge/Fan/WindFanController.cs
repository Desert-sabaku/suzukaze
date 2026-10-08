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

        private static readonly float[] DefaultFanAngles = { 0f, 60f, 120f, 180f, -120f, -60f };
        private static readonly float[] DefaultFanDistances = { 1.5f, 1.5f, 1.5f, 1.5f, 1.5f, 1.5f };

        [SerializeField] [Tooltip("テスト計算とGizmo表示に使うプレイヤーカメラ。未設定ならこのTransform")]
        private Transform referenceCamera;

        [Header("Fans")] [SerializeField] [Range(-180f, 180f)] [Tooltip("カメラ正面を0度、右を90度、左を-90度とした水平角")]
        private float[] fanAngles = (float[])DefaultFanAngles.Clone();

        [SerializeField] [Min(MinFanDistance)] [Tooltip("プレイヤーからファンまでの距離")]
        private float[] fanDistance = (float[])DefaultFanDistances.Clone();

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

        private byte[] _currentOutput = new byte[FanCount];

        // A running preset keeps blowing until StopWind; it is not saved with the scene.
        private float _seed;
        private double _startTime;

        [field: NonSerialized] public bool IsBlowing { get; private set; }

        [field: NonSerialized] public WindPreset ActivePreset { get; private set; }

        [field: NonSerialized] public float CurrentPower { get; private set; }

        // The latest fan outputs of the running preset; all zero while stopped.
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
            if (IsBlowing) Tick();
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
            Tick();
        }

        public void StopWind()
        {
            IsBlowing = false;
            CurrentPower = 0f;
            _currentOutput = new byte[FanCount];
#if UNITY_EDITOR
            EditorApplication.update -= EditorTick;
            SceneView.RepaintAll();
#endif
        }

        private void Tick()
        {
            CurrentPower = WindPresets.Power(ActivePreset, (float)(Now - _startTime), _seed);
            _currentOutput = CalculateFanPower(ReferenceCamera, presetWindDirection, CurrentPower);
        }

        // windDir is relative to playerCamera (x: right, y: up, z: forward) and
        // points where the wind travels; only its direction is used. power is
        // 0-1, where 1 is the strongest wind.
        public byte[] CalculateFanPower(Transform playerCamera, Vector3 windDir, float power)
        {
            if (!playerCamera) throw new ArgumentNullException(nameof(playerCamera));
            var output = new byte[FanCount];
            var desiredWindDirection = playerCamera.TransformDirection(windDir).normalized;
            if (desiredWindDirection == Vector3.zero) return output;

            var strength = MaxOutput * Mathf.Clamp01(power);
            var playerPosition = playerCamera.position;
            for (var i = 0; i < FanCount; i++)
            {
                var fanDirection = (playerPosition - GetFanPosition(playerCamera, i)).normalized;
                var dot = Vector3.Dot(desiredWindDirection, fanDirection);
                output[i] = (byte)Mathf.Clamp(Mathf.RoundToInt(strength * Mathf.Max(0f, dot)), 0, MaxOutput);
            }

            return output;
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

        // While a preset blows, the gizmo follows it; otherwise it shows the last test.
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
            var shownDirection = IsBlowing ? presetWindDirection : appliedTestWindDirection;
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