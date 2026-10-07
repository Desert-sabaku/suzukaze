using System.Runtime.InteropServices;
using UnityEngine;
using UnityEngine.Rendering;

// 水面を「カメラの近くほど細かい格子」のメッシュで描き、WaterWaves.compute で頂点を波で動かす。
// MeshRenderer はマテリアルの置き場所として残し、描画はこのコンポーネントが行う (MeshRenderer は無効にしておく)。
//
// 波の大きさ・向き・波長はマテリアルの 1st/2nd Wave の値から作る (シェーダー側の EnableWave は OFF にしておく)。
//   1st_Wave_Length / 2nd_Wave_Length: 一番長い波 / 短い波の目安
//   1st_Wave_Height + 2nd_Wave_Height: 波の高さの目安 (さらにこのコンポーネントの heightScale をかける)
//   1st_Wave_Direction: 波が進む主な向き
//   1st/2nd_Wave_Sharpness: 波頭の尖り具合, 1st_Wave_Speed: 速さの倍率
[ExecuteAlways]
[RequireComponent(typeof(MeshRenderer))]
public class WaterSurfaceMesh : MonoBehaviour
{
    [Tooltip("片側の分割数。多いほど遠くの波の形が崩れにくいが重くなる")]
    [Range(64, 1024)] public int resolution = 768;
    [Tooltip("細かい格子で覆うカメラからの距離")]
    public float detailRadius = 3000f;
    [Tooltip("水平線まで水面を伸ばす距離")]
    public float horizonRadius = 50000f;
    [Tooltip("波で上下する最大の高さ (カリング用)。波がこれより高いときは自動で広げる")]
    public float maxWaveHeight = 5f;

    [Header("Waves")]
    public ComputeShader waveCompute;
    [Tooltip("波の高さの倍率。マテリアルの 1st/2nd_Wave_Height から決まる高さにかける (寄せ波の高さも一緒に変わる)")]
    [Min(0f)] public float heightScale = 1f;
    [Tooltip("重ねる波の数")]
    [Range(1, 32)] public int waveCount = 16;
    [Tooltip("波の並びを決める乱数のシード")]
    public int seed = 1234;
    [Tooltip("波の向きのばらつき (度)。短い波ほど大きくばらつく")]
    [Range(0f, 90f)] public float directionSpread = 35f;

    [Header("Shore")]
    [Tooltip("この水深より浅いところで波が弱まり、寄せ波に変わる")]
    public float shoalDepth = 3f;
    [Tooltip("寄せ波で水位が上がる高さ (波の高さに対する倍率)")]
    public float swashScale = 0.6f;
    [Tooltip("水面よりこれ以上高い陸には寄せ波を上げない")]
    public float runupLimit = 0.8f;

    [StructLayout(LayoutKind.Sequential)]
    struct Wave
    {
        public Vector2 dir;
        public float k, amp, omega, phase, q, pad;
    }

    const int VertexStride = 48; // position(12) normal(12) tangent(16) uv(8)
    static readonly int WavesId = Shader.PropertyToID("_Waves");
    static readonly int BasePositionsId = Shader.PropertyToID("_BasePositions");
    static readonly int VerticesId = Shader.PropertyToID("_Vertices");
    static readonly int ShoreDepthId = Shader.PropertyToID("_ShoreDepth");
    static readonly int VertexCountId = Shader.PropertyToID("_VertexCount");
    static readonly int WaveCountId = Shader.PropertyToID("_WaveCount");
    static readonly int StrideId = Shader.PropertyToID("_Stride");
    static readonly int CenterId = Shader.PropertyToID("_Center");
    static readonly int WaveTimeId = Shader.PropertyToID("_WaveTime");
    static readonly int ShoreRectId = Shader.PropertyToID("_ShoreRect");
    static readonly int ShoreEnabledId = Shader.PropertyToID("_ShoreEnabled");
    static readonly int ShoalDepthId = Shader.PropertyToID("_ShoalDepth");
    static readonly int SwashHeightId = Shader.PropertyToID("_SwashHeight");
    static readonly int RunupLimitId = Shader.PropertyToID("_RunupLimit");
    static readonly int SwashOmegaId = Shader.PropertyToID("_SwashOmega");
    static readonly int GridSpacingId = Shader.PropertyToID("_GridSpacing");
    static readonly int DetailRadiusId = Shader.PropertyToID("_DetailRadius");

