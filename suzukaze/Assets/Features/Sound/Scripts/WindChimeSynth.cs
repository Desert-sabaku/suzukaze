using UnityEngine;

namespace Features.Sound.Scripts
{
    /// <summary>
    ///     ガラスの風鈴を舌が 1 回打った音を合成する。録音素材が無いときの代わりに使う
    /// </summary>
    public static class WindChimeSynth
    {
        public const int SampleRate = 48000;

        // ガラスの椀の振動モード。基音に対する周波数比・相対振幅・減衰時間 (秒)
        private static readonly float[] Ratios = { 1f, 2.71f, 5.18f, 8.47f };
        private static readonly float[] Amplitudes = { 1f, 0.45f, 0.22f, 0.1f };
        private static readonly float[] DecaySeconds = { 2.6f, 1.1f, 0.5f, 0.25f };

        // 椀のわずかな歪みで各モードが 2 つに分かれ、うなり (ゆらぎ) が生まれる
        private const float BeatHz = 3.2f;
        private const float StrikeSeconds = 0.004f;
        private const float FadeOutSeconds = 0.05f;
        private const float Peak = 0.8f;

        /// <summary>
        ///     風鈴 1 打ち分のモノラルの音を作る
        /// </summary>
        /// <param name="fundamentalHz">基音。江戸風鈴はおおよそ 2〜3.5kHz</param>
        /// <param name="seed">打撃音のノイズの種。同じ値なら同じ音になる</param>
        public static float[] Synthesize(float fundamentalHz, int seed, float seconds = 3f)
        {
            var length = Mathf.Max(1, Mathf.RoundToInt(seconds * SampleRate));
            var samples = new float[length];
            var random = new System.Random(seed);
            var phases = new float[Ratios.Length * 2];
            for (var i = 0; i < phases.Length; i++) phases[i] = (float)(random.NextDouble() * Mathf.PI * 2f);

            var fadeStart = length - Mathf.RoundToInt(FadeOutSeconds * SampleRate);
            var noisePrev = 0f;
            for (var n = 0; n < length; n++)
            {
                var t = (float)n / SampleRate;
                var value = 0f;
                for (var m = 0; m < Ratios.Length; m++)
                {
                    var f = fundamentalHz * Ratios[m];
                    if (f >= SampleRate * 0.45f) continue;
                    var envelope = Amplitudes[m] * Mathf.Exp(-t / DecaySeconds[m]);
                    var split = BeatHz * (m + 1) * 0.5f;
                    value += envelope * 0.5f *
                             (Mathf.Sin(2f * Mathf.PI * (f - split) * t + phases[m * 2]) +
                              Mathf.Sin(2f * Mathf.PI * (f + split) * t + phases[m * 2 + 1]));
                }

                // 舌がガラスに当たる「チッ」という高い打撃音 (差分をとったノイズ)
                if (t < StrikeSeconds * 6f)
                {
                    var noise = (float)(random.NextDouble() * 2.0 - 1.0);
                    value += (noise - noisePrev) * 0.35f * Mathf.Exp(-t / StrikeSeconds);
                    noisePrev = noise;
                }

                // 立ち上がりのクリックを避ける 0.5ms のランプ
                value *= Mathf.Clamp01(t / 0.0005f);
                if (n >= fadeStart) value *= (float)(length - n) / (length - fadeStart);
                samples[n] = value;
            }

            Normalize(samples, Peak);
            return samples;
        }

        /// <summary>
        ///     基音を少しずつ変えた風鈴の音を作る
        /// </summary>
        public static AudioClip[] CreateClips(float baseHz = 2600f, int count = 3)
        {
            var clips = new AudioClip[count];
            for (var i = 0; i < count; i++)
            {
                // 同じ風鈴でも打つ位置で響き方が少し変わる
                var hz = baseHz * (1f + 0.025f * (i - (count - 1) * 0.5f));
                var data = Synthesize(hz, 1000 + i);
                var clip = AudioClip.Create($"WindChime_Synth_{i + 1}", data.Length, 1, SampleRate, false);
                clip.SetData(data, 0);
                clips[i] = clip;
            }

            return clips;
        }

        private static void Normalize(float[] samples, float peak)
        {
            var max = 0f;
            foreach (var s in samples) max = Mathf.Max(max, Mathf.Abs(s));
            if (max <= 0f) return;
            var gain = peak / max;
            for (var i = 0; i < samples.Length; i++) samples[i] *= gain;
        }
    }
}
