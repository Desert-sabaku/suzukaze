using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.Audio;
using Object = UnityEngine.Object;
using Random = System.Random;

namespace Features.Sound.Scripts.Editor
{
    /// <summary>
    ///     夏の環境音のプロファイル・プレハブを作り、シーンに音源を配置する
    /// </summary>
    public static class SoundscapeBuilder
    {
        private const string Root = "Assets/Features/Sound";
        private const string ClipsDir = Root + "/Clips";
        private const string ProfilesDir = Root + "/Profiles";
        private const string PrefabsDir = Root + "/Prefabs";
        private const string MixerPath = Root + "/MainMixer.mixer";
        private const string SoundscapeName = "Soundscape";

        private static readonly Spec[] Specs = SummerSpecs().ToArray();

        [MenuItem("Tools/Sound/Create Missing Profiles And Prefabs")]
        public static void CreateProfilesAndPrefabs()
        {
            var mixer = AssetDatabase.LoadAssetAtPath<AudioMixer>(MixerPath);
            if (!mixer) throw new InvalidOperationException($"{MixerPath} が見つかりません。");

            Directory.CreateDirectory(ProfilesDir);
            Directory.CreateDirectory(PrefabsDir);

            foreach (var spec in Specs)
            {
                var profilePath = $"{ProfilesDir}/{spec.Name}.asset";
                var profile = AssetDatabase.LoadAssetAtPath<CreatureSoundProfile>(profilePath);
                if (!profile)
                {
                    profile = ScriptableObject.CreateInstance<CreatureSoundProfile>();
                    spec.Apply(profile, FindGroup(mixer, spec.Group), LoadClips(spec));
                    AssetDatabase.CreateAsset(profile, profilePath);
                    Debug.Log($"[Sound] プロファイルを作成しました: {profilePath}");
                }

                var prefabPath = $"{PrefabsDir}/{spec.Name}.prefab";
                if (AssetDatabase.LoadAssetAtPath<GameObject>(prefabPath)) continue;

                var go = new GameObject(spec.Name, typeof(AudioSource), typeof(CreatureSoundEmitter));
                CreatureSoundEmitter.Configure(go.GetComponent<AudioSource>(), profile);
                var serialized = new SerializedObject(go.GetComponent<CreatureSoundEmitter>());
                serialized.FindProperty("profile").objectReferenceValue = profile;
                serialized.ApplyModifiedPropertiesWithoutUndo();
                PrefabUtility.SaveAsPrefabAsset(go, prefabPath);
                Object.DestroyImmediate(go);
                Debug.Log($"[Sound] プレハブを作成しました: {prefabPath}");
            }

            AssetDatabase.SaveAssets();
        }

        [MenuItem("Tools/Sound/Build Soundscape In Active Scene")]
        public static void BuildActiveScene()
        {
            var scene = EditorSceneManager.GetActiveScene();
            var mixer = AssetDatabase.LoadAssetAtPath<AudioMixer>(MixerPath);
            var listener = FindListener();
            if (!listener) throw new InvalidOperationException("シーンにカメラ (AudioListener) が見つかりません。");

            var old = scene.GetRootGameObjects().FirstOrDefault(go => go.name == SoundscapeName);
            if (old) Undo.DestroyObjectImmediate(old);

            var root = new GameObject(SoundscapeName);
            Undo.RegisterCreatedObjectUndo(root, "Build Soundscape");
            var director = root.AddComponent<SoundscapeDirector>();
            var directorSo = new SerializedObject(director);
            directorSo.FindProperty("mixer").objectReferenceValue = mixer;
            directorSo.ApplyModifiedPropertiesWithoutUndo();

            var world = new World(listener.position, new Random(scene.name.GetHashCode()));
            var counts = new Dictionary<string, int>();
            foreach (var spec in Specs)
            {
                var prefab = AssetDatabase.LoadAssetAtPath<GameObject>($"{PrefabsDir}/{spec.Name}.prefab");
                if (!prefab)
                {
                    Debug.LogWarning($"[Sound] {spec.Name} のプレハブがありません。先にプロファイルとプレハブを作成してください。");
                    continue;
                }

                if (spec.NeedsWater && !world.HasWater) continue;

                var parent = GetOrCreateChild(root.transform, spec.Group);
                for (var i = 0; i < spec.Count; i++)
                {
                    if (!world.TryPlace(spec, out var position)) break;
                    var instance = (GameObject)PrefabUtility.InstantiatePrefab(prefab, parent);
                    instance.name = $"{spec.Name} ({i + 1})";
                    instance.transform.position = position;
                    counts[spec.Group] = counts.GetValueOrDefault(spec.Group) + 1;
                }
            }

            EditorSceneManager.MarkSceneDirty(scene);
            Debug.Log($"[Sound] {scene.name} に音源を配置しました: " +
                      string.Join(", ", counts.Select(kv => $"{kv.Key} {kv.Value}")) +
                      (world.HasWater ? $" (水面 y={world.WaterLevel:0.0}, 岸 {world.ShoreCount} 点)" : ""));
        }