    MeshRenderer meshRenderer;
    Mesh mesh;
    GraphicsBuffer vertexBuffer;
    ComputeBuffer basePositions;
    ComputeBuffer waveBuffer;
    Wave[] waves;
    Texture2D shoreDepth;
    Vector4 shoreRect;
    float gridSpacing;
    bool rebuildRequested;
    float[] depthData;      // shoreDepth と同じ水深 (CPU で波の高さを求めるとき用)
    int depthWidth, depthHeight;
    float waveHeight;       // 最後に作った波の高さの目安
    Vector2 gameCenter;     // ゲームカメラ用の格子の中心 (遠くの短い波を消す範囲を合わせる)
    bool hasGameCenter;

    float WaveTime => Application.isPlaying ? Time.timeSinceLevelLoad : Time.realtimeSinceStartup;
    float EffectiveShoalDepth => Mathf.Max(0.01f, shoalDepth, waveHeight * 1.5f);

    void OnEnable()
    {
        meshRenderer = GetComponent<MeshRenderer>();
        RenderPipelineManager.beginCameraRendering += OnBeginCameraRendering;
    }

    void OnDisable()
    {
        RenderPipelineManager.beginCameraRendering -= OnBeginCameraRendering;
        Release();
    }

    // OnValidate と描画コールバックの中ではメッシュを破棄できないので、作り直しは Update で行う
    void OnValidate() => rebuildRequested = true;

    void Update()
    {
        if (!rebuildRequested) return;
        rebuildRequested = false;
        Release();
    }

    void Release()
    {
        vertexBuffer?.Dispose();
        vertexBuffer = null;
        basePositions?.Release();
        basePositions = null;
        waveBuffer?.Release();
        waveBuffer = null;
        DestroySafe(mesh);
        mesh = null;
        DestroySafe(shoreDepth);
        shoreDepth = null;
    }

    static void DestroySafe(Object o)
    {
        if (o == null) return;
        if (Application.isPlaying) Destroy(o);
        else DestroyImmediate(o);
    }

