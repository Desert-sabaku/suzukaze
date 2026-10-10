Shader "Suzukaze/CoffeeSurface"
{
    Properties
    {
        [Header(Color)]
        _BaseColor ("Base Color", Color) = (0.075, 0.032, 0.012, 1)
        _EdgeColor ("Edge Color", Color) = (0.22, 0.11, 0.05, 1)
        _EdgeWidth ("Edge Width (0-1 of radius)", Range(0, 0.5)) = 0.12

        [Header(Slosh)]
        _SloshTilt ("Slosh Tilt (slope)", Range(0, 0.2)) = 0.04
        _SloshSpeed ("Slosh Speed", Range(0, 5)) = 1.2

        [Header(Ripples)]
        _RippleStrength ("Ring Ripple Strength", Range(0, 1)) = 0.25
        _RippleFrequency ("Ring Ripple Frequency", Range(1, 40)) = 14
        _RippleSpeed ("Ring Ripple Speed", Range(0, 10)) = 2.5
        _NoiseStrength ("Noise Ripple Strength", Range(0, 1)) = 0.15
        _NoiseScale ("Noise Ripple Scale", Range(0.5, 20)) = 5

        [Header(Surface)]
        _Smoothness ("Smoothness", Range(0, 1)) = 0.95
        _ReflectionStrength ("Reflection Strength", Range(0, 2)) = 0.7
        _SpecularStrength ("Specular Strength", Range(0, 4)) = 1.5
    }

    SubShader
    {
        Tags
        {
            "RenderPipeline" = "UniversalPipeline"
            "RenderType" = "Opaque"
            "Queue" = "Geometry"
        }

        HLSLINCLUDE
        #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Core.hlsl"

        CBUFFER_START(UnityPerMaterial)
            half4 _BaseColor;
            half4 _EdgeColor;
            half _EdgeWidth;
            float _SloshTilt;
            float _SloshSpeed;
            half _RippleStrength;
            float _RippleFrequency;
            float _RippleSpeed;
            half _NoiseStrength;
            float _NoiseScale;
            half _Smoothness;
            half _ReflectionStrength;
            half _SpecularStrength;
        CBUFFER_END

        // World-space slope of the sloshing surface (d height / d xz). Two incommensurate
        // frequencies so the liquid never settles into an obvious loop.
        float2 SloshSlope()
        {
            float t = _Time.y * _SloshSpeed;
            float2 slope = float2(sin(t * 1.7) + 0.4 * sin(t * 3.1 + 1.3),
                                  cos(t * 1.3) + 0.4 * sin(t * 2.3 + 0.7));
            return slope * (_SloshTilt / 1.4);
        }

        // Tilt the surface around the object's centre so the liquid appears to rock.
        float3 SloshPositionWS(float3 positionOS)
        {
            float3 positionWS = TransformObjectToWorld(positionOS);
            float3 centerWS = TransformObjectToWorld(float3(0, 0, 0));
            positionWS.y += dot(positionWS.xz - centerWS.xz, SloshSlope());
            return positionWS;
        }
        ENDHLSL

        Pass
        {
            Name "ForwardLit"
            Tags
            {
                "LightMode" = "UniversalForward"
            }

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

            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Lighting.hlsl"

            struct Attributes
            {
                float4 positionOS : POSITION;
                UNITY_VERTEX_INPUT_INSTANCE_ID
            };

            struct Varyings
            {
                float4 positionCS : SV_POSITION;
                float3 positionWS : TEXCOORD0;
                float2 radialOS : TEXCOORD1; // object XZ scaled to the unit disc
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

                float3 positionWS = SloshPositionWS(input.positionOS.xyz);
                output.positionWS = positionWS;
                output.positionCS = TransformWorldToHClip(positionWS);
                // Unity's cylinder primitive has a radius of 0.5.
                output.radialOS = input.positionOS.xz * 2.0;
                output.fogCoord = ComputeFogFactor(output.positionCS.z);
                return output;
            }

            // ---------------------------------------------------------------- Noise

            float2 Hash22(float2 p)
            {
                p = float2(dot(p, float2(127.1, 311.7)), dot(p, float2(269.5, 183.3)));
                return frac(sin(p) * 43758.5453) * 2.0 - 1.0;
            }

            // 2D gradient noise in roughly [-1, 1].
            float GradientNoise(float2 p)
            {
                float2 i = floor(p);
                float2 f = frac(p);
                float2 u = f * f * (3.0 - 2.0 * f);
                float n00 = dot(Hash22(i + float2(0, 0)), f - float2(0, 0));
                float n10 = dot(Hash22(i + float2(1, 0)), f - float2(1, 0));
                float n01 = dot(Hash22(i + float2(0, 1)), f - float2(0, 1));
                float n11 = dot(Hash22(i + float2(1, 1)), f - float2(1, 1));
                return lerp(lerp(n00, n10, u.x), lerp(n01, n11, u.x), u.y);
            }

            // ---------------------------------------------------------------- Ripples

            // Ripple height on the unit disc: rings travelling inward from the cup wall
            // plus drifting noise.
            float RippleHeight(float2 p)
            {
                float t = _Time.y;
                float r = length(p);
                float ring = sin(r * _RippleFrequency + t * _RippleSpeed) * smoothstep(0.0, 0.6, r);
                float2 drift = float2(t * 0.11, -t * 0.07);
                float n = GradientNoise(p * _NoiseScale + drift)
                    + 0.5 * GradientNoise(p * _NoiseScale * 2.1 - drift * 1.7 + 13.1);
                return ring * _RippleStrength / _RippleFrequency + n * _NoiseStrength / _NoiseScale;
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
                float2 p = input.radialOS;

                // Ripple normal from finite differences on the unit disc. The disc's world
                // radius only rescales the slope, which the strength properties absorb.
                const float e = 0.01;
                float h = RippleHeight(p);
                float2 gradient = float2(RippleHeight(p + float2(e, 0)), RippleHeight(p + float2(0, e))) - h;
                gradient = gradient / e + SloshSlope();
                float3 normalWS = normalize(float3(-gradient.x, 1.0, -gradient.y));

                // Body colour: lighter towards the wall, like the thin film where coffee meets the cup.
                half edge = smoothstep(1.0 - _EdgeWidth, 1.0, length(p));
                half3 albedo = lerp(_BaseColor.rgb, _EdgeColor.rgb, edge);
                Light mainLight = GetMainLight(TransformWorldToShadowCoord(positionWS));
                half3 diffuse = albedo * (mainLight.color * mainLight.shadowAttenuation
                    * saturate(dot(normalWS, mainLight.direction)) + SampleSH(normalWS));

                // Reflection of the surroundings and the sun glint, both broken up by the ripples.
                half nDotV = saturate(dot(normalWS, viewDirWS));
                half3 fresnel = FresnelSchlick(half3(0.02, 0.02, 0.02), nDotV);
                half3 reflectDir = reflect(-viewDirWS, normalWS);
                half perceptualRoughness = PerceptualSmoothnessToPerceptualRoughness(_Smoothness);
                float2 screenUV = GetNormalizedScreenSpaceUV(input.positionCS);
                half3 reflection = GlossyEnvironmentReflection(reflectDir, positionWS, perceptualRoughness, 1.0, screenUV)
                    * _ReflectionStrength;
                half roughness = max(PerceptualSmoothnessToRoughness(_Smoothness), HALF_MIN_SQRT);
                half3 specular = SpecularGGX(mainLight, normalWS, viewDirWS, roughness, 0.02) * _SpecularStrength;

                half3 color = lerp(diffuse, reflection, fresnel) + specular;
                color = MixFog(color, input.fogCoord);
                return half4(color, 1.0);
            }
            ENDHLSL
        }

        Pass
        {
            Name "DepthOnly"
            Tags
            {
                "LightMode" = "DepthOnly"
            }

            ZWrite On
            ColorMask R
            Cull Back

            HLSLPROGRAM
            #pragma target 3.5
            #pragma vertex DepthVert
            #pragma fragment DepthFrag
            #pragma multi_compile_instancing

            struct Attributes
            {
                float4 positionOS : POSITION;
                UNITY_VERTEX_INPUT_INSTANCE_ID
            };

            struct Varyings
            {
                float4 positionCS : SV_POSITION;
                UNITY_VERTEX_OUTPUT_STEREO
            };

            Varyings DepthVert(Attributes input)
            {
                Varyings output = (Varyings)0;
                UNITY_SETUP_INSTANCE_ID(input);
                UNITY_INITIALIZE_VERTEX_OUTPUT_STEREO(output);
                output.positionCS = TransformWorldToHClip(SloshPositionWS(input.positionOS.xyz));
                return output;
            }

            half DepthFrag(Varyings input) : SV_Target
            {
                return input.positionCS.z;
            }
            ENDHLSL
        }

        Pass
        {
            Name "DepthNormals"
            Tags
            {
                "LightMode" = "DepthNormals"
            }

            ZWrite On
            Cull Back

            HLSLPROGRAM
            #pragma target 3.5
            #pragma vertex DepthNormalsVert
            #pragma fragment DepthNormalsFrag
            #pragma multi_compile_instancing

            struct Attributes
            {
                float4 positionOS : POSITION;
                UNITY_VERTEX_INPUT_INSTANCE_ID
            };

            struct Varyings
            {
                float4 positionCS : SV_POSITION;
                UNITY_VERTEX_OUTPUT_STEREO
            };

            Varyings DepthNormalsVert(Attributes input)
            {
                Varyings output = (Varyings)0;
                UNITY_SETUP_INSTANCE_ID(input);
                UNITY_INITIALIZE_VERTEX_OUTPUT_STEREO(output);
                output.positionCS = TransformWorldToHClip(SloshPositionWS(input.positionOS.xyz));
                return output;
            }

            half4 DepthNormalsFrag(Varyings input) : SV_Target
            {
                float2 slope = SloshSlope();
                float3 normalWS = normalize(float3(-slope.x, 1.0, -slope.y));
                return half4(NormalizeNormalPerPixel(normalWS), 0.0);
            }
            ENDHLSL
        }
    }

    FallBack Off
}
