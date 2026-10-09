using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEngine;

namespace Features.Sound.Scripts.Editor
{
    // Split recordings at impacts. Playback speed is chosen by the emitter at runtime.
    public static class WindChimeRecordingBuilder
    {
        private const string Root = "Assets/Features/Sound/Clips/WindChimes/";
        private static readonly Queue<System.Action> Jobs = new();
        private static readonly List<string>[] Paths = { new(), new() };
        private static int _completed;

        public static int[] FindAttacks(float[] samples, int channels, int sampleRate)
        {
            int hop = Math.Max(1, sampleRate / 200);
            int frames = samples.Length / channels;
            var envelope = new float[(frames + hop - 1) / hop];
            for (int i = 0; i < envelope.Length; i++)
            {
                double sum = 0;
                int count = Math.Min(hop, frames - i * hop);
                for (int n = 0; n < count; n++)
                    for (int c = 0; c < channels; c++)
                    {
                        var value = samples[(i * hop + n) * channels + c];
                        sum += value * value;
                    }
                envelope[i] = (float)Math.Sqrt(sum / (count * channels));
            }
            float peak = envelope.Length > 0 ? envelope.Max() : 0f;
            if (peak < 0.0001f) return Array.Empty<int>();
            var candidates = new List<(int bin, float score)>();
            if (envelope[0] > peak * 0.14f) candidates.Add((0, envelope[0]));
            for (int i = 1; i < envelope.Length; i++)
            {
                float baseline = 0;
                int count = Math.Min(4, i);
                for (int j = i - count; j < i; j++) baseline += envelope[j];
                baseline /= count;
                float rise = envelope[i] - envelope[i - 1];
                if (rise > peak * 0.065f && envelope[i] > Math.Max(peak * 0.14f, baseline * 2.2f)
                    && envelope[i] > envelope[i - 1] * 1.6f)
                    candidates.Add((i, rise));
            }
            var chosen = new List<int>();
            int separation = Mathf.RoundToInt(sampleRate * 0.2f / hop);
            foreach (var candidate in candidates.OrderByDescending(c => c.score))
                if (chosen.All(bin => Math.Abs(bin - candidate.bin) > separation)) chosen.Add(candidate.bin);
            // At most 5 ms of pre-roll preserves the impact without leading silence.
            return chosen.OrderBy(bin => bin).Select(bin => Math.Max(0, (bin - 1) * hop)).ToArray();
        }

        public static string Begin()
        {
            if (Jobs.Count > 0) throw new InvalidOperationException("A recording bake is already running.");
            _completed = 0;
            foreach (var paths in Paths) paths.Clear();
            Directory.CreateDirectory(Root + "Attacks");
            var report = new List<string> { "source,start_seconds,end_seconds" };
            for (int sourceIndex = 1; sourceIndex <= 2; sourceIndex++)
            {
                var clip = AssetDatabase.LoadAssetAtPath<AudioClip>(Root + $"風鈴{sourceIndex}.mp3");
                var samples = new float[clip.samples * clip.channels];
                if (!clip.GetData(samples, 0)) throw new InvalidOperationException("Cannot decode " + clip.name);
                var attacks = FindAttacks(samples, clip.channels, clip.frequency);
                if (attacks.Length == 0) throw new InvalidOperationException("No attacks found in " + clip.name);
                for (int index = 0; index < attacks.Length; index++)
                {
                    int start = attacks[index];
                    int end = Math.Min(clip.samples, start + clip.frequency * 3);
                    if (index + 1 < attacks.Length) end = Math.Min(end, attacks[index + 1]);
                    if (end - start < clip.frequency / 10) continue;
                    var strike = new float[(end - start) * clip.channels];
                    Array.Copy(samples, start * clip.channels, strike, 0, strike.Length);
                    report.Add(FormattableString.Invariant($"Chime{sourceIndex},{(double)start / clip.frequency:F4},{(double)end / clip.frequency:F4}"));
                    int group = sourceIndex - 1;
                    var path = Root + $"Attacks/Chime{sourceIndex}_{index + 1:D3}.wav";
                    int channels = clip.channels, frequency = clip.frequency;
                    Paths[group].Add(path);
                    Jobs.Enqueue(() => WriteWave(path, strike, channels, frequency));
                }
            }
            File.WriteAllLines("Logs/wind-chime-attacks.csv", report);
            File.WriteAllText("Logs/wind-chime-bake-status.txt", "Running");
            EditorApplication.update -= Tick;
            EditorApplication.update += Tick;
            return $"Queued {Jobs.Count} snippets. Detected {Paths[0].Count} short-recording strikes and {Paths[1].Count} long-recording strikes.";
        }

