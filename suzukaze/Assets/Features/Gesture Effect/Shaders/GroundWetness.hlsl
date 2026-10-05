// Ground wetness left by the uchimizu splash. Used from GroundWetness.shadersubgraph.
// The globals below are owned by GroundWetness.cs; when it is absent they stay zero and
// the surface passes through unchanged.
#ifndef SUZUKAZE_GROUND_WETNESS_INCLUDED
#define SUZUKAZE_GROUND_WETNESS_INCLUDED

// Per-texel time (+1) at which the water last touched the ground; 0 means never.
TEXTURE2D(_GroundWetnessMap);
float4 _GroundWetnessRect;  // xy: world XZ min, z: 1 / world size (0 = disabled), w: resolution
float4 _GroundWetnessTime;  // x: current time, y: dry duration, z: blur radius (texels), w: edge noise scale
float4 _GroundWetnessLook;  // x: darken, y: wet smoothness, z: normal flatten, w: edge noise

float GroundWetness_Hash(float2 p)
{
    return frac(sin(dot(p, float2(127.1, 311.7))) * 43758.5453);
}

float GroundWetness_ValueNoise(float2 p)
{
    float2 i = floor(p);
    float2 f = frac(p);
    float2 u = f * f * (3.0 - 2.0 * f);
    float a = GroundWetness_Hash(i);
    float b = GroundWetness_Hash(i + float2(1, 0));
    float c = GroundWetness_Hash(i + float2(0, 1));
    float d = GroundWetness_Hash(i + float2(1, 1));
    return lerp(lerp(a, b, u.x), lerp(c, d, u.x), u.y);
}

// Remaining wet life (1 = just wetted, 0 = dry) of a single texel.
float GroundWetness_TexelLife(int2 texel, int resolution)
{
    texel = clamp(texel, 0, resolution - 1);
    float stamp = LOAD_TEXTURE2D(_GroundWetnessMap, texel).r;
    float age = _GroundWetnessTime.x - (stamp - 1.0);
    return stamp > 0.0 ? saturate(1.0 - age / max(_GroundWetnessTime.y, 1e-3)) : 0.0;
}

// Bilinear filtering of the life value. The timestamps themselves must not be filtered,
// and float textures are not filterable on every GPU.
float GroundWetness_Life(float2 uv, int resolution)
{
    float2 p = uv * resolution - 0.5;
    int2 i = (int2)floor(p);
    float2 f = p - i;
    float a = GroundWetness_TexelLife(i, resolution);
    float b = GroundWetness_TexelLife(i + int2(1, 0), resolution);
    float c = GroundWetness_TexelLife(i + int2(0, 1), resolution);
    float d = GroundWetness_TexelLife(i + int2(1, 1), resolution);
    return lerp(lerp(a, b, f.x), lerp(c, d, f.x), f.y);
}

float GroundWetness_Sample(float3 positionWS)
{
    if (_GroundWetnessRect.z <= 0.0)
        return 0.0;

    float2 uv = (positionWS.xz - _GroundWetnessRect.xy) * _GroundWetnessRect.z;
    if (any(uv < 0.0) || any(uv > 1.0))
        return 0.0;

    int resolution = (int)_GroundWetnessRect.w;
    float r = _GroundWetnessTime.z / _GroundWetnessRect.w;
    float life = GroundWetness_Life(uv, resolution) * 0.4
        + GroundWetness_Life(uv + float2( r, 0), resolution) * 0.15
        + GroundWetness_Life(uv + float2(-r, 0), resolution) * 0.15
        + GroundWetness_Life(uv + float2(0,  r), resolution) * 0.15
        + GroundWetness_Life(uv + float2(0, -r), resolution) * 0.15;

    // Blurred edges have lower life, so as everything fades the wet patch shrinks
    // from the outside in; noise makes that boundary irregular like soaked sand.
    float2 noiseUV = uv * _GroundWetnessTime.w;
    float noise = GroundWetness_ValueNoise(noiseUV) * 0.65 + GroundWetness_ValueNoise(noiseUV * 2.7) * 0.35;
    life += (noise - 0.5) * _GroundWetnessLook.w * saturate(life * 4.0);
    return smoothstep(0.02, 0.3, life);
}

void GroundWetness_float(float3 PositionWS, float3 BaseColor, float Smoothness, float3 NormalTS,
    out float3 OutBaseColor, out float OutSmoothness, out float3 OutNormalTS, out float Wetness)
{
    Wetness = GroundWetness_Sample(PositionWS);

    // Wet porous surfaces get darker and slightly more saturated.
    float3 darkened = BaseColor * lerp(1.0, _GroundWetnessLook.x, Wetness);
    float luminance = dot(darkened, float3(0.2126, 0.7152, 0.0722));
    OutBaseColor = max(lerp(luminance.xxx, darkened, 1.0 + 0.25 * Wetness), 0.0);

    // A water film is glossy and fills in small surface detail.
    OutSmoothness = lerp(Smoothness, _GroundWetnessLook.y, Wetness * Wetness);
    OutNormalTS = normalize(lerp(NormalTS, float3(0, 0, 1), Wetness * _GroundWetnessLook.z));
}

void GroundWetness_half(half3 PositionWS, half3 BaseColor, half Smoothness, half3 NormalTS,
    out half3 OutBaseColor, out half OutSmoothness, out half3 OutNormalTS, out half Wetness)
{
    float3 baseColor, normalTS;
    float smoothness, wetness;
    GroundWetness_float(PositionWS, BaseColor, Smoothness, NormalTS, baseColor, smoothness, normalTS, wetness);
    OutBaseColor = baseColor;
    OutSmoothness = smoothness;
    OutNormalTS = normalTS;
    Wetness = wetness;
}

#endif