    void OnBeginCameraRendering(ScriptableRenderContext context, Camera cam)
    {
        if (cam.cameraType == CameraType.Reflection || cam.cameraType == CameraType.Preview) return;
        if ((cam.cullingMask & (1 << gameObject.layer)) == 0) return;
        var material = meshRenderer != null ? meshRenderer.sharedMaterial : null;
        if (material == null || waveCompute == null || !SystemInfo.supportsComputeShaders) return;
        if (mesh == null) BuildMesh();
        // シーンを開いた直後などで地形がまだ無いときに作った水深の地図は、地形が現れたら作り直す
        if (shoreDepth == null || (shoreRect.z <= 0f && Terrain.activeTerrains.Length > 0)) BakeShoreDepth();

        // 格子の中心をカメラの真下に置く。波は世界座標で計算するので、中心を動かしても波の位置はずれない
        const float snap = 10f;
        Vector3 p = cam.transform.position;
        var center = new Vector3(Mathf.Round(p.x / snap) * snap, transform.position.y, Mathf.Round(p.z / snap) * snap);

        float height = UpdateWaves(material);
        if (cam.cameraType == CameraType.Game)
        {
            gameCenter = new Vector2(center.x, center.z);
            hasGameCenter = true;
        }
        // URP はカメラごとに描画を送り出すので、このカメラ用の頂点を描画の直前に計算しておく
        waveCompute.SetBuffer(0, WavesId, waveBuffer);
        waveCompute.SetBuffer(0, BasePositionsId, basePositions);
        waveCompute.SetBuffer(0, VerticesId, vertexBuffer);
        waveCompute.SetTexture(0, ShoreDepthId, shoreDepth);
        waveCompute.SetInt(VertexCountId, mesh.vertexCount);
        waveCompute.SetInt(WaveCountId, waves.Length);
        waveCompute.SetInt(StrideId, VertexStride);
        waveCompute.SetVector(CenterId, center);
        waveCompute.SetFloat(WaveTimeId, WaveTime);
        waveCompute.SetVector(ShoreRectId, shoreRect);
        waveCompute.SetFloat(ShoreEnabledId, shoreRect.z > 0f ? 1f : 0f);
        // 波が高いほど深いところから弱め始める
        waveCompute.SetFloat(ShoalDepthId, EffectiveShoalDepth);
        waveCompute.SetFloat(SwashOmegaId, waves[0].omega);
        waveCompute.SetFloat(SwashHeightId, height * swashScale);
        waveCompute.SetFloat(RunupLimitId, Mathf.Max(0.01f, runupLimit));
        waveCompute.SetFloat(GridSpacingId, gridSpacing);
        waveCompute.SetFloat(DetailRadiusId, detailRadius);
        waveCompute.Dispatch(0, Mathf.CeilToInt(mesh.vertexCount / 64f), 1, 1);

        // 波を高くしてもカメラの外と判定されないよう、上下の範囲を波の最大の高さ以上にする
        float extent = Mathf.Max(maxWaveHeight, height * (1.6f + swashScale));

        var rp = new RenderParams(material)
        {
            camera = cam,
            layer = gameObject.layer,
            renderingLayerMask = meshRenderer.renderingLayerMask,
            shadowCastingMode = ShadowCastingMode.Off,
            receiveShadows = meshRenderer.receiveShadows,
            lightProbeUsage = LightProbeUsage.Off,
            reflectionProbeUsage = ReflectionProbeUsage.BlendProbes,
            motionVectorMode = MotionVectorGenerationMode.Camera,
            worldBounds = new Bounds(center, new Vector3(horizonRadius * 2f, extent * 2f, horizonRadius * 2f)),
        };
        Graphics.RenderMesh(rp, mesh, 0, Matrix4x4.Translate(center));
    }

    // マテリアルの波の値から、向き・波長・位相がばらばらな波の組を作る。戻り値は波の高さの目安
    float UpdateWaves(Material material)
    {
        float longest = Mathf.Max(0.5f, material.GetFloat("_1st_Wave_Length"));
        float shortest = Mathf.Clamp(material.GetFloat("_2nd_Wave_Length") * 0.35f, 0.25f, longest);
        float height = Mathf.Max(0f, material.GetFloat("_1st_Wave_Height") + material.GetFloat("_2nd_Wave_Height")) * Mathf.Max(0f, heightScale);
        float sharpness = Mathf.Clamp01(Mathf.Max(material.GetFloat("_1st_Wave_Sharpness"), material.GetFloat("_2nd_Wave_Sharpness")));
        float speed = material.GetFloat("_1st_Wave_Speed");
        Vector4 d = material.GetVector("_1st_Wave_Direction");
        float mainAngle = Mathf.Atan2(d.z, d.x);

        int count = Mathf.Clamp(waveCount, 1, 32);
        if (waves == null || waves.Length != count) waves = new Wave[count];

        var random = new System.Random(seed);
        float ampSum = 0f;
        for (int i = 0; i < count; i++)
        {
            float t = count == 1 ? 0f : i / (count - 1f);
            // 波長は長い方から短い方へ対数的に並べ、少しだけずらして等間隔にならないようにする
            float length = longest * Mathf.Pow(shortest / longest, t) * Mathf.Lerp(0.85f, 1.15f, (float)random.NextDouble());
            float spread = directionSpread * Mathf.Deg2Rad * Mathf.Lerp(0.5f, 1.5f, t);
            float angle = mainAngle + ((float)random.NextDouble() * 2f - 1f) * spread;
            float k = 2f * Mathf.PI / length;
            waves[i] = new Wave
            {
                dir = new Vector2(Mathf.Cos(angle), Mathf.Sin(angle)),
                k = k,
                amp = Mathf.Pow(length, 1.5f), // 長いうねりほど高くし、あとで合計を合わせる
                omega = Mathf.Sqrt(9.8f * k) * speed,
                phase = (float)random.NextDouble() * 2f * Mathf.PI,
            };
            ampSum += waves[i].amp;
        }
        // ばらばらな位相の波は打ち消し合うので、合計を高さの目安の 1.6 倍にして山の高さを目安に近づける
        float scale = ampSum > 0f ? height * 1.6f / ampSum : 0f;
        for (int i = 0; i < count; i++)
        {
            waves[i].amp *= scale;
            float ka = waves[i].k * waves[i].amp;
            waves[i].q = ka > 0f ? sharpness / (ka * count) : 0f;
        }

        if (waveBuffer == null || waveBuffer.count != count)
        {
            waveBuffer?.Release();
            waveBuffer = new ComputeBuffer(count, Marshal.SizeOf<Wave>());
        }
        waveBuffer.SetData(waves);
        waveHeight = height;
        return height;
    }