        private static void Tick()
        {
            try
            {
                if (Jobs.Count > 0) { Jobs.Dequeue()(); _completed++; return; }
                EditorApplication.update -= Tick;
                AssetDatabase.Refresh();
                var shortClips = Paths[0].Select(path => AssetDatabase.LoadAssetAtPath<AudioClip>(path)).ToArray();
                foreach (var path in Paths.SelectMany(group => group))
                {
                    var importer = (AudioImporter)AssetImporter.GetAtPath(path);
                    var settings = importer.defaultSampleSettings;
                    settings.loadType = AudioClipLoadType.DecompressOnLoad;
                    importer.loadInBackground = false;
                    importer.defaultSampleSettings = settings;
                    importer.SaveAndReimport();
                }
                const string bankPath = "Assets/Features/Sound/Profiles/WindChime Recordings.asset";
                var bank = AssetDatabase.LoadAssetAtPath<WindChimeRecordingBank>(bankPath);
                if (!bank) { bank = ScriptableObject.CreateInstance<WindChimeRecordingBank>(); AssetDatabase.CreateAsset(bank, bankPath); }
                bank.shortStrikes = shortClips;
                bank.longStrikes = Paths[1].Select(path => AssetDatabase.LoadAssetAtPath<AudioClip>(path)).ToArray();
                EditorUtility.SetDirty(bank);
                var prefabPath = "Assets/Features/Sound/Prefabs/Wind Chime.prefab";
                var root = PrefabUtility.LoadPrefabContents(prefabPath);
                try
                {
                    using var settings = new SerializedObject(root.GetComponent<WindChimeSoundEmitter>());
                    settings.FindProperty("recordings").objectReferenceValue = bank;
                    settings.ApplyModifiedPropertiesWithoutUndo();
                    PrefabUtility.SaveAsPrefabAsset(root, prefabPath);
                }
                finally { PrefabUtility.UnloadPrefabContents(root); }
                AssetDatabase.SaveAssetIfDirty(bank);
                File.WriteAllText("Logs/wind-chime-bake-status.txt", $"Completed: {_completed} snippets; short attacks={Paths[0].Count}, long attacks={Paths[1].Count}");
            }
            catch (Exception error)
            {
                EditorApplication.update -= Tick;
                Jobs.Clear();
                File.WriteAllText("Logs/wind-chime-bake-status.txt", "Failed: " + error);
                Debug.LogException(error);
            }
        }

        private static void WriteWave(string path, float[] samples, int channels, int sampleRate)
        {
            using var writer = new BinaryWriter(File.Create(path));
            int bytes = samples.Length * 2;
            writer.Write(System.Text.Encoding.ASCII.GetBytes("RIFF")); writer.Write(36 + bytes);
            writer.Write(System.Text.Encoding.ASCII.GetBytes("WAVEfmt ")); writer.Write(16);
            writer.Write((short)1); writer.Write((short)channels); writer.Write(sampleRate);
            writer.Write(sampleRate * channels * 2); writer.Write((short)(channels * 2)); writer.Write((short)16);
            writer.Write(System.Text.Encoding.ASCII.GetBytes("data")); writer.Write(bytes);
            int frames = samples.Length / channels;
            int fadeIn = Math.Max(1, sampleRate / 1000), fadeOut = Math.Min(frames, sampleRate * 15 / 1000);
            for (int n = 0; n < frames; n++)
            {
                float gain = Math.Min(1f, (float)n / fadeIn) * Math.Min(1f, (float)(frames - 1 - n) / fadeOut);
                for (int c = 0; c < channels; c++) writer.Write((short)Mathf.RoundToInt(Mathf.Clamp(samples[n * channels + c] * gain, -1f, 1f) * 32767f));
            }
        }
    }
}
