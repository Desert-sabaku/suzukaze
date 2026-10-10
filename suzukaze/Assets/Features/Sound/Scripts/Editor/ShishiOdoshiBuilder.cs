using System;
using System.Linq;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.Audio;
using Object = UnityEngine.Object;

namespace Features.Sound.Scripts.Editor
{
    /// <summary>
    ///     ししおどしのプレハブを作り、夕涼みのある各シーンの Soundscape の下に置く
    /// </summary>
    public static class ShishiOdoshiBuilder
    {
        private const string PrefabPath = "Assets/Features/Sound/Prefabs/Shishi Odoshi.prefab";
        private const string ClipPath = "Assets/Features/Sound/Clips/Yusuzumi/ShishiOdoshi.wav";
        private const string MixerPath = "Assets/Features/Sound/MainMixer.mixer";
        private const string OutputGroup = "Ambient";

        [MenuItem("Tools/Sound/Place Shishi Odoshi In Yusuzumi Scenes")]
        public static void PlaceInYusuzumiScenes()
        {
            var prefab = GetOrCreatePrefab();
            var scenePaths = AssetDatabase.FindAssets("t:Scene", new[] { "Assets/Projects/Scenes" })
                .Select(AssetDatabase.GUIDToAssetPath).ToArray();
            foreach (var path in scenePaths)
            {
                var scene = EditorSceneManager.OpenScene(path, OpenSceneMode.Single);
                var director = Object.FindAnyObjectByType<YusuzumiSoundDirector>(FindObjectsInactive.Include);
                if (!director || director.gameObject.scene != scene) continue;
                if (Place(prefab, director.transform)) EditorSceneManager.SaveScene(scene);
            }
        }

        /// <summary>
        ///     Soundscape の下にししおどしを 1 つ置く。すでにあれば何もしない
        /// </summary>
        /// <returns>新しく置いた場合は true</returns>
        public static bool Place(GameObject prefab, Transform soundscape)
        {
            if (soundscape.GetComponentInChildren<ShishiOdoshiSoundEmitter>(true)) return false;
            var instance = (GameObject)PrefabUtility.InstantiatePrefab(prefab, soundscape);
            Undo.RegisterCreatedObjectUndo(instance, "Place Shishi Odoshi");
            Debug.Log($"[Sound] {soundscape.gameObject.scene.name} にししおどしを置きました");
            return true;
        }

        public static GameObject GetOrCreatePrefab()
        {
            var existing = AssetDatabase.LoadAssetAtPath<GameObject>(PrefabPath);
            if (existing) return existing;

            var clip = AssetDatabase.LoadAssetAtPath<AudioClip>(ClipPath);
            if (!clip) throw new InvalidOperationException($"{ClipPath} が見つかりません。");
            var mixer = AssetDatabase.LoadAssetAtPath<AudioMixer>(MixerPath);
            var group = mixer ? mixer.FindMatchingGroups(OutputGroup).FirstOrDefault(g => g.name == OutputGroup) : null;
            if (!group) Debug.LogWarning($"[Sound] Mixer に {OutputGroup} グループがありません。");

            var go = new GameObject("Shishi Odoshi", typeof(AudioSource), typeof(AudioReverbFilter),
                typeof(ShishiOdoshiSoundEmitter));
            // 庭の奥から届くよう 3D で鳴らす。夕涼みで持ち上がる環境音 (Ambient) に混ぜる
            var source = go.GetComponent<AudioSource>();
            source.outputAudioMixerGroup = group;
            source.playOnAwake = false;
            source.spatialBlend = 1f;
            source.rolloffMode = AudioRolloffMode.Logarithmic;
            source.minDistance = 3f;
            source.maxDistance = 40f;
            source.dopplerLevel = 0f;
            source.priority = 64;

            // 静かな庭に響いて消えていく余韻。Ambient には残響の送りがないため、音源に付ける
            var reverb = go.GetComponent<AudioReverbFilter>();
            reverb.reverbPreset = AudioReverbPreset.User;
            reverb.dryLevel = 0f;
            reverb.room = -1200f;
            reverb.roomHF = -600f;
            reverb.decayTime = 1.8f;
            reverb.decayHFRatio = 0.5f;
            reverb.reflectionsLevel = -1000f;
            reverb.reflectionsDelay = 0.02f;
            reverb.reverbLevel = -800f;
            reverb.reverbDelay = 0.04f;

            using (var emitter = new SerializedObject(go.GetComponent<ShishiOdoshiSoundEmitter>()))
            {
                emitter.FindProperty("clip").objectReferenceValue = clip;
                emitter.ApplyModifiedPropertiesWithoutUndo();
            }

            var prefab = PrefabUtility.SaveAsPrefabAsset(go, PrefabPath);
            Object.DestroyImmediate(go);
            Debug.Log($"[Sound] プレハブを作成しました: {PrefabPath}");
            return prefab;
        }
    }
}
