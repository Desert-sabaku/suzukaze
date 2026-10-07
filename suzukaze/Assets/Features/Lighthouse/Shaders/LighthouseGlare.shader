// 灯台の光源のまぶしさ。カメラに向けた四角形に、丸い光と横に伸びる光芒を加算合成で描く
Shader "Suzukaze/Lighthouse Glare"
{
    Properties
    {
        [HDR] _Color ("Color", Color) = (1, 0.95, 0.8, 1)
        _Intensity ("Intensity", Float) = 1
        _Size ("Size (world units)", Float) = 10
        _Falloff ("Falloff", Range(0.5, 16)) = 4
        _Streak ("Streak", Range(0, 2)) = 0.6
        _TowardCamera ("Offset Toward Camera", Float) = 5
    }

    SubShader
    {
        Tags
        {
            "RenderType" = "Transparent"
            "Queue" = "Transparent+1"
            "RenderPipeline" = "UniversalPipeline"
            "IgnoreProjector" = "True"
        }

        Pass
        {
            Name "Glare"
            Blend One One
            ZWrite Off
            ZTest LEqual
            Cull Off

            HLSLPROGRAM
            #pragma vertex Vert
            #pragma fragment Frag

            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Core.hlsl"

            CBUFFER_START(UnityPerMaterial)
                half4 _Color;
                half _Intensity;
                float _Size;
                half _Falloff;
                half _Streak;
                float _TowardCamera;
            CBUFFER_END

            struct Attributes
            {
                float4 positionOS : POSITION;
                float2 uv : TEXCOORD0;
            };

            struct Varyings
            {
                float4 positionCS : SV_POSITION;
                float2 offset : TEXCOORD0;
            };

            Varyings Vert(Attributes input)
            {
                Varyings output;
                // オブジェクトの原点を中心に、ビュー空間で四角形を広げる
                float3 centerVS = TransformWorldToView(TransformObjectToWorld(float3(0, 0, 0)));
                // ランプのガラスに埋もれないよう、カメラ側へ少し寄せる
                centerVS += normalize(-centerVS) * _TowardCamera;
                const float2 offset = input.uv * 2 - 1;
                centerVS.xy += offset * _Size;
                output.positionCS = TransformWViewToHClip(centerVS);
                output.offset = offset;
                return output;
            }

            half4 Frag(Varyings input) : SV_Target
            {
                const float2 p = input.offset;
                const half core = pow(saturate(1 - length(p)), _Falloff);
                const half streak = exp(-abs(p.y) * 40) * pow(saturate(1 - abs(p.x)), 2) * _Streak;
                return half4(_Color.rgb * (_Intensity * (core + streak)), 1);
            }
            ENDHLSL
        }
    }
}
