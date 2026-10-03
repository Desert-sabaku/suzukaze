Shader "Skybox/CubemapBlend"
{
    Properties
    {
        _Tint ("Tint Color", Color) = (.5, .5, .5, .5)
        [Gamma] _Exposure ("Exposure", Range(0, 8)) = 1.0
        [NoScaleOffset] _TexA ("Cubemap A", Cube) = "grey" {}
        [NoScaleOffset] _TexB ("Cubemap B", Cube) = "grey" {}
        _Blend ("Blend", Range(0, 1)) = 0
    }
    SubShader
    {
        Tags { "Queue"="Background" "RenderType"="Background" "PreviewType"="Skybox" }
        Cull Off ZWrite Off

        Pass
        {
            CGPROGRAM
            #pragma vertex vert
            #pragma fragment frag
            #include "UnityCG.cginc"

            samplerCUBE _TexA;
            samplerCUBE _TexB;
            half4 _TexA_HDR;
            half4 _TexB_HDR;
            half4 _Tint;
            half _Exposure;
            half _Blend;

            struct appdata { float4 vertex : POSITION; };
            struct v2f
            {
                float4 vertex : SV_POSITION;
                float3 texcoord : TEXCOORD0;
            };

            v2f vert (appdata v)
            {
                v2f o;
                o.vertex = UnityObjectToClipPos(v.vertex);
                o.texcoord = v.vertex.xyz;
                return o;
            }

            half4 frag (v2f i) : SV_Target
            {
                half3 a = DecodeHDR(texCUBE(_TexA, i.texcoord), _TexA_HDR);
                half3 b = DecodeHDR(texCUBE(_TexB, i.texcoord), _TexB_HDR);
                half3 c = lerp(a, b, _Blend);
                c *= _Tint.rgb * unity_ColorSpaceDouble.rgb * _Exposure;
                return half4(c, 1);
            }
            ENDCG
        }
    }
    Fallback Off
}