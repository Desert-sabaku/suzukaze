using Features.Common.Scripts;
using UnityEngine;

namespace Features.Lighthouse.Scripts
{
    /// <summary>
    ///     灯台の灯火。光の筋を回転させ、筋がカメラを向いた瞬間に光源を強く光らせる。
    ///     BetweenSceneTimeManager の時刻に合わせて点灯・消灯する。
    ///     このコンポーネントはランプの中心に置く
    /// </summary>
    public class LighthouseBeacon : MonoBehaviour
    {
        private const float FallbackHour = 12f;
        private static readonly int IntensityId = Shader.PropertyToID("_Intensity");
        private static readonly int EmissionColorId = Shader.PropertyToID("_EmissionColor");

        [Header("点灯時刻")]
        [Tooltip("この時刻 (0〜24) に点灯する。日没は 18 時")]
        [SerializeField] [Range(0f, 24f)] private float turnOnHour = 17.5f;

        [Tooltip("この時刻 (0〜24) に消灯する。日の出は 6 時")]
        [SerializeField] [Range(0f, 24f)] private float turnOffHour = 6.5f;

        [Tooltip("点灯・消灯しきるまでの秒数")]
        [SerializeField] [Min(0f)] private float fadeSeconds = 3f;

        [Header("回転")]
        [Tooltip("光の筋を回転させる。オフにするとカメラの方向 (カメラを狙わない場合は正面) に向けたまま止める")]
        [SerializeField] private bool rotate = true;

        [Tooltip("1 回転にかかる秒数")]
        [SerializeField] [Min(0.1f)] private float secondsPerRevolution = 12f;

        [Tooltip("光の筋の本数。等間隔に並ぶ")]
        [SerializeField] [Range(1, 6)] private int beamCount = 2;

        [Tooltip("光の筋の俯角 (度)。正の値で下を向く。カメラを狙う場合は開始時に上書きされる")]
        [SerializeField] [Range(-10f, 45f)] private float beamPitch = 1f;

        [Tooltip("開始時にメインカメラの位置を通るよう仰角を合わせる")]
        [SerializeField] private bool aimAtCamera = true;

        [Tooltip("カメラを狙うとき、カメラの位置からどれだけ上下にずらすか (m)。負の値で足元寄りを照らす")]
        [SerializeField] private float aimHeightOffset = -2f;

        [Header("光の筋")]
        [SerializeField] private Material beamMaterial;

        [SerializeField] [Min(1f)] private float beamLength = 400f;
        [SerializeField] [Min(0f)] private float beamStartRadius = 1.5f;
        [SerializeField] [Min(0f)] private float beamEndRadius = 28f;
        [SerializeField] [Min(0f)] private float beamIntensity = 0.35f;

        [Header("照らす光")]
        [Tooltip("光の筋に沿って地面やオブジェクトを照らすスポットライトを付ける")]
        [SerializeField] private bool castLight = true;

        [SerializeField] private Color lightColor = new(1f, 0.95f, 0.8f);

        [Tooltip("狙った位置での明るさ。距離に応じてライトの強度を決める (太陽のライト強度 1 が目安)")]
        [SerializeField] [Min(0f)] private float lightIlluminance = 6f;

        [Tooltip("照らす範囲の縁をぼかす割合 (0 でくっきり)")]
        [SerializeField] [Range(0f, 1f)] private float lightEdgeSoftness = 0.5f;

        [Header("まぶしさ")]
        [SerializeField] private Material glareMaterial;

        [Tooltip("筋がカメラを向いていないときのまぶしさ")]
        [SerializeField] [Min(0f)] private float glareIdleIntensity = 0.4f;

        [Tooltip("筋がカメラを向いたときに上乗せするまぶしさ")]
        [SerializeField] [Min(0f)] private float glareFlashIntensity = 5f;

        [Tooltip("閃光が見える水平方向の角度幅 (度)")]
        [SerializeField] [Min(0.1f)] private float flashWidthDegrees = 6f;

        [Header("ランプ")]
        [Tooltip("発光させるランプのガラス")]
        [SerializeField] private Renderer lampRenderer;

        [Tooltip("点灯中の発光の強さ (マテリアルの発光色に対する倍率)")]
        [SerializeField] [Min(0f)] private float lampEmissionIdle = 3f;

        [Tooltip("閃光時に上乗せする発光の強さ")]
        [SerializeField] [Min(0f)] private float lampEmissionFlash = 12f;

        private Renderer[] _beamRenderers;
        private Transform[] _beams;
        private MaterialPropertyBlock _block;
        private float _aimYaw;
        private Renderer _glareRenderer;
        private bool _isOn;
        private Color _lampBaseEmission;
        private float _level;
        private float _lightIntensity;
        private Light[] _lights;
        private Transform _rotor;

        private static float CurrentHour
        {
            get
            {
                var timeManager = BetweenSceneTimeManager.Instance;
                return timeManager ? timeManager.CurrentHour : FallbackHour;
            }
        }

