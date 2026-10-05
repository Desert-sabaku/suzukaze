Shader "Suzukaze/RamuneGlass"
{
    Properties
    {
        [Header(Bottle Geometry)]
        _BottleAxis ("Axis (object space)", Vector) = (0, 0, 1, 0)
        _ProfileScale ("Profile Scale", Float) = 1
        _GlassThickness ("Wall Thickness (object units)", Range(0.005, 0.15)) = 0.05
        _BottomThickness ("Bottom Thickness (object units)", Range(0.005, 0.5)) = 0.16

        [Header(Glass)]
        _GlassIOR ("Index of Refraction", Range(1, 2)) = 1.5
        _GlassAbsorption ("Absorption (per channel)", Color) = (0.8, 0.15, 0.2, 1)
        _GlassDensity ("Absorption Density", Range(0, 30)) = 10
        _GlassScatterColor ("Scatter Color", Color) = (0.55, 0.9, 0.85, 1)
        _GlassScatter ("Scatter Strength", Range(0, 1)) = 0.25
        _Smoothness ("Smoothness", Range(0, 1)) = 0.97
        _ReflectionStrength ("Reflection Strength", Range(0, 2)) = 1
        _SpecularStrength ("Specular Strength", Range(0, 4)) = 1
        _InternalReflection ("Internal Reflection Strength", Range(0, 2)) = 0.6

        [Header(Liquid)]
        _FillLevel ("Fill Level (object units along axis)", Range(-1.9, 1.75)) = -0.05
        _LiquidIOR ("Index of Refraction", Range(1, 1.6)) = 1.34
        _LiquidAbsorption ("Absorption (per channel)", Color) = (0.12, 0.04, 0.03, 1)
        _LiquidDensity ("Absorption Density", Range(0, 10)) = 1
        _WaveStrength ("Wave Strength", Range(0, 1)) = 0.15
        _WaveScale ("Wave Scale (1 / object units)", Range(0.1, 40)) = 8
        _WaveSpeed ("Wave Speed", Range(0, 10)) = 2
        _LiquidTilt ("Tilt (xz: world surface slope, w: motion) - set by RamuneLiquid", Vector) = (0, 0, 0, 0)

        [Header(Bubbles)]
        [Toggle(_BUBBLES_ON)] _Bubbles ("Enable", Float) = 1
        _BubbleColor ("Color", Color) = (0.9, 0.97, 1, 1)
        _BubbleIntensity ("Intensity", Range(0, 4)) = 1.5
        _BubbleCellSize ("Spacing (object units)", Range(0.03, 0.5)) = 0.1
        _BubbleRadius ("Radius (object units)", Range(0.003, 0.08)) = 0.012
        _BubbleDensity ("Density", Range(0, 1)) = 0.15
        _BubbleSpeed ("Rise Speed (object units / s)", Range(0, 3)) = 0.5

        [Header(Marble)]
        [Toggle(_MARBLE_ON)] _Marble ("Enable", Float) = 1
        _MarbleCenter ("Center (object units along axis)", Range(-1.9, 1.75)) = 0.56
        _MarbleRadius ("Radius (object units)", Range(0.05, 0.4)) = 0.19
        _MarbleAbsorption ("Absorption (per channel)", Color) = (0.5, 0.12, 0.15, 1)
        _MarbleDensity ("Absorption Density", Range(0, 30)) = 1.5

        [Header(Background)]
        _MaxTravel ("Max Background Distance (world units)", Range(0.01, 10)) = 0.5
    }

    SubShader
    {
        Tags
        {
            "RenderPipeline" = "UniversalPipeline"
            "RenderType" = "Transparent"
            "Queue" = "Transparent"
            "IgnoreProjector" = "True"
        }

        Pass
        {
            Name "ForwardLit"
            Tags
            {
                "LightMode" = "UniversalForward"
            }

            // The shader composites the background itself, so the output is opaque.
            Blend SrcAlpha OneMinusSrcAlpha
            ZWrite Off
            Cull Back

            HLSLPROGRAM
            #pragma target 3.5
            #pragma vertex Vert
            #pragma fragment Frag

            #pragma shader_feature_local _BUBBLES_ON
            #pragma shader_feature_local _MARBLE_ON

            #pragma multi_compile _ _MAIN_LIGHT_SHADOWS _MAIN_LIGHT_SHADOWS_CASCADE _MAIN_LIGHT_SHADOWS_SCREEN
            #pragma multi_compile _ _ADDITIONAL_LIGHTS_VERTEX _ADDITIONAL_LIGHTS
            #pragma multi_compile_fragment _ _SHADOWS_SOFT _SHADOWS_SOFT_LOW _SHADOWS_SOFT_MEDIUM _SHADOWS_SOFT_HIGH
            #pragma multi_compile_fragment _ _REFLECTION_PROBE_BLENDING
            #pragma multi_compile_fragment _ _REFLECTION_PROBE_BOX_PROJECTION
            #pragma multi_compile_fragment _ _REFLECTION_PROBE_ATLAS
            #pragma multi_compile _ _CLUSTER_LIGHT_LOOP
            #pragma multi_compile_fog
            #pragma multi_compile_instancing

            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Core.hlsl"
            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Lighting.hlsl"
            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/DeclareOpaqueTexture.hlsl"
            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/DeclareDepthTexture.hlsl"

            CBUFFER_START(UnityPerMaterial)
                float4 _BottleAxis;
                float _ProfileScale;
                float _GlassThickness;
                float _BottomThickness;
                half _GlassIOR;
                half4 _GlassAbsorption;
                half _GlassDensity;
                half4 _GlassScatterColor;
                half _GlassScatter;
                half _Smoothness;
                half _ReflectionStrength;
                half _SpecularStrength;
                half _InternalReflection;
                float _FillLevel;
                half _LiquidIOR;
                half4 _LiquidAbsorption;
                half _LiquidDensity;
                half _WaveStrength;
                float _WaveScale;
                float _WaveSpeed;
                float4 _LiquidTilt;
                half4 _BubbleColor;
                half _BubbleIntensity;
                float _BubbleCellSize;
                float _BubbleRadius;
                half _BubbleDensity;
                float _BubbleSpeed;
                float _MarbleCenter;
                float _MarbleRadius;
                half4 _MarbleAbsorption;
                half _MarbleDensity;
                float _MaxTravel;
            CBUFFER_END

            struct Attributes
            {
                float4 positionOS : POSITION;
                float3 normalOS : NORMAL;
                UNITY_VERTEX_INPUT_INSTANCE_ID
            };

            struct Varyings
            {
                float4 positionCS : SV_POSITION;
                float3 positionWS : TEXCOORD0;
                float3 normalWS : TEXCOORD1;
                float3 positionOS : TEXCOORD2;
                float3 normalOS : TEXCOORD3;
                float fogCoord : TEXCOORD4;
                UNITY_VERTEX_INPUT_INSTANCE_ID
                UNITY_VERTEX_OUTPUT_STEREO
            };

            Varyings Vert(Attributes input)
            {
                Varyings output = (Varyings)0;
                UNITY_SETUP_INSTANCE_ID(input);
                UNITY_TRANSFER_INSTANCE_ID(input, output);
                UNITY_INITIALIZE_VERTEX_OUTPUT_STEREO(output);

                VertexPositionInputs positionInputs = GetVertexPositionInputs(input.positionOS.xyz);
                output.positionCS = positionInputs.positionCS;
                output.positionWS = positionInputs.positionWS;
                output.normalWS = TransformObjectToWorldNormal(input.normalOS);
                output.positionOS = input.positionOS.xyz;
                output.normalOS = input.normalOS;
                output.fogCoord = ComputeFogFactor(positionInputs.positionCS.z);
                return output;
            }

            float ObjectScale()
            {
                float4x4 m = GetObjectToWorldMatrix();
                return (length(m._m00_m10_m20) + length(m._m01_m11_m21) + length(m._m02_m12_m22)) / 3.0;
            }

            // ---------------------------------------------------------------- Bottle shape

            // Outer silhouette of Ramune.blend's Bottle as (radius, height) in object units,
            // measured from the mesh, bottom center to top center. The inside is this
            // profile shrunk by the wall thickness.
            #define PROFILE_COUNT 28
            static const float2 kProfile[PROFILE_COUNT] =
            {
                float2(0.000, -1.889), float2(0.320, -1.889), float2(0.465, -1.850), float2(0.501, -1.800),
                float2(0.514, -1.750), float2(0.518, -1.350), float2(0.521, -0.450), float2(0.516, -0.300),
                float2(0.479, -0.200), float2(0.427, -0.100), float2(0.402, 0.000), float2(0.397, 0.100),
                float2(0.405, 0.300), float2(0.416, 0.450), float2(0.434, 0.550), float2(0.438, 0.620),
                float2(0.431, 0.700), float2(0.414, 0.800), float2(0.375, 0.900), float2(0.342, 1.000),
                float2(0.312, 1.100), float2(0.290, 1.200), float2(0.252, 1.300), float2(0.229, 1.400),
                float2(0.225, 1.550), float2(0.216, 1.700), float2(0.190, 1.744), float2(0.000, 1.744)
            };

            float3 BottleAxis()
            {
                return normalize(_BottleAxis.xyz);
            }

            float2 ProfilePoint(int i)
            {
                return kProfile[i] * _ProfileScale;
            }

            // Profile radius at height h along the axis (object units), clamped to the bottle's height.
            float ProfileRadius(float h)
            {
                h = clamp(h, ProfilePoint(0).y, ProfilePoint(PROFILE_COUNT - 1).y - 1e-4);
                [loop] for (int i = 0; i < PROFILE_COUNT - 1; i++)
                {
                    float2 a = ProfilePoint(i);
                    float2 b = ProfilePoint(i + 1);
                    if (h >= a.y && h < b.y)
                        return lerp(a.x, b.x, (h - a.y) / (b.y - a.y));
                }
                return 0.0;
            }

            struct BottleHit
            {
                float t;
                float3 normal; // pointing out of the solid
            };

            // Nearest hit beyond tMin of a ray with the solid of revolution of the profile,
            // shrunk radially by inset and capped by planes moved in by bottomInset / inset.
            // inset = 0 gives the outer glass surface; the wall thickness gives the cavity.
            // Each profile segment is a cone, intersected analytically.
            BottleHit IntersectBottle(float3 origin, float3 direction, float inset, float bottomInset, float tMin)
            {
                float3 axis = BottleAxis();
                float oz = dot(origin, axis);
                float dz = dot(direction, axis);
                float3 oRadial = origin - axis * oz;
                float3 dRadial = direction - axis * dz;
                float qa = dot(dRadial, dRadial);
                float qb = dot(oRadial, dRadial);
                float qc = dot(oRadial, oRadial);
                float bottom = ProfilePoint(0).y + bottomInset;
                float top = ProfilePoint(PROFILE_COUNT - 1).y - inset;

                BottleHit hit;
                hit.t = 1e9;
                hit.normal = axis;

                [loop] for (int i = 0; i < PROFILE_COUNT - 1; i++)
                {
                    float2 a = ProfilePoint(i);
                    float2 b = ProfilePoint(i + 1);
                    float z0 = max(a.y, bottom);
                    float z1 = min(b.y, top);
                    if (b.y - a.y < 1e-5 || z1 <= z0)
                        continue;

                    // Cone radius along the ray: ra + rb * t.
                    float slope = (b.x - a.x) / (b.y - a.y);
                    float ra = a.x - inset + (oz - a.y) * slope;
                    float rb = dz * slope;
                    float qA = qa - rb * rb;
                    float qB = qb - ra * rb;
                    float qC = qc - ra * ra;
                    float disc = qB * qB - qA * qC;
                    if (disc < 0.0)
                        continue;

                    float2 roots;
                    if (abs(qA) < 1e-6)
                    {
                        roots = -qC / (2.0 * qB);
                    }
                    else
                    {
                        float sq = sqrt(disc);
                        roots = float2(-qB - sq, -qB + sq) / qA;
                    }

                    [unroll] for (int r = 0; r < 2; r++)
                    {
                        float t = roots[r];
                        float z = oz + dz * t;
                        if (t > tMin && t < hit.t && z >= z0 && z <= z1 && ra + rb * t >= 0.0)
                        {
                            hit.t = t;
                            hit.normal = normalize(normalize(oRadial + dRadial * t) - axis * slope);
                        }
                    }
                }

                // End caps.
                if (abs(dz) > 1e-6)
                {
                    [unroll] for (int c = 0; c < 2; c++)
                    {
                        float z = c == 0 ? bottom : top;
                        float t = (z - oz) / dz;
                        if (t > tMin && t < hit.t)
                        {
                            float radius = ProfileRadius(z) - inset;
                            if (radius > 0.0 && qc + t * (2.0 * qb + t * qa) <= radius * radius)
                            {
                                hit.t = t;
                                hit.normal = c == 0 ? -axis : axis;
                            }
                        }
                    }
                }
                return hit;
            }

            bool IsInCavity(float3 p)
            {
                float3 axis = BottleAxis();
                float h = dot(p, axis);
                return h > ProfilePoint(0).y + _BottomThickness
                    && h < ProfilePoint(PROFILE_COUNT - 1).y - _GlassThickness
                    && length(p - axis * h) < ProfileRadius(h) - _GlassThickness;
            }

            // ---------------------------------------------------------------- Liquid surface

            struct LiquidPlane
            {
                float3 normal; // object space, pointing up out of the liquid
                float3 origin;
                float3 tangent;
                float3 bitangent;
            };

            LiquidPlane GetLiquidPlane()
            {
                LiquidPlane plane;
                float3 upWS = normalize(float3(-_LiquidTilt.x, 1.0, -_LiquidTilt.z));
                plane.normal = normalize(TransformWorldToObjectDir(upWS));
                plane.origin = BottleAxis() * _FillLevel;
                float3 helper = abs(plane.normal.x) < 0.9 ? float3(1, 0, 0) : float3(0, 1, 0);
                plane.tangent = normalize(cross(plane.normal, helper));
                plane.bitangent = cross(plane.normal, plane.tangent);
                return plane;
            }

            bool IsInLiquid(float3 p, LiquidPlane plane)
            {
                return dot(p - plane.origin, plane.normal) < 0.0;
            }

            float3 WavyLiquidNormal(float3 p, LiquidPlane plane)
            {
                float2 uv = float2(dot(p, plane.tangent), dot(p, plane.bitangent)) * _WaveScale;
                float t = _Time.y * _WaveSpeed;
                float2 grad = float2(
                    cos(uv.x + t) * cos(uv.y * 0.8 - t * 1.3),
                    -0.8 * sin(uv.x + t) * sin(uv.y * 0.8 - t * 1.3));
                grad += 0.5 * float2(cos(uv.x * 1.7 - uv.y * 1.3 + t * 1.6), -cos(uv.x * 1.7 - uv.y * 1.3 + t * 1.6)) * float2(1.7, 1.3);
                float amplitude = _WaveStrength * (0.15 + saturate(_LiquidTilt.w));
                return normalize(plane.normal - (grad.x * plane.tangent + grad.y * plane.bitangent) * amplitude * 0.1);
            }

            // ---------------------------------------------------------------- Noise

            float3 Hash33(float3 p)
            {
                p = float3(dot(p, float3(127.1, 311.7, 74.7)),
                           dot(p, float3(269.5, 183.3, 246.1)),
                           dot(p, float3(113.5, 271.9, 124.6)));
                return frac(sin(p) * 43758.5453);
            }

            float Hash12(float2 p)
            {
                return frac(sin(dot(p, float2(127.1, 311.7))) * 43758.5453);
            }

            // ---------------------------------------------------------------- Lighting

            half3 FresnelSchlick(half3 f0, half cosTheta)
            {
                return f0 + (1.0 - f0) * pow(1.0 - saturate(cosTheta), 5.0);
            }

            half3 SpecularGGX(Light light, half3 normalWS, half3 viewDirWS, half roughness, half3 f0)
            {
                half3 halfDir = SafeNormalize(light.direction + viewDirWS);
                half nDotL = saturate(dot(normalWS, light.direction));
                half nDotH = saturate(dot(normalWS, halfDir));
                half lDotH = saturate(dot(light.direction, halfDir));

                half a2 = roughness * roughness;
                float d = nDotH * nDotH * (a2 - 1.0) + 1.00001;
                // Same visibility approximation as URP's DirectBRDFSpecular.
                half term = a2 / (d * d * max(0.1h, lDotH * lDotH) * (roughness * 4.0 + 2.0));
                term = min(term, 1000.0);

                half3 radiance = light.color * (light.distanceAttenuation * light.shadowAttenuation * nDotL);
                return FresnelSchlick(f0, lDotH) * term * radiance;
            }

            half3 DirectSpecular(float3 positionWS, float2 screenUV, half3 normalWS, half3 viewDirWS, half roughness,
                                 half3 f0)
            {
                float4 shadowCoord = TransformWorldToShadowCoord(positionWS);
                half3 spec = SpecularGGX(GetMainLight(shadowCoord), normalWS, viewDirWS, roughness, f0);

                #if defined(_ADDITIONAL_LIGHTS)
                uint pixelLightCount = GetAdditionalLightsCount();

                #if USE_CLUSTER_LIGHT_LOOP
                [loop] for (uint lightIndex = 0; lightIndex < min(URP_FP_DIRECTIONAL_LIGHTS_COUNT, MAX_VISIBLE_LIGHTS);
                                                           lightIndex++)
                {
                    CLUSTER_LIGHT_LOOP_SUBTRACTIVE_LIGHT_CHECK
                    Light light = GetAdditionalLight(lightIndex, positionWS, half4(1, 1, 1, 1));
                    spec += SpecularGGX(light, normalWS, viewDirWS, roughness, f0);
                }
                #endif

                // LIGHT_LOOP_BEGIN reads inputData under the cluster light loop.
                InputData inputData = (InputData)0;
                inputData.positionWS = positionWS;
                inputData.normalizedScreenSpaceUV = screenUV;
                LIGHT_LOOP_BEGIN(pixelLightCount)
                    Light light = GetAdditionalLight(lightIndex, positionWS, half4(1, 1, 1, 1));
                    spec += SpecularGGX(light, normalWS, viewDirWS, roughness, f0);
                LIGHT_LOOP_END
                #endif

                return spec;
            }

            // Internal reflections use the sky cubemap only; probe blending per interface is
            // too expensive and barely visible inside the bottle.
            half3 Environment(float3 directionOS)
            {
                return GlossyEnvironmentReflection(TransformObjectToWorldDir(directionOS),
                                                   PerceptualSmoothnessToPerceptualRoughness(_Smoothness), 1.0);
            }

            // ---------------------------------------------------------------- Ray tracing through the bottle

            #define MEDIUM_GLASS 0
            #define MEDIUM_AIR 1
            #define MEDIUM_LIQUID 2
            #define MAX_EVENTS 8
            #define MAX_BUBBLE_COLUMNS 20
            #define MAX_BUBBLE_CELLS_PER_COLUMN 6
            #define SURFACE_EPSILON 0.0015

            struct Ray
            {
                float3 position; // object space
                float3 direction;
                int medium;
                half3 throughput;
                half3 radiance;
                half3 ambient;
            };

            half MediumIOR(int medium)
            {
                return medium == MEDIUM_GLASS ? _GlassIOR : medium == MEDIUM_LIQUID ? _LiquidIOR : 1.0h;
            }

            // Crosses an interface whose normal faces the incoming side. Reflection is added
            // as environment light; the ray continues along the refracted direction, or the
            // reflected one under total internal reflection. Returns whether it got through.
            bool CrossInterface(inout Ray ray, float3 normal, int nextMedium)
            {
                half n1 = MediumIOR(ray.medium);
                half n2 = MediumIOR(nextMedium);
                half eta = n1 / n2;
                half cosI = saturate(-dot(ray.direction, normal));
                half sin2T = eta * eta * (1.0 - cosI * cosI);
                float3 reflected = reflect(ray.direction, normal);
                if (sin2T >= 1.0)
                {
                    ray.direction = reflected;
                    return false;
                }

                half cosT = sqrt(1.0 - sin2T);
                half f0 = (n1 - n2) / (n1 + n2);
                half fresnel = FresnelSchlick(f0 * f0, n1 > n2 ? cosT : cosI).x;
                ray.radiance += ray.throughput * fresnel * _InternalReflection * Environment(reflected);
                ray.throughput *= 1.0 - fresnel;
                ray.direction = refract(ray.direction, normal, eta);
                ray.medium = nextMedium;
                return true;
            }

            void Absorb(inout Ray ray, float pathLength)
            {
                if (ray.medium == MEDIUM_GLASS)
                {
                    half3 transmittance = exp(-_GlassAbsorption.rgb * _GlassDensity * pathLength);
                    ray.radiance += ray.throughput * _GlassScatterColor.rgb * ray.ambient * _GlassScatter * (1.0 - transmittance);
                    ray.throughput *= transmittance;
                }
                else if (ray.medium == MEDIUM_LIQUID)
                {
                    ray.throughput *= exp(-_LiquidAbsorption.rgb * _LiquidDensity * pathLength);
                }
            }

            // Distance along the ray to a sphere's front face, or -1.
            float RaySphere(float3 origin, float3 direction, float3 center, float radius)
            {
                float3 oc = origin - center;
                float b = dot(oc, direction);
                float c = dot(oc, oc) - radius * radius;
                float h = b * b - c;
                if (c < 0.0 || h < 0.0)
                    return -1.0;
                float t = -b - sqrt(h);
                return t > 0.0 ? t : -1.0;
            }

            #if defined(_MARBLE_ON)
            // Refracts through the marble and leaves the ray just outside its far side.
            void TraceMarble(inout Ray ray, float3 center, LiquidPlane plane)
            {
                float3 outward = normalize(ray.position - center);
                if (!CrossInterface(ray, outward, MEDIUM_GLASS))
                {
                    ray.position += outward * SURFACE_EPSILON;
                    return;
                }

                float chord = max(-2.0 * dot(ray.position - center, ray.direction), 0.0);
                ray.throughput *= exp(-_MarbleAbsorption.rgb * _MarbleDensity * chord);
                ray.position += ray.direction * chord;
                outward = normalize(ray.position - center);
                int outside = IsInLiquid(ray.position, plane) ? MEDIUM_LIQUID : MEDIUM_AIR;
                CrossInterface(ray, -outward, outside);
                ray.medium = outside;
                ray.position += outward * SURFACE_EPSILON;
            }
            #endif

            #if defined(_BUBBLES_ON)
            // Shades the rising bubbles along a segment of liquid. Bubbles live in vertical
            // columns that rise at their own speed, one candidate per cell; the columns the
            // segment crosses are walked with a 2D DDA and only the cells it spans are tested.
            void ShadeBubbles(inout Ray ray, float segment, LiquidPlane plane)
            {
                float3 origin = float3(dot(ray.position, plane.tangent), dot(ray.position, plane.bitangent),
                                       dot(ray.position, plane.normal));
                float3 dir = float3(dot(ray.direction, plane.tangent), dot(ray.direction, plane.bitangent),
                                    dot(ray.direction, plane.normal));
                half3 light = (ray.ambient + _MainLightColor.rgb * 0.25) * _BubbleColor.rgb * _BubbleIntensity;

                float size = _BubbleCellSize;
                float2 column = floor(origin.xy / size);
                float2 stepDir = dir.xy >= 0.0 ? 1.0 : -1.0;
                float2 invDir = 1.0 / max(abs(dir.xy), 1e-5);
                float2 tDelta = size * invDir;
                float2 tNext = (dir.xy >= 0.0 ? (column + 1.0) * size - origin.xy : origin.xy - column * size) * invDir;
                float tEnter = 0.0;

                [loop] for (int c = 0; c < MAX_BUBBLE_COLUMNS && tEnter < segment; c++)
                {
                    float tExit = min(min(tNext.x, tNext.y), segment);
                    float scroll = _Time.y * _BubbleSpeed * lerp(0.6, 1.4, Hash12(column));
                    float zA = origin.z + dir.z * tEnter - scroll;
                    float zB = origin.z + dir.z * tExit - scroll;
                    float cellLow = floor(min(zA, zB) / size);
                    float cellHigh = min(floor(max(zA, zB) / size), cellLow + MAX_BUBBLE_CELLS_PER_COLUMN - 1);

                    [loop] for (float cz = cellLow; cz <= cellHigh; cz++)
                    {
                        float3 cell = float3(column, cz);
                        float3 h = Hash33(cell);
                        if (h.x > _BubbleDensity)
                            continue;

                        float radius = _BubbleRadius * lerp(0.5, 1.0, h.y);
                        float margin = radius / size + 0.08;
                        float3 center = (cell + lerp(margin, 1.0 - margin, Hash33(cell + 17.0))) * size;
                        center.xy += sin(_Time.y * (2.0 + 3.0 * h.z) + h.yz * 6.2831) * size * 0.08;
                        center.z += scroll;

                        float3 toCenter = center - origin;
                        float along = dot(toCenter, dir);
                        float closest = length(toCenter - dir * along);
                        if (along < 0.0 || along > segment || closest >= radius)
                            continue;

                        half x = closest / radius;
                        half rim = pow(x, 6.0) * 0.9 + 0.08;
                        ray.radiance += ray.throughput * light * rim;
                        ray.throughput *= 1.0 - rim * 0.5;
                    }

                    tEnter = tExit;
                    if (tNext.x < tNext.y)
                    {
                        tNext.x += tDelta.x;
                        column.x += stepDir.x;
                    }
                    else
                    {
                        tNext.y += tDelta.y;
                        column.y += stepDir.y;
                    }
                }
            }
            #endif

            // Follows the refracted ray from inside the front glass surface from interface
            // to interface until it leaves the bottle.
            void TraceBottle(inout Ray ray)
            {
                LiquidPlane plane = GetLiquidPlane();
                #if defined(_MARBLE_ON)
                float3 marbleCenter = BottleAxis() * _MarbleCenter;
                #endif

                [loop] for (int i = 0; i < MAX_EVENTS; i++)
                {
                    if (ray.medium == MEDIUM_GLASS)
                    {
                        BottleHit outer = IntersectBottle(ray.position, ray.direction, 0.0, 0.0, SURFACE_EPSILON);
                        BottleHit cavity = IntersectBottle(ray.position, ray.direction, _GlassThickness,
                                                           _BottomThickness, SURFACE_EPSILON);
                        if (cavity.t < outer.t)
                        {
                            Absorb(ray, cavity.t);
                            ray.position += ray.direction * cavity.t;
                            // The cavity normal points out of the cavity, toward the glass.
                            int inside = IsInLiquid(ray.position, plane) ? MEDIUM_LIQUID : MEDIUM_AIR;
                            CrossInterface(ray, cavity.normal, inside);
                        }
                        else
                        {
                            if (outer.t > 1e8)
                                return;
                            Absorb(ray, outer.t);
                            ray.position += ray.direction * outer.t;
                            if (CrossInterface(ray, -outer.normal, MEDIUM_AIR))
                                return;
                        }
                        continue;
                    }

                    // Inside the cavity, filled with air or liquid.
                    BottleHit wall = IntersectBottle(ray.position, ray.direction, _GlassThickness, _BottomThickness,
                                                     SURFACE_EPSILON);
                    float segment = wall.t;
                    int hit = 0; // 0: wall, 1: liquid surface, 2: marble

                    float height = dot(ray.position - plane.origin, plane.normal);
                    float rate = dot(ray.direction, plane.normal);
                    if (height * rate < 0.0 && -height / rate < segment)
                    {
                        segment = -height / rate;
                        hit = 1;
                    }

                    #if defined(_MARBLE_ON)
                    float tMarble = RaySphere(ray.position, ray.direction, marbleCenter, _MarbleRadius);
                    if (tMarble > 0.0 && tMarble < segment)
                    {
                        segment = tMarble;
                        hit = 2;
                    }
                    #endif

                    if (segment > 1e8)
                        return;

                    #if defined(_BUBBLES_ON)
                    if (ray.medium == MEDIUM_LIQUID)
                        ShadeBubbles(ray, segment, plane);
                    #endif

                    Absorb(ray, segment);
                    ray.position += ray.direction * segment;

                    if (hit == 0)
                    {
                        CrossInterface(ray, -wall.normal, MEDIUM_GLASS);
                    }
                    else if (hit == 1)
                    {
                        float3 normal = WavyLiquidNormal(ray.position, plane);
                        normal = height > 0.0 ? normal : -normal;
                        int other = ray.medium == MEDIUM_LIQUID ? MEDIUM_AIR : MEDIUM_LIQUID;
                        CrossInterface(ray, normal, other);
                        // Step off the plane to whichever side the ray now travels.
                        ray.position += ray.direction * SURFACE_EPSILON;
                        ray.medium = IsInLiquid(ray.position, plane) ? MEDIUM_LIQUID : MEDIUM_AIR;
                    }
                    #if defined(_MARBLE_ON)
                    else
                    {
                        TraceMarble(ray, marbleCenter, plane);
                    }
                    #endif
                }
            }

            // ---------------------------------------------------------------- Fragment

            float2 ScreenUV(float3 positionWS)
            {
                float4 screenPos = ComputeScreenPos(TransformWorldToHClip(positionWS));
                return screenPos.xy / screenPos.w;
            }

            half4 Frag(Varyings input) : SV_Target
            {
                UNITY_SETUP_INSTANCE_ID(input);
                UNITY_SETUP_STEREO_EYE_INDEX_POST_VERTEX(input);

                float3 positionWS = input.positionWS;
                float3 viewDirWS = SafeNormalize(GetWorldSpaceViewDir(positionWS));
                float3 normalWS = normalize(input.normalWS);
                float3 normalOS = normalize(input.normalOS);
                float3 viewDirOS = normalize(TransformWorldToObjectDir(viewDirWS));
                float objectScale = ObjectScale();

                float2 baseUV = GetNormalizedScreenSpaceUV(input.positionCS);
                float surfaceEyeDepth = LinearEyeDepth(positionWS, GetWorldToViewMatrix());
                float sceneEyeDepth = LinearEyeDepth(SampleSceneDepth(baseUV), _ZBufferParams);

                half nDotV = saturate(dot(normalWS, viewDirWS));
                half f0Scalar = (_GlassIOR - 1.0) / (_GlassIOR + 1.0);
                half3 f0 = f0Scalar * f0Scalar;
                half3 fresnel = FresnelSchlick(f0, nDotV);

                // Enter the glass at the mesh surface.
                Ray ray;
                ray.direction = refract(-viewDirOS, normalOS, 1.0 / _GlassIOR);
                ray.medium = MEDIUM_GLASS;
                ray.throughput = 1.0;
                ray.radiance = 0.0;
                ray.ambient = SampleSH(normalWS);

                // Start just inside the profile's outer surface, which the mesh only
                // approximately matches.
                float3 axis = BottleAxis();
                float h = clamp(dot(input.positionOS, axis), ProfilePoint(0).y + SURFACE_EPSILON,
                                ProfilePoint(PROFILE_COUNT - 1).y - SURFACE_EPSILON);
                float3 radial = input.positionOS - axis * dot(input.positionOS, axis);
                float radius = length(radial);
                float maxRadius = ProfileRadius(h) - SURFACE_EPSILON;
                ray.position = axis * h + (radius > maxRadius ? radial * (maxRadius / radius) : radial);

                // Where the mesh dents into the cavity (the marble stops), assume a wall of the
                // nominal thickness parallel to the surface and enter the cavity right away.
                if (IsInCavity(ray.position))
                {
                    Absorb(ray, _GlassThickness / max(dot(-normalOS, ray.direction), 0.3));
                    int inside = IsInLiquid(ray.position, GetLiquidPlane()) ? MEDIUM_LIQUID : MEDIUM_AIR;
                    CrossInterface(ray, normalOS, inside);
                }

                TraceBottle(ray);

                // Background along the outgoing ray.
                float3 exitWS = TransformObjectToWorld(ray.position);
                float3 exitDirWS = normalize(TransformObjectToWorldDir(ray.direction));
                float travel = clamp(sceneEyeDepth - surfaceEyeDepth, 0.01 * objectScale, _MaxTravel);
                float2 backgroundUV = saturate(ScreenUV(exitWS + exitDirWS * travel));
                // Reject samples of objects in front of the bottle.
                if (LinearEyeDepth(SampleSceneDepth(backgroundUV), _ZBufferParams) < surfaceEyeDepth)
                    backgroundUV = baseUV;
                half3 transmitted = ray.radiance + ray.throughput * SampleSceneColor(backgroundUV);

                // Outer surface reflection and highlights.
                half3 reflection = GlossyEnvironmentReflection(reflect(-viewDirWS, normalWS), positionWS,
                                                               PerceptualSmoothnessToPerceptualRoughness(_Smoothness),
                                                               1.0, baseUV) * _ReflectionStrength;
                half roughness = max(PerceptualSmoothnessToRoughness(_Smoothness), HALF_MIN_SQRT);
                half3 specular = DirectSpecular(positionWS, baseUV, normalWS, viewDirWS, roughness, f0) * _SpecularStrength;

                half3 color = lerp(transmitted, reflection, fresnel) + specular;
                color = MixFog(color, InitializeInputDataFog(float4(positionWS, 1.0), input.fogCoord));
                return half4(color, 1.0);
            }
            ENDHLSL
        }
    }

    FallBack Off
}
