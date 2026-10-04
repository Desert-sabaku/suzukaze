// Water for the uchimizu (打ち水) splash.
// The Alembic fluid mesh has no usable UVs and changes topology every frame, so all
// surface detail is generated procedurally in world space. The body of the water is
// rendered by refracting the already-drawn scene (_CameraOpaqueTexture), tinted by
// Beer-Lambert absorption, and combined with Fresnel-weighted reflections and specular.
// Lengths are given in object units and follow the Transform's scale, so the look
// survives resizing the splash. Absorption is per object unit of path length.
// Requires "Opaque Texture" and "Depth Texture" on the URP asset.
Shader "Suzukaze/UchimizuWater"
{
    Properties
    {
        [Header(Body)]
        _AbsorptionColor ("Absorption (per channel)", Color) = (0.45, 0.10, 0.06, 1)
        _AbsorptionDensity ("Absorption Density", Range(0, 500)) = 40
        _Thickness ("Thickness (object units)", Range(0, 0.1)) = 0.004
        _ScatterColor ("Scatter Color", Color) = (0.55, 0.75, 0.80, 1)
        _ScatterStrength ("Scatter Strength", Range(0, 1)) = 0.04

        [Header(Refraction)]
        _IOR ("Index of Refraction", Range(1, 1.6)) = 1.333
        _RefractionDistance ("Refraction Distance (object units)", Range(0, 0.2)) = 0.012
        _MaxScreenOffset ("Max Screen Offset", Range(0, 0.2)) = 0.06
        _Dispersion ("Dispersion", Range(0, 0.05)) = 0.012
        _BlurRadius ("Blur Radius (px)", Range(0, 6)) = 1

        [Header(Surface)]
        _Smoothness ("Smoothness", Range(0, 1)) = 0.96
        _ReflectionStrength ("Reflection Strength", Range(0, 2)) = 1
        _SpecularStrength ("Specular Strength", Range(0, 4)) = 1

        [Header(Ripples)]
        _RippleScale ("Scale (1 / object units)", Range(1, 2000)) = 400
        _RippleStrength ("Strength", Range(0, 1)) = 0.2
        _RippleSpeed ("Speed", Range(0, 10)) = 1.5

        [Header(Edges)]
        _EdgeFade ("Intersection Fade (object units)", Range(0.00001, 0.05)) = 0.0008
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
            Tags { "LightMode" = "UniversalForward" }

            Blend SrcAlpha OneMinusSrcAlpha
            ZWrite Off
            Cull Back

            HLSLPROGRAM
            #pragma target 3.5
            #pragma vertex Vert
            #pragma fragment Frag

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
                half4 _AbsorptionColor;
                half _AbsorptionDensity;
                float _Thickness;
                half4 _ScatterColor;
                half _ScatterStrength;
                half _IOR;
                float _RefractionDistance;
                float _MaxScreenOffset;
                half _Dispersion;
                half _BlurRadius;
                half _Smoothness;
                half _ReflectionStrength;
                half _SpecularStrength;
                float _RippleScale;
                half _RippleStrength;
                float _RippleSpeed;
                float _EdgeFade;
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
                float fogCoord : TEXCOORD2;
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
                output.fogCoord = ComputeFogFactor(positionInputs.positionCS.z);
                return output;
            }

            float ObjectScale()
            {
                float4x4 m = GetObjectToWorldMatrix();
                return (length(m._m00_m10_m20) + length(m._m01_m11_m21) + length(m._m02_m12_m22)) / 3.0;
            }

            // ---------------------------------------------------------------- Noise

            float3 Hash33(float3 p)
            {
                p = float3(dot(p, float3(127.1, 311.7, 74.7)),
                           dot(p, float3(269.5, 183.3, 246.1)),
                           dot(p, float3(113.5, 271.9, 124.6)));
                return frac(sin(p) * 43758.5453) * 2.0 - 1.0;
            }

            // 3D gradient noise in [-1, 1].
            float GradientNoise(float3 p)
            {
                float3 i = floor(p);
                float3 f = frac(p);
                float3 u = f * f * f * (f * (f * 6.0 - 15.0) + 10.0);

                float n000 = dot(Hash33(i + float3(0, 0, 0)), f - float3(0, 0, 0));
                float n100 = dot(Hash33(i + float3(1, 0, 0)), f - float3(1, 0, 0));
                float n010 = dot(Hash33(i + float3(0, 1, 0)), f - float3(0, 1, 0));
                float n110 = dot(Hash33(i + float3(1, 1, 0)), f - float3(1, 1, 0));
                float n001 = dot(Hash33(i + float3(0, 0, 1)), f - float3(0, 0, 1));
                float n101 = dot(Hash33(i + float3(1, 0, 1)), f - float3(1, 0, 1));
                float n011 = dot(Hash33(i + float3(0, 1, 1)), f - float3(0, 1, 1));
                float n111 = dot(Hash33(i + float3(1, 1, 1)), f - float3(1, 1, 1));

                float nx00 = lerp(n000, n100, u.x);
                float nx10 = lerp(n010, n110, u.x);
                float nx01 = lerp(n001, n101, u.x);
                float nx11 = lerp(n011, n111, u.x);
                return lerp(lerp(nx00, nx10, u.y), lerp(nx01, nx11, u.y), u.z);
            }

            float RippleHeight(float3 p)
            {
                float t = _Time.y * _RippleSpeed;
                float h = GradientNoise(p + float3(0.0, -t, 0.3 * t));
                h += 0.5 * GradientNoise(p * 2.13 + float3(0.7 * t, 0.4 * t, -t));
                return h;
            }

            // Perturbs the normal by the tangential gradient of a world-space height field.
            float3 ApplyRipples(float3 positionWS, float3 normalWS, float objectScale)
            {
                const float e = 0.05;
                float3 p = positionWS * (_RippleScale / objectScale);
                float h = RippleHeight(p);
                float3 grad = float3(
                    RippleHeight(p + float3(e, 0, 0)) - h,
                    RippleHeight(p + float3(0, e, 0)) - h,
                    RippleHeight(p + float3(0, 0, e)) - h) / e;
                grad -= dot(grad, normalWS) * normalWS;
                return normalize(normalWS - grad * _RippleStrength * 0.25);
            }

            // ---------------------------------------------------------------- Refraction

            float2 ScreenUV(float3 positionWS)
            {
                float4 screenPos = ComputeScreenPos(TransformWorldToHClip(positionWS));
                return screenPos.xy / screenPos.w;
            }

            // Screen UV of the background seen through the surface along a refracted ray.
            float2 RefractedUV(float2 baseUV, float2 surfaceUV, float3 positionWS, float3 viewDirWS,
                               float3 normalWS, float eta, float travel)
            {
                float3 refracted = refract(-viewDirWS, normalWS, eta);
                // Total internal reflection: fall back to the straight-through ray.
                if (dot(refracted, refracted) < 1e-4)
                    refracted = -viewDirWS;

                float2 offset = ScreenUV(positionWS + refracted * travel) - surfaceUV;
                float len = length(offset);
                if (len > _MaxScreenOffset)
                    offset *= _MaxScreenOffset / len;
                return saturate(baseUV + offset);
            }

            // Rejects samples whose background lies in front of the water surface,
            // which would otherwise leak foreground objects into the refraction.
            float2 ValidateRefractedUV(float2 refractedUV, float2 baseUV, float surfaceEyeDepth)
            {
                float sceneEyeDepth = LinearEyeDepth(SampleSceneDepth(refractedUV), _ZBufferParams);
                return sceneEyeDepth < surfaceEyeDepth ? baseUV : refractedUV;
            }

            float3 SampleBlurredScene(float2 uv, float2 radius)
            {
                float3 c = SampleSceneColor(uv) * 0.4;
                c += SampleSceneColor(uv + float2( radius.x, 0)) * 0.15;
                c += SampleSceneColor(uv + float2(-radius.x, 0)) * 0.15;
                c += SampleSceneColor(uv + float2(0,  radius.y)) * 0.15;
                c += SampleSceneColor(uv + float2(0, -radius.y)) * 0.15;
                return c;
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

            half3 DirectSpecular(InputData inputData, half roughness, half3 f0)
            {
                float4 shadowCoord = TransformWorldToShadowCoord(inputData.positionWS);
                half3 spec = SpecularGGX(GetMainLight(shadowCoord), inputData.normalWS, inputData.viewDirectionWS, roughness, f0);

                #if defined(_ADDITIONAL_LIGHTS)
                uint pixelLightCount = GetAdditionalLightsCount();

                #if USE_CLUSTER_LIGHT_LOOP
                [loop] for (uint lightIndex = 0; lightIndex < min(URP_FP_DIRECTIONAL_LIGHTS_COUNT, MAX_VISIBLE_LIGHTS); lightIndex++)
                {
                    CLUSTER_LIGHT_LOOP_SUBTRACTIVE_LIGHT_CHECK
                    Light light = GetAdditionalLight(lightIndex, inputData.positionWS, half4(1, 1, 1, 1));
                    spec += SpecularGGX(light, inputData.normalWS, inputData.viewDirectionWS, roughness, f0);
                }
                #endif

                LIGHT_LOOP_BEGIN(pixelLightCount)
                    Light light = GetAdditionalLight(lightIndex, inputData.positionWS, half4(1, 1, 1, 1));
                    spec += SpecularGGX(light, inputData.normalWS, inputData.viewDirectionWS, roughness, f0);
                LIGHT_LOOP_END
                #endif

                return spec;
            }

            // ---------------------------------------------------------------- Fragment

            half4 Frag(Varyings input, bool isFrontFace : SV_IsFrontFace) : SV_Target
            {
                UNITY_SETUP_INSTANCE_ID(input);
                UNITY_SETUP_STEREO_EYE_INDEX_POST_VERTEX(input);

                float3 positionWS = input.positionWS;
                float3 viewDirWS = SafeNormalize(GetWorldSpaceViewDir(positionWS));
                float3 normalWS = normalize(input.normalWS);
                normalWS = isFrontFace ? normalWS : -normalWS;
                float objectScale = ObjectScale();
                normalWS = ApplyRipples(positionWS, normalWS, objectScale);

                float2 baseUV = GetNormalizedScreenSpaceUV(input.positionCS);
                float2 surfaceUV = ScreenUV(positionWS);
                float surfaceEyeDepth = LinearEyeDepth(positionWS, GetWorldToViewMatrix());
                float sceneEyeDepth = LinearEyeDepth(SampleSceneDepth(baseUV), _ZBufferParams);
                float depthBehind = max(sceneEyeDepth - surfaceEyeDepth, 0.0);

                half nDotV = saturate(dot(normalWS, viewDirWS));

                // Approximate path length through the water: thicker at grazing angles,
                // never longer than the gap to the geometry behind it.
                float thickness = min(_Thickness * objectScale / max(nDotV, 0.2), depthBehind) / objectScale;
                float refractionDistance = _RefractionDistance * objectScale;
                float travel = refractionDistance * saturate(depthBehind / max(refractionDistance, 1e-6));

                // Refraction with per-channel IOR for dispersion.
                float eta = 1.0 / _IOR;
                float etaSpread = _Dispersion * eta;
                float2 uvR = RefractedUV(baseUV, surfaceUV, positionWS, viewDirWS, normalWS, eta + etaSpread, travel);
                float2 uvG = RefractedUV(baseUV, surfaceUV, positionWS, viewDirWS, normalWS, eta, travel);
                float2 uvB = RefractedUV(baseUV, surfaceUV, positionWS, viewDirWS, normalWS, eta - etaSpread, travel);
                uvR = ValidateRefractedUV(uvR, baseUV, surfaceEyeDepth);
                uvG = ValidateRefractedUV(uvG, baseUV, surfaceEyeDepth);
                uvB = ValidateRefractedUV(uvB, baseUV, surfaceEyeDepth);

                half roughness = max(PerceptualSmoothnessToRoughness(_Smoothness), HALF_MIN_SQRT);
                float2 blur = (_BlurRadius + roughness * 8.0) * (_ScreenParams.zw - 1.0);
                half3 background = half3(
                    SampleBlurredScene(uvR, blur).r,
                    SampleBlurredScene(uvG, blur).g,
                    SampleBlurredScene(uvB, blur).b);

                // Beer-Lambert absorption plus a little in-scattered ambient light.
                half3 transmittance = exp(-_AbsorptionColor.rgb * _AbsorptionDensity * thickness);
                half3 ambient = SampleSH(normalWS);
                half3 transmitted = background * transmittance
                    + _ScatterColor.rgb * ambient * _ScatterStrength * (1.0 - transmittance);

                // Reflection.
                half f0Scalar = (_IOR - 1.0) / (_IOR + 1.0);
                half3 f0 = f0Scalar * f0Scalar;
                half3 fresnel = FresnelSchlick(f0, nDotV);
                half3 reflectDir = reflect(-viewDirWS, normalWS);
                half3 reflection = GlossyEnvironmentReflection(reflectDir, positionWS,
                    PerceptualSmoothnessToPerceptualRoughness(_Smoothness), 1.0, baseUV) * _ReflectionStrength;

                InputData inputData = (InputData)0;
                inputData.positionWS = positionWS;
                inputData.normalWS = normalWS;
                inputData.viewDirectionWS = viewDirWS;
                inputData.normalizedScreenSpaceUV = baseUV;
                half3 specular = DirectSpecular(inputData, roughness, f0) * _SpecularStrength;

                half3 color = lerp(transmitted, reflection, fresnel) + specular;
                color = MixFog(color, InitializeInputDataFog(float4(positionWS, 1.0), input.fogCoord));

                // Soften where the water touches other geometry.
                half alpha = saturate(depthBehind / (_EdgeFade * objectScale));
                return half4(color, alpha);
            }
            ENDHLSL
        }
    }

    FallBack Off
}
