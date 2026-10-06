Shader "Hidden/Suzukaze/WetnessStamp"
{
    SubShader
    {
        Pass
        {
            ZTest Always
            ZWrite Off
            Cull Off
            Blend Off

            HLSLPROGRAM
            #pragma vertex Vert
            #pragma fragment Frag

            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Core.hlsl"

            float4 _StampRect; // xy: world XZ min, z: 1 / world size
            float _StampValue; // time + 1
            float _ContactY; // world Y below which water counts as touching the ground

            struct Attributes
            {
                float4 positionOS : POSITION;
            };

            struct Varyings
            {
                float4 positionCS : SV_POSITION;
                float positionY : TEXCOORD0;
            };

            Varyings Vert(Attributes input)
            {
                Varyings output;
                float3 positionWS = TransformObjectToWorld(input.positionOS.xyz);
                float2 uv = (positionWS.xz - _StampRect.xy) * _StampRect.z;
                output.positionCS = float4(uv * 2.0 - 1.0, 0.5, 1.0);
                #if UNITY_UV_STARTS_AT_TOP
                output.positionCS.y = -output.positionCS.y;
                #endif
                output.positionY = positionWS.y;
                return output;
            }

            float4 Frag(Varyings input) : SV_Target
            {
                clip(_ContactY - input.positionY);
                return _StampValue;
            }
            ENDHLSL
        }
    }
}