        private void Awake()
        {
            _block = new MaterialPropertyBlock();
            if (lampRenderer) _lampBaseEmission = lampRenderer.sharedMaterial.GetColor(EmissionColorId);
            var targetDistance = AimAtCamera();
            BuildBeams(targetDistance);
            BuildGlare();
        }

        private void Start()
        {
            // 開始時点の状態にはフェードせずに合わせる
            _isOn = ShouldBeOn(CurrentHour);
            _level = _isOn ? 1f : 0f;
            Apply();
        }

        private void Update()
        {
            _isOn = ShouldBeOn(CurrentHour);
            var step = fadeSeconds > 0f ? Time.deltaTime / fadeSeconds : 1f;
            _level = Mathf.MoveTowards(_level, _isOn ? 1f : 0f, step);

            var yaw = rotate ? Time.time * 360f / secondsPerRevolution : _aimYaw;
            _rotor.localRotation = Quaternion.Euler(0f, yaw, 0f);
            Apply();
        }

        private void OnDestroy()
        {
            if (_beamRenderers == null || _beamRenderers.Length == 0) return;
            Destroy(_beamRenderers[0].GetComponent<MeshFilter>().sharedMesh);
            if (_glareRenderer) Destroy(_glareRenderer.GetComponent<MeshFilter>().sharedMesh);
        }

        private void OnDrawGizmosSelected()
        {
            Gizmos.color = Color.yellow;
            for (var i = 0; i < beamCount; i++)
            {
                var rotation = transform.rotation * Quaternion.Euler(beamPitch, 360f / beamCount * i, 0f);
                Gizmos.DrawLine(transform.position, transform.position + rotation * Vector3.forward * beamLength);
            }
        }

        /// <summary>
        ///     点灯時刻から消灯時刻までの間 (日付をまたぐ場合も含む) なら true
        /// </summary>
        private bool ShouldBeOn(float hour)
        {
            return turnOnHour <= turnOffHour
                ? hour >= turnOnHour && hour < turnOffHour
                : hour >= turnOnHour || hour < turnOffHour;
        }

        private void Apply()
        {
            var visible = _level > 0f;
            var flash = visible ? FlashTowardCamera() : 0f;

            _block.Clear();
            _block.SetFloat(IntensityId, beamIntensity * _level);
            foreach (var beam in _beamRenderers)
            {
                beam.enabled = visible;
                beam.SetPropertyBlock(_block);
            }

            if (_glareRenderer)
            {
                _glareRenderer.enabled = visible;
                _block.Clear();
                _block.SetFloat(IntensityId, (glareIdleIntensity + glareFlashIntensity * flash) * _level);
                _glareRenderer.SetPropertyBlock(_block);
            }

            foreach (var beamLight in _lights)
            {
                beamLight.enabled = visible;
                beamLight.intensity = _lightIntensity * _level;
            }

            if (lampRenderer)
            {
                // 消灯中はマテリアル本来の発光に戻す
                var gain = Mathf.Lerp(1f, lampEmissionIdle + lampEmissionFlash * flash, _level);
                _block.Clear();
                _block.SetColor(EmissionColorId, _lampBaseEmission * gain);
                lampRenderer.SetPropertyBlock(_block);
            }
        }

        /// <summary>
        ///     いずれかの光の筋がカメラの方向を向いている度合い (0〜1)。
        ///     実際の灯台と同じく縦方向には広がっているとみなし、水平方向の角度だけで決める
        /// </summary>
        private float FlashTowardCamera()
        {
            var cam = Camera.main;
            if (!cam) return 0f;

            var toCamera = Vector3.ProjectOnPlane(cam.transform.position - transform.position, Vector3.up);
            var flash = 0f;
            foreach (var beam in _beams)
            {
                var direction = Vector3.ProjectOnPlane(beam.forward, Vector3.up);
                var t = Vector3.Angle(direction, toCamera) / flashWidthDegrees;
                flash = Mathf.Max(flash, Mathf.Exp(-t * t));
            }

            return flash;
        }

        /// <summary>
        ///     カメラを狙う設定なら、光の筋がカメラの位置を通るよう仰角と、回転しないときの向きを合わせる。
        ///     照らしたい位置までの距離を返す (狙わない場合は光の筋の長さ)
        /// </summary>
        private float AimAtCamera()
        {
            var cam = Camera.main;
            if (!aimAtCamera || !cam) return beamLength;

            var toTarget = cam.transform.position + Vector3.up * aimHeightOffset - transform.position;
            var horizontal = Vector3.ProjectOnPlane(toTarget, Vector3.up).magnitude;
            beamPitch = Mathf.Atan2(-toTarget.y, horizontal) * Mathf.Rad2Deg;
            var local = transform.InverseTransformDirection(toTarget);
            _aimYaw = Mathf.Atan2(local.x, local.z) * Mathf.Rad2Deg;
            return toTarget.magnitude;
        }

