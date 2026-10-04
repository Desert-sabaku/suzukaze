using System;
using UnityEngine;
using UnityEngine.Formats.Alembic.Importer;
using UnityEngine.Rendering;

namespace Features.Gesture_Effect.Scripts
{
    /// <summary>
    ///     打ち水が地面に触れたとみなされるときに，地面を濡らすための濡れ濡れ💦テクスチャマップを生成する
    /// </summary>
    [DisallowMultipleComponent]
    public class GroundWetness : MonoBehaviour
    {
        private static readonly int MapId = Shader.PropertyToID("_GroundWetnessMap");
        private static readonly int RectId = Shader.PropertyToID("_GroundWetnessRect");
        private static readonly int TimeId = Shader.PropertyToID("_GroundWetnessTime");
        private static readonly int LookId = Shader.PropertyToID("_GroundWetnessLook");
        private static readonly int StampRectId = Shader.PropertyToID("_StampRect");
        private static readonly int StampValueId = Shader.PropertyToID("_StampValue");
        private static readonly int ContactYId = Shader.PropertyToID("_ContactY");

        [Header("Source")] [Tooltip("Water renderers whose ground contact is recorded.")] [SerializeField]
        private Renderer[] waterRenderers;

        [Tooltip("Stamping pauses while this player's time is not advancing, so a finished clip " +
                 "left on screen does not keep the ground wet. Optional.")]
        [SerializeField]
        private AlembicStreamPlayer player;

        [SerializeField] private Shader stampShader;

        [Header("Area")]
        [Tooltip("World size of the square area, centered on this transform, that can get wet.")]
        [SerializeField]
        private float areaSize = 0.2f;

        [SerializeField] private int resolution = 512;

        [Tooltip("Ground height comes from this terrain. Without one, this transform's Y is used.")] [SerializeField]
        private Terrain terrain;

        [Tooltip("Water lower than this height above the ground counts as touching it (world units).")] [SerializeField]
        private float contactHeight = 0.003f;

        [Header("Drying")] [SerializeField] private float dryDuration = 20f;

        [Header("Look")] [Range(0f, 1f)] [SerializeField]
        private float darken = 0.5f;

        [Range(0f, 1f)] [SerializeField] private float wetSmoothness = 0.6f;
        [Range(0f, 1f)] [SerializeField] private float normalFlatten = 0.1f;
        [Range(0f, 8f)] [SerializeField] private float blurTexels = 3f;

        [Tooltip("Frequency of the edge noise across the whole area.")] [SerializeField]
        private float edgeNoiseScale = 24f;

        [Range(0f, 1f)] [SerializeField] private float edgeNoise = 0.5f;
        private CommandBuffer _commandBuffer;
        private float _lastPlayerTime = float.NaN;

        private RenderTexture _map;
        private Vector4 _rect;
        private Material _stampMaterial;

        private void Reset()
        {
            player = GetComponent<AlembicStreamPlayer>();
            stampShader = Shader.Find("Hidden/Suzukaze/WetnessStamp");
            terrain = Terrain.activeTerrain;
            waterRenderers = Array.FindAll(GetComponentsInChildren<Renderer>(true),
                r => r.sharedMaterial != null && r.sharedMaterial.shader.name == "Suzukaze/UchimizuWater");
        }

        private void LateUpdate()
        {
            PublishGlobals();
            if (IsWaterMoving()) Stamp();
        }

        private void OnEnable()
        {
            _map = new RenderTexture(resolution, resolution, 0, RenderTextureFormat.RFloat)
            {
                name = "GroundWetnessMap",
                filterMode = FilterMode.Point,
                wrapMode = TextureWrapMode.Clamp
            };
            _map.Create();
            Clear();

            _stampMaterial = new Material(stampShader) { hideFlags = HideFlags.HideAndDontSave };
            _commandBuffer = new CommandBuffer { name = "Ground Wetness Stamp" };

            var center = transform.position;
            var half = areaSize * 0.5f;
            _rect = new Vector4(center.x - half, center.z - half, 1f / areaSize, resolution);
            Shader.SetGlobalTexture(MapId, _map);
            PublishGlobals();
        }

        private void OnDisable()
        {
            Shader.SetGlobalVector(RectId, Vector4.zero);
            _commandBuffer?.Release();
            _commandBuffer = null;
            if (_stampMaterial != null) Destroy(_stampMaterial);
            if (_map != null) _map.Release();
            _map = null;
        }

        private void Clear()
        {
            var previous = RenderTexture.active;
            RenderTexture.active = _map;
            GL.Clear(false, true, Color.clear);
            RenderTexture.active = previous;
        }

        private bool IsWaterMoving()
        {
            if (!player) return true;
            var time = player.CurrentTime;
            var moving = !Mathf.Approximately(time, _lastPlayerTime);
            _lastPlayerTime = time;
            return moving;
        }

        private void Stamp()
        {
            var groundY = terrain
                ? terrain.SampleHeight(transform.position) + terrain.GetPosition().y
                : transform.position.y;

            _stampMaterial.SetVector(StampRectId, _rect);
            _stampMaterial.SetFloat(StampValueId, Time.time + 1f);
            _stampMaterial.SetFloat(ContactYId, groundY + contactHeight);

            _commandBuffer.Clear();
            _commandBuffer.SetRenderTarget(_map);
            var any = false;
            foreach (var r in waterRenderers)
            {
                if (!r || !r.enabled || !r.gameObject.activeInHierarchy) continue;
                _commandBuffer.DrawRenderer(r, _stampMaterial);
                any = true;
            }

            if (any) Graphics.ExecuteCommandBuffer(_commandBuffer);
        }

        private void PublishGlobals()
        {
            Shader.SetGlobalVector(RectId, _rect);
            Shader.SetGlobalVector(TimeId, new Vector4(Time.time, dryDuration, blurTexels, edgeNoiseScale));
            Shader.SetGlobalVector(LookId, new Vector4(darken, wetSmoothness, normalFlatten, edgeNoise));
        }
    }
}