        private static Transform FindListener()
        {
            var listener = Object.FindAnyObjectByType<AudioListener>();
            if (listener) return listener.transform;
            var camera = Camera.main ? Camera.main : Object.FindAnyObjectByType<Camera>();
            if (!camera) return null;
            Undo.AddComponent<AudioListener>(camera.gameObject);
            return camera.transform;
        }

        private static Transform GetOrCreateChild(Transform parent, string name)
        {
            var child = parent.Find(name);
            if (child) return child;
            child = new GameObject(name).transform;
            child.SetParent(parent, false);
            return child;
        }

        private static AudioMixerGroup FindGroup(AudioMixer mixer, string name)
        {
            var group = mixer.FindMatchingGroups(name).FirstOrDefault(g => g.name == name);
            if (!group) Debug.LogWarning($"[Sound] Mixer に {name} グループがありません。");
            return group;
        }

        private static AudioClip[] LoadClips(Spec spec)
        {
            return spec.Clips.Select(file =>
            {
                var path = $"{ClipsDir}/{spec.Group}/{file}.wav";
                var clip = AssetDatabase.LoadAssetAtPath<AudioClip>(path);
                if (!clip) Debug.LogWarning($"[Sound] {path} が見つかりません。");
                return clip;
            }).Where(c => c).ToArray();
        }

        #region 種類ごとの設定

