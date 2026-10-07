// 灯台から伸びる光の筋。円錐メッシュに加算合成で描き、根元から先端へ、また輪郭へ向かって薄くする
Shader "Suzukaze/Lighthouse Beam"
{
    Properties
    {
        [HDR] _Color ("Color", Color) = (1, 0.95, 0.8, 1)
        _Intensity ("Intensity", Float) = 1
        _LengthFalloff ("Length Falloff", Range(0.1, 8)) = 1.5
        _EdgeSoftness ("Edge Softness", Range(0.1, 8)) = 2
        _SoftDistance ("Soft Intersection Distance", Float) = 20
    }

    SubShader
    {
        Tags
        {
            "RenderType" = "Transparent"
            "Queue" = "Transparent"
            "RenderPipeline" = "UniversalPipeline"
            "IgnoreProjector" = "True"
        }

        Pass
        {
            Name "Beam"
            Blend One One
            ZWrite Off
            Cull Off

            HLSLPROGRAM
            #pragma vertex Vert
            #pragma fragment Frag

            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Core.hlsl"
            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/DeclareDepthTexture.hlsl"

            CBUFFER_START(UnityPerMaterial)
                half4 _Color;
                half _Intensity;
                half _LengthFalloff;
                half _EdgeSoftness;
                float _SoftDistance;
            CBUFFER_END

            struct Attributes
            {
                float4 positionOS : POSITION;
                float3 normalOS : NORMAL;
                float2 uv : TEXCOORD0;
            };

            struct Varyings
            {
                float4 positionCS : SV_POSITION;
                float3 positionWS : TEXCOORD0;
                float3 normalWS : TEXCOORD1;
                float2 uv : TEXCOORD2;
            };

            Varyings Vert(Attributes input)
            {
                Varyings output;
                output.positionWS = TransformObjectToWorld(input.positionOS.xyz);
                output.positionCS = TransformWorldToHClip(output.positionWS);
                output.normalWS = TransformObjectToWorldNormal(input.normalOS);
                output.uv = input.uv;
                return output;
            }

            half4 Frag(Varyings input) : SV_Target
            {
                // 面を正面から見るほど光の層が厚く見えるとみなし、輪郭をぼかす
                const float3 viewDir = normalize(GetWorldSpaceViewDir(input.positionWS));
                const half facing = abs(dot(normalize(input.normalWS), viewDir));
                const half edge = pow(facing, _EdgeSoftness);
                // uv.y は根元 0、先端 1
                const half along = pow(saturate(1 - input.uv.y), _LengthFalloff);
                // 地面や木に刺さる部分で、交差の線が見えないよう手前から薄くする
                const float2 screenUV = input.positionCS.xy / _ScaledScreenParams.xy;
                const float sceneDepth = LinearEyeDepth(SampleSceneDepth(screenUV), _ZBufferParams);
                const float beamDepth = -TransformWorldToView(input.positionWS).z;
                const half soft = saturate((sceneDepth - beamDepth) / _SoftDistance);
                return half4(_Color.rgb * (_Intensity * edge * along * soft), 1);
            }
            ENDHLSL
        }
    }
}