        private void BuildBeams(float targetDistance)
        {
            _rotor = new GameObject("Beams").transform;
            _rotor.SetParent(transform, false);

            // 光の筋と同じ広がりで照らす
            var spotAngle = 2f * Mathf.Atan2(beamEndRadius - beamStartRadius, beamLength) * Mathf.Rad2Deg;
            // 点光源の明るさは距離の 2 乗で弱まるので、狙った位置で lightIlluminance になるよう逆算する
            _lightIntensity = lightIlluminance * targetDistance * targetDistance;

            var mesh = CreateConeMesh(beamStartRadius, beamEndRadius, beamLength, 32);
            _beams = new Transform[beamCount];
            _beamRenderers = new Renderer[beamCount];
            _lights = new Light[castLight ? beamCount : 0];
            for (var i = 0; i < beamCount; i++)
            {
                var beam = new GameObject($"Beam {i}");
                beam.transform.SetParent(_rotor, false);
                beam.transform.localRotation = Quaternion.Euler(beamPitch, 360f / beamCount * i, 0f);
                beam.AddComponent<MeshFilter>().sharedMesh = mesh;
                var meshRenderer = beam.AddComponent<MeshRenderer>();
                meshRenderer.sharedMaterial = beamMaterial;
                meshRenderer.shadowCastingMode = UnityEngine.Rendering.ShadowCastingMode.Off;
                meshRenderer.receiveShadows = false;
                _beams[i] = beam.transform;
                _beamRenderers[i] = meshRenderer;

                if (!castLight) continue;
                // ランプの囲いに遮られないよう影は落とさない
                var beamLight = beam.AddComponent<Light>();
                beamLight.type = LightType.Spot;
                beamLight.color = lightColor;
                // URP は range に近づくほど光を弱めるので、狙った位置より十分遠くまで届かせる
                beamLight.range = Mathf.Max(beamLength, targetDistance * 2f);
                beamLight.spotAngle = spotAngle;
                beamLight.innerSpotAngle = spotAngle * (1f - lightEdgeSoftness);
                beamLight.shadows = LightShadows.None;
                _lights[i] = beamLight;
            }
        }

        private void BuildGlare()
        {
            if (!glareMaterial) return;

            var glare = new GameObject("Glare");
            glare.transform.SetParent(transform, false);
            glare.AddComponent<MeshFilter>().sharedMesh = CreateGlareMesh();
            _glareRenderer = glare.AddComponent<MeshRenderer>();
            _glareRenderer.sharedMaterial = glareMaterial;
            _glareRenderer.shadowCastingMode = UnityEngine.Rendering.ShadowCastingMode.Off;
            _glareRenderer.receiveShadows = false;
        }

        /// <summary>
        ///     +Z 方向に伸びる、両端の開いた円錐台。uv.y は根元 0、先端 1
        /// </summary>
        private static Mesh CreateConeMesh(float startRadius, float endRadius, float length, int segments)
        {
            var vertices = new Vector3[(segments + 1) * 2];
            var normals = new Vector3[vertices.Length];
            var uvs = new Vector2[vertices.Length];
            var triangles = new int[segments * 6];
            var slope = (endRadius - startRadius) / length;

            for (var i = 0; i <= segments; i++)
            {
                var angle = (float)i / segments * Mathf.PI * 2f;
                var radial = new Vector3(Mathf.Cos(angle), Mathf.Sin(angle), 0f);
                var normal = (radial - Vector3.forward * slope).normalized;
                var u = (float)i / segments;

                vertices[i * 2] = radial * startRadius;
                vertices[i * 2 + 1] = radial * endRadius + Vector3.forward * length;
                normals[i * 2] = normal;
                normals[i * 2 + 1] = normal;
                uvs[i * 2] = new Vector2(u, 0f);
                uvs[i * 2 + 1] = new Vector2(u, 1f);
            }

            for (var i = 0; i < segments; i++)
            {
                var v = i * 2;
                var t = i * 6;
                triangles[t] = v;
                triangles[t + 1] = v + 1;
                triangles[t + 2] = v + 2;
                triangles[t + 3] = v + 2;
                triangles[t + 4] = v + 1;
                triangles[t + 5] = v + 3;
            }

            var mesh = new Mesh { name = "Lighthouse Beam" };
            mesh.SetVertices(vertices);
            mesh.SetNormals(normals);
            mesh.SetUVs(0, uvs);
            mesh.SetTriangles(triangles, 0);
            mesh.RecalculateBounds();
            return mesh;
        }

        /// <summary>
        ///     まぶしさ用の四角形。形はシェーダーがカメラに向けて広げるので、ここでは uv だけが意味を持つ
        /// </summary>
        private static Mesh CreateGlareMesh()
        {
            var mesh = new Mesh { name = "Lighthouse Glare" };
            mesh.SetVertices(new[] { Vector3.zero, Vector3.zero, Vector3.zero, Vector3.zero });
            mesh.SetUVs(0, new[] { new Vector2(0, 0), new Vector2(1, 0), new Vector2(0, 1), new Vector2(1, 1) });
            mesh.SetTriangles(new[] { 0, 2, 1, 1, 2, 3 }, 0);
            // 頂点はシェーダーで動かすため、カリングされないよう境界を広げておく
            mesh.bounds = new Bounds(Vector3.zero, Vector3.one * 100f);
            return mesh;
        }
    }
}