        /// <summary>
        ///     夏の日本の里山・海辺で聞こえる生き物と環境音。時刻は 24 を超えて書くと翌日に回り込む
        /// </summary>
        private static IEnumerable<Spec> SummerSpecs()
        {
            // 蝉: 声が大きく遠くまで届く。種類ごとに鳴く時間帯がはっきり分かれる
            Spec Cicada(string name, params Window[] windows)
            {
                return new Spec(name, "Cicadas", CreatureSoundProfile.PlaybackMode.Call, windows)
                {
                    Volume = 0.9f, MinDistance = 3f, MaxDistance = 140f,
                    Placement = Placement.TreeTrunk, Height = new Vector2(2f, 6f), Distance = new Vector2(10f, 55f)
                };
            }

            yield return Cicada("Cicada_Kumazemi", new Window(5.5f, 7f, 10f, 12f)) with
            {
                Count = 3, Rest = new Vector2(4f, 12f)
            };
            yield return Cicada("Cicada_Minminzemi", new Window(7.5f, 9f, 13f, 15.5f)) with
            {
                Count = 4, Rest = new Vector2(5f, 15f)
            };
            yield return Cicada("Cicada_Aburazemi", new Window(8.5f, 11f, 16.5f, 18.5f)) with
            {
                Count = 5, Rest = new Vector2(2f, 8f)
            };
            yield return Cicada("Cicada_Niiniizemi", new Window(5f, 6.5f, 16f, 18f, 0.6f)) with
            {
                Count = 2, Rest = new Vector2(3f, 10f)
            };
            yield return Cicada("Cicada_Tsukutsukuboushi", new Window(12f, 14f, 16.5f, 18f)) with
            {
                Count = 2, Rest = new Vector2(10f, 30f)
            };
            // ヒグラシは夜明け前と日暮れに林の奥で鳴き交わす
            yield return Cicada("Cicada_Higurashi",
                new Window(3.8f, 4.3f, 5f, 5.8f), new Window(16.8f, 17.6f, 18.6f, 19.4f)) with
            {
                Count = 4, Rest = new Vector2(4f, 14f), Distance = new Vector2(20f, 70f)
            };

            // 夜の虫: 草むらや木の上で鳴き続け、ときどき休む
            Spec NightInsect(string name, Window window)
            {
                return new Spec(name, "Insects", CreatureSoundProfile.PlaybackMode.Loop, new[] { window })
                {
                    Volume = 0.6f, MinDistance = 1f, MaxDistance = 45f, ActivitySmoothing = 6f,
                    Placement = Placement.Ground, Height = new Vector2(0.1f, 0.4f), Distance = new Vector2(3f, 25f)
                };
            }

            yield return NightInsect("Insect_Enmakorogi", new Window(18.5f, 19.5f, 28.5f, 29.5f)) with
            {
                Count = 4, Sing = new Vector2(20f, 90f), Pause = new Vector2(3f, 15f)
            };
            yield return NightInsect("Insect_Mitsukadokorogi", new Window(19f, 20f, 27f, 28.5f)) with
            {
                Count = 3, Sing = new Vector2(15f, 60f), Pause = new Vector2(5f, 20f), Distance = new Vector2(4f, 30f)
            };
            yield return NightInsect("Insect_Aomatsumushi", new Window(18.5f, 19.5f, 26f, 28f)) with
            {
                Count = 4, Volume = 0.55f, MinDistance = 1.5f, MaxDistance = 60f,
                Sing = new Vector2(30f, 120f), Pause = new Vector2(2f, 8f),
                Placement = Placement.TreeCanopy, Height = new Vector2(3f, 8f), Distance = new Vector2(8f, 40f)
            };
            yield return NightInsect("Insect_Kubikirigisu", new Window(19f, 20f, 26f, 27.5f)) with
            {
                Count = 2, Volume = 0.5f, Sing = new Vector2(30f, 120f), Pause = new Vector2(5f, 30f),
                Distance = new Vector2(6f, 30f)
            };
            // 遠くの草むら一面から聞こえる虫の声
            yield return new Spec("Insect_NightChorus", "Insects", CreatureSoundProfile.PlaybackMode.Loop,
                new[] { new Window(18.8f, 20f, 28f, 29f) })
            {
                Clips = new[] { "Insect_NightChorusBed" }, Count = 1, Volume = 0.22f, SpatialBlend = 0f,
                ActivitySmoothing = 8f, Placement = Placement.AtListener
            };

            // 鳥: 夜明けから午前中が最も賑やか。遠くの梢で鳴く
            Spec Bird(string name, params Window[] windows)
            {
                return new Spec(name, "Birds", CreatureSoundProfile.PlaybackMode.Call, windows)
                {
                    Volume = 0.75f, MinDistance = 2f, MaxDistance = 130f, Count = 1, Rest = new Vector2(15f, 45f),
                    Placement = Placement.TreeCanopy, Height = new Vector2(6f, 14f), Distance = new Vector2(15f, 80f)
                };
            }

            yield return Bird("Bird_Hiyodori", new Window(4.8f, 5.5f, 10f, 12f), new Window(12f, 13f, 15f, 17f, 0.5f)) with
            {
                Clips = new[] { "Bird_Hiyodori1", "Bird_Hiyodori2" }, Count = 3
            };
            yield return Bird("Bird_Kijibato", new Window(4.5f, 5.5f, 8.5f, 11f), new Window(14f, 15f, 16.5f, 18f, 0.4f)) with
            {
                Count = 2, Rest = new Vector2(8f, 25f)
            };
            yield return Bird("Bird_Uguisu", new Window(4.2f, 5f, 9f, 11.5f), new Window(11.5f, 12f, 15f, 17f, 0.5f)) with
            {
                Count = 2, Rest = new Vector2(6f, 20f)
            };
            yield return Bird("Bird_Shijukara", new Window(5f, 6f, 10f, 13f), new Window(13f, 14f, 16f, 17.5f, 0.5f)) with
            {
                Count = 2, Rest = new Vector2(10f, 30f)
            };
            yield return Bird("Bird_Yamagara", new Window(5.5f, 6.5f, 10f, 12f));
            yield return Bird("Bird_Mejiro", new Window(5f, 6f, 11f, 14f)) with
            {
                Count = 2, Rest = new Vector2(10f, 30f), Distance = new Vector2(10f, 40f)
            };
            yield return Bird("Bird_Gabichou", new Window(4.8f, 5.5f, 9f, 11f), new Window(15f, 16f, 17.5f, 18.5f, 0.6f)) with
            {
                Rest = new Vector2(20f, 50f)
            };
            yield return Bird("Bird_Kakkou", new Window(4f, 4.8f, 8f, 10f)) with
            {
                Distance = new Vector2(40f, 110f)
            };
            // ホトトギスは夜にも鳴く。トラツグミは真夜中に細く鳴く
            yield return Bird("Bird_Hototogisu", new Window(21f, 23f, 28f, 29.5f), new Window(9f, 10f, 15f, 16f, 0.25f)) with
            {
                Rest = new Vector2(20f, 60f), Distance = new Vector2(40f, 110f)
            };
            yield return Bird("Bird_Toratsugumi", new Window(21.5f, 23f, 27f, 28.5f)) with
            {
                Rest = new Vector2(15f, 45f), Distance = new Vector2(40f, 100f)
            };
            // カラスは朝夕のねぐら入り・ねぐら立ちで騒がしく、数回続けて鳴く
            yield return Bird("Bird_Karasu",
                new Window(4.3f, 5f, 6.5f, 8f), new Window(8f, 9f, 15f, 16f, 0.35f), new Window(16f, 17f, 18.5f, 19.2f)) with
            {
                Clips = new[] { "Bird_Karasu1", "Bird_Karasu2", "Bird_Karasu3" }, Count = 2,
                Rest = new Vector2(20f, 60f), CallsPerBout = new Vector2Int(2, 4), GapInBout = new Vector2(0.5f, 1.2f),
                Distance = new Vector2(30f, 110f), Height = new Vector2(8f, 20f)
            };
            yield return Bird("Bird_Umineko", new Window(5f, 6f, 17f, 18.5f)) with
            {
                Count = 3, Rest = new Vector2(8f, 25f), NeedsWater = true,
                Placement = Placement.Shore, Height = new Vector2(3f, 12f), Distance = new Vector2(20f, 90f)
            };

            // 環境音: 波は岸に沿って置き、葉擦れは全体に薄く流す
            var allDay = new Window(-1f, 0f, 24f, 25f);
            yield return new Spec("Ambience_Wave_Gentle", "Ambient", CreatureSoundProfile.PlaybackMode.Loop, new[] { allDay })
            {
                Count = 3, Volume = 0.8f, MinDistance = 6f, MaxDistance = 120f, Spread = 120f, Priority = 32,
                NeedsWater = true, Placement = Placement.Shore, Height = new Vector2(0.3f, 0.6f),
                Distance = new Vector2(0f, 60f)
            };
            yield return new Spec("Ambience_Wave_Calm", "Ambient", CreatureSoundProfile.PlaybackMode.Loop, new[] { allDay })
            {
                Count = 2, Volume = 0.6f, MinDistance = 12f, MaxDistance = 220f, Spread = 160f, Priority = 32,
                NeedsWater = true, Placement = Placement.Shore, Height = new Vector2(0.3f, 0.6f),
                Distance = new Vector2(40f, 150f)
            };
            // 葉擦れは日中の海風でやや強くなる。風そのものの音 (Ambience_WindBed) は今は使わない
            var breeze = new[] { new Window(-1f, 0f, 24f, 25f, 0.6f), new Window(8f, 11f, 16f, 19f) };
            yield return new Spec("Ambience_PlantsSwayingBed", "Ambient", CreatureSoundProfile.PlaybackMode.Loop, breeze)
            {
                Count = 1, Volume = 0.3f, SpatialBlend = 0f, ModulationDepth = 0.6f, ModulationPeriod = 6f,
                Priority = 32, Placement = Placement.AtListener
            };
        }

