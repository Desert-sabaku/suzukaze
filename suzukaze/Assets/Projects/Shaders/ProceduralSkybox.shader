Shader "Suzukaze/ProceduralSkybox"
{
    Properties
    {
        [Header(Sky Day)]
        _DayZenithColor ("Zenith", Color) = (0.18, 0.42, 0.85, 1)
        _DayHorizonColor ("Horizon", Color) = (0.68, 0.84, 1.0, 1)

        [Header(Sky Sunset)]
        _SunsetZenithColor ("Zenith", Color) = (0.28, 0.27, 0.52, 1)
        _SunsetHorizonColor ("Horizon", Color) = (1.0, 0.45, 0.16, 1)
        _SunsetRange ("Sun Height Range", Range(0.05, 0.6)) = 0.3

        [Header(Sky Night)]
        _NightZenithColor ("Zenith", Color) = (0.004, 0.008, 0.025, 1)
        _NightHorizonColor ("Horizon", Color) = (0.03, 0.05, 0.10, 1)

        [Header(Ground and Horizon)]
        _GroundColor ("Ground", Color) = (0.13, 0.12, 0.11, 1)
        _HorizonExponent ("Horizon Exponent", Range(0.5, 8)) = 3
        _HorizonSharpness ("Horizon Blend Width", Range(0.001, 0.2)) = 0.02
        _Exposure ("Exposure", Range(0, 4)) = 1

        [Header(Sun)]
        [HDR] _SunColor ("Color", Color) = (1.0, 0.95, 0.85, 1)
        _SunSize ("Angular Radius", Range(0.005, 0.2)) = 0.035
        _SunIntensity ("Disk Intensity", Range(0, 30)) = 10
        _SunGlowExponent ("Glow Exponent", Range(1, 256)) = 24
        _SunGlowStrength ("Glow Strength", Range(0, 4)) = 0.6

        [Header(Moon)]
        _MoonColor ("Color", Color) = (0.90, 0.93, 1.0, 1)
        _MoonSize ("Angular Radius", Range(0.005, 0.2)) = 0.03
        _MoonIntensity ("Intensity", Range(0, 10)) = 1
        _MoonPhase ("Phase (0 New, 0.5 Full)", Range(0, 1)) = 0.5
        _MoonOffset ("Direction Offset", Vector) = (0, 0, 0, 0)
        _MoonCraterScale ("Crater Scale", Range(1, 20)) = 5
        _MoonCraterStrength ("Crater Strength", Range(0, 1)) = 0.45
        _MoonGlowColor ("Glow Color", Color) = (0.35, 0.42, 0.6, 1)
        _MoonGlowExponent ("Glow Exponent", Range(1, 256)) = 48
        _MoonGlowStrength ("Glow Strength", Range(0, 2)) = 0.4

        [Header(Stars)]
        _StarDensity ("Density", Range(20, 400)) = 150
        _StarThreshold ("Rarity", Range(0, 1)) = 0.85
        _StarSize ("Size", Range(0.05, 0.5)) = 0.25
        _StarBrightness ("Brightness", Range(0, 10)) = 3
        _StarTwinkleSpeed ("Twinkle Speed", Range(0, 10)) = 3
        _StarRotationSpeed ("Rotation Speed", Range(0, 0.1)) = 0.005

        [Header(Clouds)]
        _CloudColorDay ("Day Color", Color) = (1.0, 1.0, 1.0, 1)
        _CloudColorSunset ("Sunset Color", Color) = (1.0, 0.58, 0.38, 1)
        _CloudColorNight ("Night Color", Color) = (0.07, 0.08, 0.11, 1)
        _CloudShadowColor ("Shadow Tint", Color) = (0.55, 0.60, 0.70, 1)
        _CloudScale ("Scale", Range(0.1, 10)) = 1.5
        _CloudDetailScale ("Detail Scale", Range(1, 10)) = 3.5
        _CloudCoverage ("Coverage", Range(0, 1)) = 0.5
        _CloudSoftness ("Softness", Range(0.01, 1)) = 0.3
        _CloudDensity ("Density", Range(0, 1)) = 0.9
        _CloudWind ("Wind (XY Base, ZW Detail)", Vector) = (0.02, 0.008, 0.035, 0.012)
        _CloudHeight ("Curvature", Range(0.01, 1)) = 0.25
        _CloudHorizonFade ("Horizon Fade", Range(0.001, 1)) = 0.15
        _CloudSilverLining ("Silver Lining", Range(0, 4)) = 1.5
    }

    SubShader
    {
        Tags
        {
            "RenderType" = "Background"
            "Queue" = "Background"
            "PreviewType" = "Skybox"
            "RenderPipeline" = "UniversalPipeline"
        }

        Cull Off
        ZWrite Off

        Pass
        {
            Name "ProceduralSkybox"

            HLSLPROGRAM
            #pragma vertex Vert
            #pragma fragment Frag
            #pragma target 3.5

            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Core.hlsl"

            CBUFFER_START(UnityPerMaterial)
                half4 _DayZenithColor;
                half4 _DayHorizonColor;
                half4 _SunsetZenithColor;
                half4 _SunsetHorizonColor;
                float _SunsetRange;
                half4 _NightZenithColor;
                half4 _NightHorizonColor;
                half4 _GroundColor;
                float _HorizonExponent;
                float _HorizonSharpness;
                float _Exposure;

                half4 _SunColor;
                float _SunSize;
                float _SunIntensity;
                float _SunGlowExponent;
                float _SunGlowStrength;

                half4 _MoonColor;
                float _MoonSize;
                float _MoonIntensity;
                float _MoonPhase;
                float4 _MoonOffset;
                float _MoonCraterScale;
                float _MoonCraterStrength;
                half4 _MoonGlowColor;
                float _MoonGlowExponent;
                float _MoonGlowStrength;

                float _StarDensity;
                float _StarThreshold;
                float _StarSize;
                float _StarBrightness;
                float _StarTwinkleSpeed;
                float _StarRotationSpeed;

                half4 _CloudColorDay;
                half4 _CloudColorSunset;
                half4 _CloudColorNight;
                half4 _CloudShadowColor;
                float _CloudScale;
                float _CloudDetailScale;
                float _CloudCoverage;
                float _CloudSoftness;
                float _CloudDensity;
                float4 _CloudWind;
                float _CloudHeight;
                float _CloudHorizonFade;
                float _CloudSilverLining;
            CBUFFER_END

            struct Attributes
            {
                float4 positionOS : POSITION;
                UNITY_VERTEX_INPUT_INSTANCE_ID
            };

            struct Varyings
            {
                float4 positionCS : SV_POSITION;
                float3 viewDirWS : TEXCOORD0;
                UNITY_VERTEX_OUTPUT_STEREO
            };

            // ---------------------------------------------------------------
            // Noise
            // ---------------------------------------------------------------

            // Hash functions by Dave Hoskins (sin-free, stable across GPUs).
            float Hash12(float2 p)
            {
                float3 p3 = frac(float3(p.xyx) * 0.1031);
                p3 += dot(p3, p3.yzx + 33.33);
                return frac((p3.x + p3.y) * p3.z);
            }

            float Hash13(float3 p3)
            {
                p3 = frac(p3 * 0.1031);
                p3 += dot(p3, p3.zyx + 31.32);
                return frac((p3.x + p3.y) * p3.z);
            }

            float3 Hash33(float3 p3)
            {
                p3 = frac(p3 * float3(0.1031, 0.1030, 0.0973));
                p3 += dot(p3, p3.yxz + 33.33);
                return frac((p3.xxy + p3.yxx) * p3.zyx);
            }

            float ValueNoise(float2 p)
            {
                float2 i = floor(p);
                float2 f = frac(p);
                float2 u = f * f * (3.0 - 2.0 * f);
                float a = Hash12(i);
                float b = Hash12(i + float2(1.0, 0.0));
                float c = Hash12(i + float2(0.0, 1.0));
                float d = Hash12(i + float2(1.0, 1.0));
                return lerp(lerp(a, b, u.x), lerp(c, d, u.x), u.y);
            }

            float Fbm(float2 p, int octaves)
            {
                const float2x2 rot = float2x2(0.8, -0.6, 0.6, 0.8);
                float value = 0.0;
                float amplitude = 0.5;
                for (int i = 0; i < octaves; i++)
                {
                    value += amplitude * ValueNoise(p);
                    p = mul(rot, p) * 2.02 + 17.0;
                    amplitude *= 0.5;
                }
                return value;
            }

            float3 RotateAroundAxis(float3 v, float3 axis, float angle)
            {
                float s, c;
                sincos(angle, s, c);
                return v * c + cross(axis, v) * s + axis * dot(axis, v) * (1.0 - c);
            }

            // ---------------------------------------------------------------
            // Sky elements
            // ---------------------------------------------------------------

            float3 GetSunDirection()
            {
                // _MainLightPosition.xyz is the direction towards the main Directional Light.
                float3 d = _MainLightPosition.xyz;
                return dot(d, d) > 1e-6 ? normalize(d) : normalize(float3(0.3, 0.5, 0.2));
            }

            float StarLayer(float3 dir, float density, float seed, out float3 tint)
            {
                float3 p = dir * density;
                float3 cell = floor(p);
                float3 f = frac(p);
                float3 h = Hash33(cell + seed);

                // Keep the star away from cell borders so it is never clipped.
                float3 starPos = 0.2 + 0.6 * h;
                float dist = length(f - starPos);

                float present = step(_StarThreshold, Hash13(cell + seed + 31.7));
                float magnitude = Hash13(cell + seed + 7.1);
                float size = _StarSize * (0.5 + magnitude);
                float shape = saturate(1.0 - dist / size);
                shape *= shape * shape;

                float twinkle = 0.65 + 0.35 * sin(_Time.y * _StarTwinkleSpeed * (0.5 + h.x) + h.y * TWO_PI);
                tint = lerp(float3(0.75, 0.85, 1.0), float3(1.0, 0.85, 0.7), h.z);
                return shape * present * magnitude * magnitude * twinkle;
            }

            float3 Stars(float3 dir)
            {
                // Slow rotation around a tilted celestial pole.
                const float3 pole = normalize(float3(0.0, 1.0, 0.6));
                float3 d = RotateAroundAxis(dir, pole, _Time.y * _StarRotationSpeed);

                float3 tintA, tintB;
                float a = StarLayer(d, _StarDensity, 0.0, tintA);
                float b = StarLayer(d, _StarDensity * 0.45, 113.0, tintB) * 1.5;
                return (tintA * a + tintB * b) * _StarBrightness;
            }

            // Returns moon radiance; outputs the disk mask for star occlusion.
            float3 Moon(float3 dir, float3 moonDir, out float diskMask)
            {
                float3 up = abs(moonDir.y) < 0.999 ? float3(0.0, 1.0, 0.0) : float3(1.0, 0.0, 0.0);
                float3 right = normalize(cross(up, moonDir));
                float3 upLocal = cross(moonDir, right);

                float2 local = float2(dot(dir, right), dot(dir, upLocal)) / _MoonSize;
                float r = length(local);
                float front = step(0.0, dot(dir, moonDir));
                diskMask = (1.0 - smoothstep(0.92, 1.0, r)) * front;

                float3 n = float3(local, sqrt(saturate(1.0 - r * r)));

                // Phase: 0 = new moon (lit from behind), 0.5 = full moon (lit from the viewer).
                float phaseAngle = _MoonPhase * TWO_PI;
                float3 phaseLight = float3(sin(phaseAngle), 0.0, -cos(phaseAngle));
                float lit = smoothstep(-0.05, 0.1, dot(n, phaseLight));

                float craters = Fbm(local * _MoonCraterScale + 23.0, 4);
                float surface = 1.0 - _MoonCraterStrength * smoothstep(0.4, 0.7, craters);
                float limb = pow(saturate(n.z), 0.35);

                float3 color = _MoonColor.rgb * _MoonIntensity * surface * limb * lit;
                float3 earthshine = _MoonColor.rgb * 0.015 * surface;
                return (color + earthshine) * diskMask;
            }

            // Returns cloud color in rgb and coverage in a.
            float4 Clouds(float3 dir, float3 sunDir, float3 moonDir, float dayF, float sunsetF, float nightF,
                          float3 horizonColor, float3 sunColor, float moonBrightness)
            {
                float horizonMask = smoothstep(0.0, _CloudHorizonFade, dir.y);
                if (horizonMask <= 0.0)
                {
                    return 0.0;
                }

                // Project onto a curved cloud plane above the viewer.
                float2 uv = dir.xz / (dir.y + _CloudHeight) * _CloudScale;
                float t = _Time.y;
                float2 baseUV = uv + _CloudWind.xy * t;
                float2 detailUV = uv * _CloudDetailScale + _CloudWind.zw * t + 5.2;

                float base = Fbm(baseUV, 5);
                float detail = Fbm(detailUV, 4);
                float n = base - (detail - 0.5) * 0.35;

                float threshold = lerp(0.8, 0.25, _CloudCoverage);
                float coverage = smoothstep(threshold, threshold + _CloudSoftness, n);
                float alpha = coverage * _CloudDensity * horizonMask;

                // Cheap self-shadowing: compare density a step towards the light.
                float3 lightDir = dayF + sunsetF > 0.01 ? sunDir : moonDir;
                float2 lightStep = lightDir.xz * 0.15;
                float towardsLight = Fbm(baseUV + lightStep, 4) - (detail - 0.5) * 0.35;
                float lighting = saturate(0.6 + (n - towardsLight) * 4.0);

                float3 litColor = lerp(_CloudColorNight.rgb, _CloudColorDay.rgb, dayF);
                litColor = lerp(litColor, _CloudColorSunset.rgb, sunsetF * 0.8);
                float3 color = lerp(litColor * _CloudShadowColor.rgb, litColor, lighting);

                // Bright edges when looking towards the sun or moon.
                float edges = 1.0 - coverage;
                float sunScatter = pow(saturate(dot(dir, sunDir)), 8.0) * saturate(dayF + sunsetF);
                color += sunColor * sunScatter * edges * _CloudSilverLining;
                float moonScatter = pow(saturate(dot(dir, moonDir)), 16.0) * nightF * moonBrightness;
                color += _MoonGlowColor.rgb * moonScatter * (0.3 + edges) * _CloudSilverLining;

                // Atmospheric perspective towards the horizon.
                color = lerp(color, horizonColor, pow(1.0 - saturate(dir.y), 6.0) * 0.6);
                return float4(color, alpha);
            }

            // ---------------------------------------------------------------
            // Vertex / Fragment
            // ---------------------------------------------------------------

            Varyings Vert(Attributes input)
            {
                Varyings output = (Varyings)0;
                UNITY_SETUP_INSTANCE_ID(input);
                UNITY_INITIALIZE_VERTEX_OUTPUT_STEREO(output);
                output.positionCS = TransformObjectToHClip(input.positionOS.xyz);
                output.viewDirWS = input.positionOS.xyz;
                return output;
            }

            half4 Frag(Varyings input) : SV_Target
            {
                UNITY_SETUP_STEREO_EYE_INDEX_POST_VERTEX(input);

                float3 dir = normalize(input.viewDirWS);
                float3 sunDir = GetSunDirection();
                float3 moonDir = normalize(-sunDir + _MoonOffset.xyz);

                float sunY = sunDir.y;
                float dayF = smoothstep(-0.05, 0.25, sunY);
                float nightF = 1.0 - smoothstep(-0.25, 0.0, sunY);
                float sunsetF = saturate(1.0 - abs(sunY) / _SunsetRange);
                sunsetF *= sunsetF;

                // Sunset colors concentrate on the sun's side of the sky.
                float2 dirH = dir.xz / max(length(dir.xz), 1e-4);
                float2 sunH = sunDir.xz / max(length(sunDir.xz), 1e-4);
                float sunSide = saturate(dot(dirH, sunH) * 0.5 + 0.5);
                sunSide *= sunSide;

                // --- Sky gradient ---
                float3 zenith = lerp(_NightZenithColor.rgb, _DayZenithColor.rgb, dayF);
                float3 horizon = lerp(_NightHorizonColor.rgb, _DayHorizonColor.rgb, dayF);
                zenith = lerp(zenith, _SunsetZenithColor.rgb, sunsetF * 0.5);
                horizon = lerp(horizon, _SunsetHorizonColor.rgb, sunsetF * (0.35 + 0.65 * sunSide));

                float height = saturate(dir.y);
                float3 sky = lerp(zenith, horizon, pow(1.0 - height, _HorizonExponent));

                float groundF = 1.0 - smoothstep(-_HorizonSharpness, _HorizonSharpness, dir.y);
                float3 ground = _GroundColor.rgb * lerp(0.05, 1.0, dayF);
                ground = lerp(ground, horizon, 0.25);
                float skyMask = 1.0 - groundF;

                // --- Sun ---
                float3 sunColor = lerp(_SunColor.rgb, _SunsetHorizonColor.rgb * 1.5, sunsetF * 0.6);
                float sunCos = dot(dir, sunDir);
                float sunAngle = acos(clamp(sunCos, -1.0, 1.0));
                float sunDisk = 1.0 - smoothstep(_SunSize * 0.85, _SunSize, sunAngle);
                float sunVisible = smoothstep(-0.1, 0.0, sunY);
                float sunGlow = pow(saturate(sunCos), _SunGlowExponent) * _SunGlowStrength * (1.0 + sunsetF);
                sky += sunColor * sunGlow * sunVisible;

                // --- Moon ---
                float moonDiskMask;
                float3 moon = Moon(dir, moonDir, moonDiskMask);
                float moonBrightness = 0.5 - 0.5 * cos(_MoonPhase * TWO_PI);
                float moonVisibility = lerp(1.0, 0.25, dayF);
                float moonGlow = pow(saturate(dot(dir, moonDir)), _MoonGlowExponent) * _MoonGlowStrength *
                    moonBrightness;
                sky += _MoonGlowColor.rgb * moonGlow * nightF;

                // --- Stars ---
                float starFade = nightF * smoothstep(0.0, 0.2, dir.y) * (1.0 - moonDiskMask);
                sky += Stars(dir) * starFade;

                sky += moon * moonVisibility;
                sky += sunColor * sunDisk * _SunIntensity * sunVisible;

                // --- Clouds ---
                float4 clouds = Clouds(dir, sunDir, moonDir, dayF, sunsetF, nightF, horizon, sunColor, moonBrightness);
                sky = lerp(sky, clouds.rgb, clouds.a);

                float3 color = lerp(ground, sky, skyMask) * _Exposure;
                return half4(color, 1.0);
            }
            ENDHLSL
        }
    }

    Fallback Off
}