    // 水面の点 (波が無いときの位置 worldXZ) が今どれだけ動いているかと、その点の法線を返す。
    // 浮かぶ物をこの点と一緒に動かすと、波に乗って上下・前後に揺れる。計算は WaterWaves.compute と同じ
    public bool SampleSurface(Vector2 worldXZ, out Vector3 displacement, out Vector3 normal)
    {
        displacement = Vector3.zero;
        normal = Vector3.up;
        if (waves == null)
        {
            var material = meshRenderer != null ? meshRenderer.sharedMaterial : null;
            if (material == null) return false;
            UpdateWaves(material);
        }

        float shoal = EffectiveShoalDepth;
        float depth = SampleDepthCpu(worldXZ);
        float att = Mathf.SmoothStep(0f, 1f, Mathf.Clamp01(depth / shoal));
        float spacing = 0f;
        if (hasGameCenter)
        {
            var local = worldXZ - gameCenter;
            float d = Mathf.Max(Mathf.Abs(local.x), Mathf.Abs(local.y));
            spacing = d < detailRadius ? gridSpacing * Mathf.Sqrt(d) : 1e6f;
        }

        float time = WaveTime;
        var n = Vector3.up;
        foreach (var w in waves)
        {
            float amp = w.amp;
            if (spacing > 0f) amp *= Mathf.Clamp01((2f * Mathf.PI / (w.k * spacing) - 2f) / 2f);
            float theta = w.k * Vector2.Dot(w.dir, worldXZ) - w.omega * time + w.phase;
            float sin = Mathf.Sin(theta), cos = Mathf.Cos(theta);
            displacement.x += w.q * amp * w.dir.x * cos;
            displacement.z += w.q * amp * w.dir.y * cos;
            displacement.y += amp * sin;
            float wa = w.k * amp;
            n.x -= w.dir.x * wa * cos;
            n.z -= w.dir.y * wa * cos;
            n.y -= w.q * wa * sin;
        }
        displacement *= att;
        normal = Vector3.Lerp(Vector3.up, n, att).normalized;

        if (displacement.y < 0f)
        {
            float room = Mathf.Max(depth, 0f) * 0.8f + 1e-3f;
            displacement.y = -room * (1f - Mathf.Exp(displacement.y / room));
        }
        float shore = (1f - Mathf.SmoothStep(0f, 1f, Mathf.Clamp01(Mathf.Max(depth, 0f) / shoal)))
            * (1f - Mathf.SmoothStep(0f, 1f, Mathf.Clamp01(-depth / Mathf.Max(0.01f, runupLimit))));
        float along = 1.5f * Mathf.Sin(worldXZ.x * 0.021f + worldXZ.y * 0.034f) + Mathf.Sin(worldXZ.x * -0.047f + worldXZ.y * 0.013f);
        float swashTheta = -depth * (Mathf.PI / shoal) - waves[0].omega * time + along;
        displacement.y += waveHeight * swashScale * shore * (0.5f + 0.5f * Mathf.Sin(swashTheta));
        return true;
    }