        #endregion

        #region 型

        private enum Placement
        {
            TreeTrunk,
            TreeCanopy,
            Ground,
            Shore,
            AtListener
        }

        /// <summary>
        ///     活動する時間帯。start〜fullStart で鳴き始め、fullEnd〜end で鳴き止む台形
        /// </summary>
        private readonly struct Window
        {
            private readonly float _start, _fullStart, _fullEnd, _end, _level;

            public Window(float start, float fullStart, float fullEnd, float end, float level = 1f)
            {
                (_start, _fullStart, _fullEnd, _end, _level) = (start, fullStart, fullEnd, end, level);
            }

            public IEnumerable<float> Corners => new[] { _start, _fullStart, _fullEnd, _end };

            public float Evaluate(float hour)
            {
                // 24 時をまたぐ窓にも対応するため、前後の日も見る
                return Mathf.Max(Trapezoid(hour - 24f), Trapezoid(hour), Trapezoid(hour + 24f));
            }

            private float Trapezoid(float h)
            {
                if (h <= _start || h >= _end) return 0f;
                if (h < _fullStart) return _level * Mathf.InverseLerp(_start, _fullStart, h);
                if (h > _fullEnd) return _level * Mathf.InverseLerp(_end, _fullEnd, h);
                return _level;
            }
        }

