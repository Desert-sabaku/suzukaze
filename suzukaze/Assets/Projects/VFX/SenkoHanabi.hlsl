// 線香花火 VFX (Senko Hanabi VFX.vfx) の Custom HLSL ブロックが共有する補助関数と調整値．
// 各ブロックの本体は VFX Graph 上の Custom HLSL ブロックに埋め込まれていて，ここを #include している．
// このファイルを変更したら Senko Hanabi VFX.vfx を Reimport すること (自動では再コンパイルされない)．
//
// 時間はすべて公開パラメータ Elapsed (着火からの秒数) から解析的に求めるので，
// SenkoHanabiController が Elapsed を進める限り VFX の内部時間に依存しない．
// 段階は BurnDuration に対する割合 u = Elapsed / BurnDuration で固定されている (SH_Phases)．
//   0.00-0.07 蕾 (火玉ができる)  0.06-0.32 牡丹  0.24-0.63 松葉
//   0.55-0.86 柳  0.78-1.00 散り菊  1.00- 燃え尽き (火玉が冷える)
// DropTime を過ぎると火玉が落ち，新しい火花は出なくなる．
//
// 位置の単位はエフェクトのローカル空間のメートル．原点が手 (こよりの上端) で，
// 火玉は (0, -StringLength, 0) にぶら下がる．

#ifndef SENKO_HANABI_INCLUDED
#define SENKO_HANABI_INCLUDED

// ---- 段階ごとの調整値 (x 牡丹, y 松葉, z 柳, w 散り菊) -------------------------
// 激しさ 1 のときの 1 段目の火花の発生数 (個/秒)．スポナーの Rate (400) が上限．
#define SH_SPARK_RATE float4(30.0, 380.0, 110.0, 40.0)
// 1 段目の火花の初速 (m/s)
#define SH_SPARK_SPEED float4(0.35, 1.3, 0.95, 0.45)
// 1 段目の火花の寿命 (秒)
#define SH_SPARK_LIFE float4(0.10, 0.10, 0.34, 0.07)
// 火花にかかる重力 (m/s^2)．柳を大きくして垂れ下がらせる．
#define SH_SPARK_GRAVITY float4(0.6, 0.8, 3.2, 0.5)

float SH_Window(float u, float a, float b, float c, float d)
{
    return smoothstep(a, b, u) * (1.0 - smoothstep(c, d, u));
}

// 牡丹・松葉・柳・散り菊の重み (0-1)
float4 SH_Phases(float elapsed, float burnDuration)
{
    float u = elapsed / max(burnDuration, 0.01);
    return float4(
        SH_Window(u, 0.06, 0.12, 0.24, 0.32),
        SH_Window(u, 0.24, 0.32, 0.55, 0.63),
        SH_Window(u, 0.55, 0.63, 0.78, 0.86),
        SH_Window(u, 0.78, 0.86, 0.94, 1.00));
}

float4 SH_Normalize(float4 w)
{
    return w / max(dot(w, float4(1, 1, 1, 1)), 1e-4);
}

float3 SH_RandomDirection(float r1, float r2)
{
    float y = r1 * 2.0 - 1.0;
    float a = r2 * 6.2831853;
    float r = sqrt(saturate(1.0 - y * y));
    return float3(r * cos(a), y, r * sin(a));
}

// 火玉の直径．蕾で育ち，牡丹の頃は脈打ち，燃え尽きると少し縮む．
float SH_BallSize(float elapsed, float burnDuration, float intensity, float ballSize)
{
    float u = elapsed / max(burnDuration, 0.01);
    float grow = smoothstep(0.0, 0.07, u);
    float burnt = smoothstep(0.94, 1.08, u);
    float boil = 1.0 + 0.12 * sin(elapsed * 37.0) * sin(elapsed * 23.0) * (1.0 - burnt);
    return ballSize * grow * lerp(0.7, 1.1, intensity) * boil * lerp(1.0, 0.8, burnt);
}

#endif