    // シェーダーの SampleLevel (バイリニア, 範囲外は深い海) と同じように水深を読む
    float SampleDepthCpu(Vector2 xz)
    {
        if (depthData == null || shoreRect.z <= 0f) return 1000f;
        float u = (xz.x - shoreRect.x) * shoreRect.z, v = (xz.y - shoreRect.y) * shoreRect.w;
        if (u < 0f || v < 0f || u > 1f || v > 1f) return 1000f;
        float fx = Mathf.Clamp(u * depthWidth - 0.5f, 0f, depthWidth - 1f);
        float fy = Mathf.Clamp(v * depthHeight - 0.5f, 0f, depthHeight - 1f);
        int x0 = (int)fx, y0 = (int)fy;
        int x1 = Mathf.Min(x0 + 1, depthWidth - 1), y1 = Mathf.Min(y0 + 1, depthHeight - 1);
        float tx = fx - x0, ty = fy - y0;
        float a = Mathf.Lerp(depthData[y0 * depthWidth + x0], depthData[y0 * depthWidth + x1], tx);
        float b = Mathf.Lerp(depthData[y1 * depthWidth + x0], depthData[y1 * depthWidth + x1], tx);
        return Mathf.Lerp(a, b, ty);
    }

    // 地形の高さから水深の地図を作る (水面より上の陸は負の値)
    void BakeShoreDepth()
    {
        shoreRect = Vector4.zero;
        var terrains = Terrain.activeTerrains;
        var bounds = new Rect();
        bool any = false;
        foreach (var t in terrains)
        {
            var tp = t.transform.position;
            var size = t.terrainData.size;
            var r = new Rect(tp.x, tp.z, size.x, size.z);
            bounds = any ? Rect.MinMaxRect(Mathf.Min(bounds.xMin, r.xMin), Mathf.Min(bounds.yMin, r.yMin),
                Mathf.Max(bounds.xMax, r.xMax), Mathf.Max(bounds.yMax, r.yMax)) : r;
            any = true;
        }

        int w = any ? Mathf.Clamp(Mathf.CeilToInt(bounds.width / 2f), 2, 1024) : 2;
        int h = any ? Mathf.Clamp(Mathf.CeilToInt(bounds.height / 2f), 2, 1024) : 2;
        var depths = new float[w * h];
        float waterY = transform.position.y;
        for (int z = 0; z < h; z++)
        {
            for (int x = 0; x < w; x++)
            {
                float depth = 1000f;
                if (any)
                {
                    var pos = new Vector3(bounds.xMin + (x + 0.5f) / w * bounds.width, 0f, bounds.yMin + (z + 0.5f) / h * bounds.height);
                    foreach (var t in terrains)
                    {
                        var tp = t.transform.position;
                        var size = t.terrainData.size;
                        if (pos.x < tp.x || pos.z < tp.z || pos.x > tp.x + size.x || pos.z > tp.z + size.z) continue;
                        depth = waterY - (t.SampleHeight(pos) + tp.y);
                        break;
                    }
                }
                depths[z * w + x] = depth;
            }
        }

        // 描画コールバックの中では破棄できないので、作り直すときは同じテクスチャの大きさを変えて使う
        if (shoreDepth == null)
        {
            shoreDepth = new Texture2D(w, h, TextureFormat.RFloat, false, true)
            {
                name = "WaterShoreDepth",
                hideFlags = HideFlags.DontSave,
                wrapMode = TextureWrapMode.Clamp,
                filterMode = FilterMode.Bilinear,
            };
        }
        else shoreDepth.Reinitialize(w, h, TextureFormat.RFloat, false);
        shoreDepth.SetPixelData(depths, 0);
        shoreDepth.Apply(false, false);
        depthData = depths;
        depthWidth = w;
        depthHeight = h;
        if (any) shoreRect = new Vector4(bounds.xMin, bounds.yMin, 1f / bounds.width, 1f / bounds.height);
    }