        private sealed record Spec(
            string Name,
            string Group,
            CreatureSoundProfile.PlaybackMode Mode,
            Window[] Windows)
        {
            public string[] Clips { get; init; } = { Name };
            public int Count { get; init; } = 1;
            public float Volume { get; init; } = 1f;
            public float ActivitySmoothing { get; init; } = 3f;
            public float SpatialBlend { get; init; } = 1f;
            public float MinDistance { get; init; } = 2f;
            public float MaxDistance { get; init; } = 80f;
            public float Spread { get; init; }
            public int Priority { get; init; } = 128;
            public Vector2 Rest { get; init; } = new(5f, 15f);
            public Vector2Int CallsPerBout { get; init; } = new(1, 1);
            public Vector2 GapInBout { get; init; } = new(0.3f, 0.8f);
            public Vector2 Sing { get; init; } = new(20f, 60f);
            public Vector2 Pause { get; init; } = Vector2.zero;
            public float ModulationDepth { get; init; }
            public float ModulationPeriod { get; init; } = 8f;
            public bool NeedsWater { get; init; }
            public Placement Placement { get; init; } = Placement.AtListener;
            public Vector2 Height { get; init; }
            public Vector2 Distance { get; init; } = new(5f, 40f);

            public void Apply(CreatureSoundProfile profile, AudioMixerGroup output, AudioClip[] clips)
            {
                profile.clips = clips;
                profile.output = output;
                profile.mode = Mode;
                profile.volume = Volume;
                profile.activityByHour = ActivityCurve();
                profile.activitySmoothing = ActivitySmoothing;
                profile.restSeconds = Rest;
                profile.callsPerBout = CallsPerBout;
                profile.gapInBoutSeconds = GapInBout;
                profile.singSeconds = Sing;
                profile.pauseSeconds = Pause;
                profile.modulationDepth = ModulationDepth;
                profile.modulationPeriod = ModulationPeriod;
                profile.spatialBlend = SpatialBlend;
                profile.minDistance = MinDistance;
                profile.maxDistance = MaxDistance;
                profile.spread = Spread;
                profile.airAbsorption = SpatialBlend > 0f;
                profile.priority = Priority;
            }

            private AnimationCurve ActivityCurve()
            {
                float Evaluate(float h)
                {
                    return Windows.Max(w => w.Evaluate(h));
                }

                var times = Windows.SelectMany(w => w.Corners)
                    .Select(t => Mathf.Repeat(t, 24f))
                    .Append(0f).Append(24f)
                    .Select(t => Mathf.Round(t * 100f) / 100f)
                    .Distinct().OrderBy(t => t).ToArray();

                var curve = new AnimationCurve(times.Select(t => new Keyframe(t, Evaluate(t))).ToArray());
                for (var i = 0; i < curve.length; i++)
                {
                    AnimationUtility.SetKeyLeftTangentMode(curve, i, AnimationUtility.TangentMode.Linear);
                    AnimationUtility.SetKeyRightTangentMode(curve, i, AnimationUtility.TangentMode.Linear);
                }

                return curve;
            }
        }

