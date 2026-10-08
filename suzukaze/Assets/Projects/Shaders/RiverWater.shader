Shader "Suzukaze/RiverWater"
{
    Properties
    {
        [Header(Flow)]
        _FlowDirection ("Flow Direction (world XZ)", Vector) = (1, 0, 0, 0)
        _FlowSpeed ("Flow Speed (m/s)", Range(0, 20)) = 4
        _FlowPeriod ("Flow Cycle (s)", Range(0.5, 8)) = 2
        _Turbulence ("Turbulence (pattern evolution)", Range(0, 4)) = 0.6
        _SpeedVariation ("Speed Variation", Range(0, 1)) = 0.45
        _Meander ("Current Meander (rad)", Range(0, 1)) = 0.25
        _BankSpeed ("Speed Near Banks", Range(0, 1)) = 0.3
        _BankDepth ("Full Speed Depth (m)", Range(0.1, 20)) = 4

        [Header(Rough And Calm Water)]
        _RoughScale ("Rough Patch Size (m)", Range(10, 300)) = 70
        _RoughContrast ("Rough Patch Contrast", Range(0, 1)) = 0.7

        [Header(Color)]
        _ShallowColor ("Shallow Color", Color) = (0.25, 0.55, 0.50, 1)
        _DeepColor ("Deep Color", Color) = (0.02, 0.12, 0.14, 1)
        _AbsorptionColor ("Absorption (per channel)", Color) = (0.45, 0.12, 0.10, 1)
        _AbsorptionDensity ("Absorption Density (1/m)", Range(0, 5)) = 0.9
        _ScatterDepth ("Scatter Depth (m)", Range(0.1, 20)) = 3

        [Header(Waves)]
        _WaveSize ("Wave Size (m)", Range(1, 40)) = 9
        _WaveStretch ("Stretch Along Flow", Range(1, 8)) = 3
        _NormalStrength ("Normal Strength", Range(0, 4)) = 1.2
        _ChopStrength ("Small Chop Strength", Range(0, 2)) = 0.35
        _NormalFadeDistance ("Normal Fade Distance (m)", Range(10, 500)) = 200

        [Header(Surface)]
        _Smoothness ("Smoothness", Range(0, 1)) = 0.92
        _ReflectionStrength ("Reflection Strength", Range(0, 2)) = 0.8
        _SpecularStrength ("Specular Strength", Range(0, 4)) = 1.2
        _RefractionStrength ("Refraction Strength", Range(0, 0.2)) = 0.04

        [Header(Foam)]
        _FoamColor ("Foam Color", Color) = (0.95, 0.97, 0.97, 1)
        _FoamAmount ("Streak Foam Amount", Range(0, 1)) = 0.3
        _FoamSoftness ("Streak Foam Softness", Range(0.01, 1)) = 0.3
        _FoamStreakLength ("Streak Length", Range(1, 20)) = 5
        _FoamSize ("Streak Size (m)", Range(1, 40)) = 10
        _CrestFoam ("Wave Crest Foam", Range(0, 2)) = 0.6
        _IntersectionFoamDistance ("Intersection Foam Distance (m)", Range(0, 5)) = 1.2
        _RapidsDepth ("Rapids Depth (m)", Range(0, 10)) = 2
        _RapidsFoam ("Rapids Foam Boost", Range(0, 2)) = 0.8
        _FoamFadeDistance ("Streak Foam Fade Distance (m)", Range(10, 1000)) = 300

        [Header(Edges)]
        _EdgeFade ("Shore Fade (m)", Range(0.01, 2)) = 0.3
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

            Blend SrcAlpha OneMinusSrcAlpha
            ZWrite Off
            Cull Back

            HLSLPROGRAM
            #pragma target 3.5
            #pragma vertex Vert
            #pragma fragment Frag

            #pragma multi_compile _ _MAIN_LIGHT_SHADOWS _MAIN_LIGHT_SHADOWS_CASCADE _MAIN_LIGHT_SHADOWS_SCREEN
            #pragma multi_compile_fragment _ _SHADOWS_SOFT _SHADOWS_SOFT_LOW _SHADOWS_SOFT_MEDIUM _SHADOWS_SOFT_HIGH
            #pragma multi_compile_fragment _ _REFLECTION_PROBE_BLENDING
            #pragma multi_compile_fragment _ _REFLECTION_PROBE_BOX_PROJECTION
            #pragma multi_compile_fragment _ _REFLECTION_PROBE_ATLAS
            #pragma multi_compile_fog
            #pragma multi_compile_instancing

            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Core.hlsl"
            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Lighting.hlsl"
            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/DeclareOpaqueTexture.hlsl"
            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/DeclareDepthTexture.hlsl"

            CBUFFER_START(UnityPerMaterial)
                float4 _FlowDirection;
                float _FlowSpeed;
                float _FlowPeriod;
                float _Turbulence;
                float _SpeedVariation;
                float _Meander;
                float _BankSpeed;
                float _BankDepth;
                float _RoughScale;
                half _RoughContrast;
                half4 _ShallowColor;
                half4 _DeepColor;
                half4 _AbsorptionColor;
                half _AbsorptionDensity;
                float _ScatterDepth;
                float _WaveSize;
                float _WaveStretch;
                half _NormalStrength;
                half _ChopStrength;
                float _NormalFadeDistance;
                half _Smoothness;
                half _ReflectionStrength;
                half _SpecularStrength;
                half _RefractionStrength;
                half4 _FoamColor;
                half _FoamAmount;
                half _FoamSoftness;
                float _FoamStreakLength;
                float _FoamSize;
                half _CrestFoam;
                float _IntersectionFoamDistance;
                float _RapidsDepth;
                half _RapidsFoam;
                float _FoamFadeDistance;
                float _EdgeFade;
            CBUFFER_END

            struct Attributes
            {
                float4 positionOS : POSITION;
                UNITY_VERTEX_INPUT_INSTANCE_ID
            };

            struct Varyings
            {
                float4 positionCS : SV_POSITION;
                float3 positionWS : TEXCOORD0;
                float fogCoord : TEXCOORD1;
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
                output.fogCoord = ComputeFogFactor(positionInputs.positionCS.z);
                return output;
            }

            // ---------------------------------------------------------------- Noise

            float3 Hash33(float3 p)
            {
                p = float3(dot(p, float3(127.1, 311.7, 74.7)),
                           dot(p, float3(269.5, 183.3, 246.1)),
                           dot(p, float3(113.5, 271.9, 124.6)));
                return frac(sin(p) * 43758.5453) * 2.0 - 1.0;
            }

            // 3D gradient noise in roughly [-1, 1].
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

            // ---------------------------------------------------------------- Flow space

            struct FlowFrame
            {
                float2 along;  // unit flow direction in world XZ
                float2 across; // perpendicular, in world XZ
            };

            FlowFrame GetFlowFrame()
            {
                FlowFrame frame;
                float2 dir = _FlowDirection.xy;
                frame.along = dot(dir, dir) > 1e-6 ? normalize(dir) : float2(1, 0);
                frame.across = float2(-frame.along.y, frame.along.x);
                return frame;
            }

            // World XZ -> (distance along the flow, distance across it), in metres.
            float2 ToFlowSpace(float2 xz, FlowFrame frame)
            {
                return float2(dot(xz, frame.along), dot(xz, frame.across));
            }

            // Local current in flow space (m/s): slower near the banks, with slowly drifting
            // fast/slow lanes and a gentle meander so the river doesn't move as one sheet.
            float2 FlowVelocity(float2 uv, float waterDepth)
            {
                float t = _Time.y;
                float bank = lerp(_BankSpeed, 1.0, smoothstep(0.0, _BankDepth, waterDepth));
                float lanes = GradientNoise(float3(uv.x * 0.012, uv.y * 0.05, t * 0.04));
                float speed = _FlowSpeed * bank * max(0.15, 1.0 + _SpeedVariation * lanes * 2.0);
                float angle = _Meander * GradientNoise(float3(uv.x * 0.02 + 5.3, uv.y * 0.03, t * 0.06));
                return speed * float2(cos(angle), sin(angle));
            }

            // Two-phase flow: the pattern is advected for one cycle and then restarted, while a
            // second copy half a cycle out of phase hides the restart. This lets the velocity
            // vary per pixel without the pattern stretching over time.
            struct FlowLayers
            {
                float2 uvA;
                float2 uvB;
                float weightA;
                float weightB;
            };

            FlowLayers GetFlowLayers(float2 uv, float2 velocity)
            {
                float cycle = _Time.y / _FlowPeriod;
                float phaseA = frac(cycle);
                float phaseB = frac(cycle + 0.5);
                // Jump to a different part of the pattern on every restart to hide repetition.
                float2 jumpA = floor(cycle) * float2(13.7, 7.3);
                float2 jumpB = floor(cycle + 0.5) * float2(13.7, 7.3) + float2(31.1, 17.9);

                FlowLayers layers;
                layers.uvA = uv - velocity * (phaseA - 0.5) * _FlowPeriod + jumpA;
                layers.uvB = uv - velocity * (phaseB - 0.5) * _FlowPeriod + jumpB;
                layers.weightA = 1.0 - abs(1.0 - 2.0 * phaseA);
                layers.weightB = 1.0 - layers.weightA;
                return layers;
            }

            // Noise octave in flow space, stretched along the flow so features read as
            // streaks rather than blobs. `wavelength` is in metres across the flow.
            float FlowOctave(float2 uv, float wavelength, float evolve, float stretch)
            {
                float frequency = 1.0 / wavelength;
                return GradientNoise(float3(uv.x * frequency / stretch, uv.y * frequency,
                                            _Time.y * _Turbulence * evolve));
            }

            float WaveHeight(float2 uv)
            {
                float h = FlowOctave(uv, _WaveSize, 0.2, _WaveStretch);
                h += 0.45 * FlowOctave(uv + 17.3, _WaveSize * 0.4, 0.4, _WaveStretch);
                h += 0.25 * _ChopStrength * FlowOctave(uv + 41.7, _WaveSize * 0.17, 0.8, _WaveStretch * 0.6);
                return h;
            }

            // Height and its flow-space gradient, blended across the two flow phases.
            float3 FlowWave(FlowLayers layers)
            {
                const float e = 0.15;
                float hA = WaveHeight(layers.uvA);
                float hB = WaveHeight(layers.uvB);
                float2 gA = float2(WaveHeight(layers.uvA + float2(e, 0)), WaveHeight(layers.uvA + float2(0, e))) - hA;
                float2 gB = float2(WaveHeight(layers.uvB + float2(e, 0)), WaveHeight(layers.uvB + float2(0, e))) - hB;
                float height = hA * layers.weightA + hB * layers.weightB;
                // Scale by the wave size so the slope (and so the look) stays the same when
                // the waves are made bigger or smaller.
                float2 gradient = (gA * layers.weightA + gB * layers.weightB) / e * (_WaveSize * 0.3);
                return float3(height, gradient);
            }

            // Large slowly drifting patches of choppy rapids and smooth glides.
            float RoughMask(float2 uv)
            {
                float t = _Time.y;
                float2 p = float2((uv.x - t * _FlowSpeed * 0.6) / (_RoughScale * 2.0), uv.y / _RoughScale);
                float n = GradientNoise(float3(p, t * 0.03));
                n += 0.5 * GradientNoise(float3(p * 2.3 + 9.1, t * 0.05));
                return lerp(1.0, smoothstep(-0.35, 0.45, n), _RoughContrast);
            }

            // ---------------------------------------------------------------- Foam

            float StreakFoam(float2 uv)
            {
                float stretch = _FoamStreakLength;
                float f = FlowOctave(uv + 91.1, _FoamSize, 0.3, stretch);
                f += 0.5 * FlowOctave(uv + 63.9, _FoamSize * 0.4, 0.5, stretch * 0.7);
                return f;
            }

            // Breakup so foam edges look clumpy instead of perfectly smooth.
            float FoamBreakup(float2 uv)
            {
                return FlowOctave(uv + 7.7, _FoamSize * 0.2, 0.8, 1.5) * 0.5 + 0.5;
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

            // ---------------------------------------------------------------- Fragment

            half4 Frag(Varyings input) : SV_Target
            {
                UNITY_SETUP_INSTANCE_ID(input);
                UNITY_SETUP_STEREO_EYE_INDEX_POST_VERTEX(input);

                float3 positionWS = input.positionWS;
                float3 viewDirWS = SafeNormalize(GetWorldSpaceViewDir(positionWS));
                float viewDistance = distance(GetCameraPositionWS(), positionWS);

                // Scene behind the surface.
                float2 baseUV = GetNormalizedScreenSpaceUV(input.positionCS);
                float surfaceEyeDepth = LinearEyeDepth(positionWS, GetWorldToViewMatrix());
                float sceneRawDepth = SampleSceneDepth(baseUV);
                float sceneEyeDepth = LinearEyeDepth(sceneRawDepth, _ZBufferParams);
                float depthBehind = max(sceneEyeDepth - surfaceEyeDepth, 0.0);
                float3 scenePositionWS = ComputeWorldSpacePosition(baseUV, sceneRawDepth, UNITY_MATRIX_I_VP);
                float waterDepth = max(positionWS.y - scenePositionWS.y, 0.0);

                // Flow.
                FlowFrame frame = GetFlowFrame();
                float2 uv = ToFlowSpace(positionWS.xz, frame);
                float2 velocity = FlowVelocity(uv, waterDepth);
                FlowLayers layers = GetFlowLayers(uv, velocity);
                float rough = RoughMask(uv);

                // Waves. Distant pixels cover many wave periods; flatten them to avoid shimmering.
                float normalFade = saturate(1.0 - viewDistance / _NormalFadeDistance);
                float strength = _NormalStrength * lerp(0.3, 1.0, normalFade) * lerp(0.35, 1.0, rough);
                float3 wave = FlowWave(layers);
                float height = wave.x;
                float2 gradXZ = (wave.y * frame.along + wave.z * frame.across) * strength;
                float3 normalWS = normalize(float3(-gradXZ.x, 1.0, -gradXZ.y));

                // Refraction, rejecting samples that land on geometry in front of the water.
                float2 refractedUV = baseUV + normalWS.xz * _RefractionStrength * saturate(depthBehind * 0.5);
                float refractedEyeDepth = LinearEyeDepth(SampleSceneDepth(refractedUV), _ZBufferParams);
                if (refractedEyeDepth < surfaceEyeDepth)
                    refractedUV = baseUV;
                else
                    depthBehind = max(refractedEyeDepth - surfaceEyeDepth, 0.0);
                half3 background = SampleSceneColor(refractedUV);

                // Body colour: absorb the background along the view ray, and fade towards a
                // depth-tinted scatter colour as the water gets deeper.
                Light mainLight = GetMainLight(TransformWorldToShadowCoord(positionWS));
                half3 ambient = SampleSH(half3(0, 1, 0));
                half3 lightIntensity = mainLight.color * mainLight.shadowAttenuation * saturate(mainLight.direction.y)
                    + ambient;
                half3 transmittance = exp(-_AbsorptionColor.rgb * _AbsorptionDensity * depthBehind);
                half depthT = saturate(waterDepth / _ScatterDepth);
                half3 scatter = lerp(_ShallowColor.rgb, _DeepColor.rgb, depthT) * lightIntensity;
                half3 body = lerp(scatter, background, transmittance * (1.0 - depthT * 0.5));

                // Foam: flow-aligned streaks (mostly in the rough patches), wave crests,
                // shallow rapids and contact with rocks and banks.
                float foamFade = saturate(1.0 - viewDistance / _FoamFadeDistance);
                float streak = (StreakFoam(layers.uvA) * layers.weightA + StreakFoam(layers.uvB) * layers.weightB) * 1.6;
                float breakup = FoamBreakup(layers.uvA) * layers.weightA + FoamBreakup(layers.uvB) * layers.weightB;
                float threshold = 1.0 - _FoamAmount * 1.6 * lerp(0.4, 1.2, rough);
                float rapids = _RapidsFoam * saturate(1.0 - waterDepth / max(_RapidsDepth, 1e-3));
                float crest = _CrestFoam * saturate(height) * rough;
                float foam = smoothstep(threshold, threshold + _FoamSoftness, streak + crest + rapids) * foamFade;
                float contact = 1.0 - saturate(depthBehind / max(_IntersectionFoamDistance, 1e-3));
                foam = max(foam, smoothstep(0.45, 0.7, contact * contact + (breakup - 0.5) * 0.8));
                foam *= smoothstep(0.15, 0.6, breakup);
                foam = saturate(foam) * _FoamColor.a;

                // Surface reflection and sun glints.
                half nDotV = saturate(dot(normalWS, viewDirWS));
                half3 fresnel = FresnelSchlick(half3(0.02, 0.02, 0.02), nDotV);
                half3 reflectDir = reflect(-viewDirWS, normalWS);
                half perceptualRoughness = PerceptualSmoothnessToPerceptualRoughness(_Smoothness);
                half3 reflection = GlossyEnvironmentReflection(reflectDir, positionWS, perceptualRoughness, 1.0, baseUV)
                    * _ReflectionStrength;
                half roughness = max(PerceptualSmoothnessToRoughness(_Smoothness), HALF_MIN_SQRT);
                half3 specular = SpecularGGX(mainLight, normalWS, viewDirWS, roughness, 0.02) * _SpecularStrength;

                half3 water = lerp(body, reflection, fresnel) + specular;
                half3 foamLit = _FoamColor.rgb * lightIntensity;
                half3 color = lerp(water, foamLit, foam);
                color = MixFog(color, InitializeInputDataFog(float4(positionWS, 1.0), input.fogCoord));

                // Soften the waterline against the terrain.
                half alpha = saturate(depthBehind / _EdgeFade);
                return half4(color, alpha);
            }
            ENDHLSL
        }
    }

    FallBack Off
}