    // 中心ほど間隔が狭い座標列 (x = r * u^2) に、水平線までの外周を足した格子を作る
    void BuildMesh()
    {
        int inner = Mathf.Max(2, resolution - resolution % 2);
        // x = r * u^2 で u を 2 / inner ずつ進めるので、中心から d の間隔は 4 * sqrt(r * d) / inner
        gridSpacing = 4f * Mathf.Sqrt(detailRadius) / inner;
        var coords = new float[inner + 1 + 4];
        coords[0] = -horizonRadius;
        coords[1] = -Mathf.Max(detailRadius * 2f, horizonRadius * 0.1f);
        for (int i = 0; i <= inner; i++)
        {
            float u = -1f + 2f * i / inner;
            coords[i + 2] = Mathf.Sign(u) * detailRadius * u * u;
        }
        coords[inner + 3] = -coords[1];
        coords[inner + 4] = horizonRadius;

        int n = coords.Length;
        var vertices = new float[n * n * (VertexStride / 4)];
        var basePos = new Vector2[n * n];
        for (int z = 0; z < n; z++)
        {
            for (int x = 0; x < n; x++)
            {
                int i = z * n + x;
                int o = i * (VertexStride / 4);
                vertices[o + 0] = coords[x];
                vertices[o + 2] = coords[z];
                vertices[o + 4] = 1f;                                   // normal
                vertices[o + 6] = 1f; vertices[o + 9] = -1f;             // tangent
                vertices[o + 10] = coords[x] / (horizonRadius * 2f) + 0.5f; // uv
                vertices[o + 11] = coords[z] / (horizonRadius * 2f) + 0.5f;
                basePos[i] = new Vector2(coords[x], coords[z]);
            }
        }

        var indices = new int[(n - 1) * (n - 1) * 6];
        int t = 0;
        for (int z = 0; z < n - 1; z++)
        {
            for (int x = 0; x < n - 1; x++)
            {
                int i = z * n + x;
                indices[t++] = i;
                indices[t++] = i + n;
                indices[t++] = i + 1;
                indices[t++] = i + 1;
                indices[t++] = i + n;
                indices[t++] = i + n + 1;
            }
        }

        mesh = new Mesh { name = "WaterSurfaceMesh", hideFlags = HideFlags.DontSave };
        mesh.vertexBufferTarget |= GraphicsBuffer.Target.Raw;
        mesh.SetVertexBufferParams(n * n,
            new VertexAttributeDescriptor(VertexAttribute.Position, VertexAttributeFormat.Float32, 3),
            new VertexAttributeDescriptor(VertexAttribute.Normal, VertexAttributeFormat.Float32, 3),
            new VertexAttributeDescriptor(VertexAttribute.Tangent, VertexAttributeFormat.Float32, 4),
            new VertexAttributeDescriptor(VertexAttribute.TexCoord0, VertexAttributeFormat.Float32, 2));
        mesh.SetVertexBufferData(vertices, 0, 0, vertices.Length, 0, MeshUpdateFlags.DontRecalculateBounds | MeshUpdateFlags.DontValidateIndices);
        mesh.SetIndexBufferParams(indices.Length, IndexFormat.UInt32);
        mesh.SetIndexBufferData(indices, 0, 0, indices.Length, MeshUpdateFlags.DontRecalculateBounds | MeshUpdateFlags.DontValidateIndices);
        mesh.subMeshCount = 1;
        mesh.SetSubMesh(0, new SubMeshDescriptor(0, indices.Length), MeshUpdateFlags.DontRecalculateBounds);
        mesh.bounds = new Bounds(Vector3.zero, new Vector3(horizonRadius * 2f, maxWaveHeight * 2f, horizonRadius * 2f));
        mesh.UploadMeshData(true);

        vertexBuffer = mesh.GetVertexBuffer(0);
        basePositions = new ComputeBuffer(basePos.Length, sizeof(float) * 2);
        basePositions.SetData(basePos);
    }
}