        /// <summary>
        ///     配置先を探すためのシーンの情報 (聞く位置・木・地面・岸)
        /// </summary>
        private sealed class World
        {
            private const float ShoreSpacing = 18f;
            private readonly Vector3 _listener;
            private readonly Random _random;
            private readonly List<Vector3> _shore = new();
            private readonly Terrain _terrain;
            private readonly List<Vector3> _trees = new();
            private readonly HashSet<int> _usedTrees = new();
            private readonly List<Vector3> _usedShore = new();

            public World(Vector3 listener, Random random)
            {
                _listener = listener;
                _random = random;
                _terrain = Terrain.activeTerrains.OrderBy(t => DistanceToTerrain(t, listener)).FirstOrDefault();
                if (_terrain) CollectTrees(_terrain);

                // 水面は名前に Water / Sea / Ocean を含む中で最も広いレンダラーとする
                var water = Object.FindObjectsByType<Renderer>(FindObjectsInactive.Exclude)
                    .Where(r => new[] { "Water", "Sea", "Ocean" }.Any(r.name.Contains))
                    .OrderByDescending(r => r.bounds.size.x * r.bounds.size.z)
                    .FirstOrDefault();
                if (water)
                {
                    HasWater = true;
                    WaterLevel = water.bounds.max.y;
                    CollectShore();
                }
            }

            public bool HasWater { get; }
            public float WaterLevel { get; }
            public int ShoreCount => _shore.Count;

            public bool TryPlace(Spec spec, out Vector3 position)
            {
                var height = Range(spec.Height);
                switch (spec.Placement)
                {
                    case Placement.AtListener:
                        position = _listener;
                        return true;

                    case Placement.TreeTrunk:
                    case Placement.TreeCanopy:
                        if (TryPickTree(spec.Distance, out var tree))
                        {
                            position = tree + Vector3.up * height;
                            return true;
                        }

                        return TryPlaceOnGround(spec.Distance, height, out position);

                    case Placement.Ground:
                        return TryPlaceOnGround(spec.Distance, height, out position);

                    case Placement.Shore:
                        if (TryPickShore(spec.Distance, out var shore))
                        {
                            position = shore + Vector3.up * height;
                            return true;
                        }

                        position = default;
                        return false;

                    default:
                        throw new ArgumentOutOfRangeException();
                }
            }

            private bool TryPickTree(Vector2 distance, out Vector3 tree)
            {
                var candidates = Enumerable.Range(0, _trees.Count)
                    .Where(i => !_usedTrees.Contains(i) && InRange(_trees[i], distance))
                    .ToArray();
                if (candidates.Length == 0)
                {
                    tree = default;
                    return false;
                }

                var index = candidates[_random.Next(candidates.Length)];
                _usedTrees.Add(index);
                tree = _trees[index];
                return true;
            }

            private bool TryPickShore(Vector2 distance, out Vector3 shore)
            {
                var candidates = _shore
                    .Where(p => InRange(p, distance) && _usedShore.All(u => Flat(u - p).magnitude >= ShoreSpacing))
                    .ToArray();
                if (candidates.Length == 0)
                {
                    shore = default;
                    return false;
                }

                shore = candidates[_random.Next(candidates.Length)];
                _usedShore.Add(shore);
                return true;
            }

            private bool TryPlaceOnGround(Vector2 distance, float height, out Vector3 position)
            {
                for (var attempt = 0; attempt < 50; attempt++)
                {
                    var angle = (float)(_random.NextDouble() * Math.PI * 2);
                    var r = Range(distance);
                    var p = _listener + new Vector3(Mathf.Cos(angle), 0f, Mathf.Sin(angle)) * r;
                    if (!TryGround(p, out var ground)) continue;
                    if (HasWater && ground < WaterLevel + 0.3f) continue;
                    position = new Vector3(p.x, ground + height, p.z);
                    return true;
                }

                position = default;
                return false;
            }

            private bool TryGround(Vector3 p, out float y)
            {
                if (_terrain && Contains(_terrain, p))
                {
                    y = _terrain.SampleHeight(p) + _terrain.transform.position.y;
                    return true;
                }

                if (Physics.Raycast(p + Vector3.up * 500f, Vector3.down, out var hit, 1000f))
                {
                    y = hit.point.y;
                    return true;
                }

                // 地面が無いシーン (タイトルなど) はカメラの高さを目線とみなす
                y = _listener.y - 1.6f;
                return !_terrain;
            }

            private void CollectTrees(Terrain terrain)
            {
                var data = terrain.terrainData;
                var origin = terrain.transform.position;
                foreach (var tree in data.treeInstances)
                {
                    var p = origin + Vector3.Scale(tree.position, data.size);
                    if (Flat(p - _listener).magnitude <= 200f) _trees.Add(p);
                }
            }

            /// <summary>
            ///     陸地のうち、隣に水面より低い地点がある所を岸とする
            /// </summary>
            private void CollectShore()
            {
                if (!_terrain) return;
                const float step = 3f;
                const float radius = 180f;
                for (var x = -radius; x <= radius; x += step)
                for (var z = -radius; z <= radius; z += step)
                {
                    var p = _listener + new Vector3(x, 0f, z);
                    if (!Contains(_terrain, p)) continue;
                    var ground = Height(p);
                    if (ground < WaterLevel || ground > WaterLevel + 1.5f) continue;

                    var nearWater = new[] { Vector3.forward, Vector3.back, Vector3.left, Vector3.right }
                        .Any(d => Contains(_terrain, p + d * step) && Height(p + d * step) < WaterLevel);
                    if (nearWater) _shore.Add(new Vector3(p.x, WaterLevel, p.z));
                }
            }

            private float Height(Vector3 p)
            {
                return _terrain.SampleHeight(p) + _terrain.transform.position.y;
            }

            private bool InRange(Vector3 p, Vector2 distance)
            {
                var d = Flat(p - _listener).magnitude;
                return d >= distance.x && d <= distance.y;
            }

            private float Range(Vector2 range)
            {
                return Mathf.Lerp(range.x, range.y, (float)_random.NextDouble());
            }

            private static Vector3 Flat(Vector3 v)
            {
                return new Vector3(v.x, 0f, v.z);
            }

            private static bool Contains(Terrain terrain, Vector3 p)
            {
                var origin = terrain.transform.position;
                var size = terrain.terrainData.size;
                return p.x >= origin.x && p.x <= origin.x + size.x && p.z >= origin.z && p.z <= origin.z + size.z;
            }

            private static float DistanceToTerrain(Terrain terrain, Vector3 p)
            {
                var origin = terrain.transform.position;
                var size = terrain.terrainData.size;
                var center = origin + size * 0.5f;
                return Flat(center - p).magnitude;
            }
        }

        #endregion
    }
}

namespace System.Runtime.CompilerServices
{
    // Unity の .NET プロファイルには無いため、record の init アクセサ用に定義する
    internal static class IsExternalInit
    {
    }
}
