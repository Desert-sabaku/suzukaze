using System;
using System.Reflection;
using System.Linq;
using NUnit.Framework;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;
using Object = UnityEngine.Object;

namespace Suzukaze.Gesture.Tests
{
    public class WindChimeTests
    {
        private const BindingFlags PrivateInstance = BindingFlags.Instance | BindingFlags.NonPublic;
        private GameObject _owner;
        private GameObject _sourceOwner;
        private Component _director;
        private AudioClip _clip;

        [SetUp]
        public void SetUp()
        {
            _owner = new GameObject("Wind chime test");
            _owner.SetActive(false);
            var type = Type.GetType("Features.Sound.Scripts.WindChimeSoundEmitter, Assembly-CSharp");
            Assert.That(type, Is.Not.Null);
            _director = _owner.AddComponent(type);
            _clip = AudioClip.Create("Test strike", 128, 1, 48000, false);
            Set("_clips", new[] { _clip });
            Set("windChimeClips", new[] { _clip });
            _sourceOwner = new GameObject("Test audio source");
            Set("_windChime", _sourceOwner.AddComponent<AudioSource>());
            Set("strikesPerGust", new Vector2Int(3, 3));
            Set("_nextGustTime", float.NegativeInfinity);
        }

        [TearDown]
        public void TearDown()
        {
            if (_director) Set("_windChime", null);
            Object.DestroyImmediate(_owner);
            Object.DestroyImmediate(_sourceOwner);
            if (_clip) Object.DestroyImmediate(_clip);
        }

        [TestCase(0f)]
        [TestCase(0.34f)]
        [TestCase(0.35f)]
        public void WeakWindDoesNotStartStrikes(float power)
        {
            Tick(power);
            Assert.That(Get<int>("_strikesRemaining"), Is.Zero);
            Assert.That(Get<float>("_nextGustTime"), Is.EqualTo(float.NegativeInfinity));
        }

        [Test]
        public void StrongWindStartsStrikesWithoutRelaxationAndHonorsInterval()
        {
            Tick(0.36f);
            Assert.That(Get<int>("_strikesRemaining"), Is.EqualTo(2));
            Assert.That(Get<float>("_nextGustTime"), Is.GreaterThan(Time.time));

            Set("_strikesRemaining", 0);
            Tick(0.6f);
            Assert.That(Get<int>("_strikesRemaining"), Is.Zero);
        }

        [Test]
        public void WindDroppingToThresholdCancelsPendingStrikes()
        {
            Tick(0.6f);
            Set("_nextStrikeTime", float.NegativeInfinity);
            Tick(0.35f);
            Assert.That(Get<int>("_strikesRemaining"), Is.Zero);
        }

        [Test]
        public void PendingStrikeWaitsEvenIfGustIntervalHasElapsed()
        {
            Set("_strikesRemaining", 2);
            Set("_nextStrikeTime", float.PositiveInfinity);
            Tick(0.6f);
            Assert.That(Get<int>("_strikesRemaining"), Is.EqualTo(2));
            Assert.That(Get<float>("_nextGustTime"), Is.EqualTo(float.NegativeInfinity));
        }

        [Test]
        public void MissingWindSourceCancelsStrikes()
        {
            Set("_strikesRemaining", 2);
            _director.GetType().GetMethod("LateUpdate", PrivateInstance).Invoke(_director, null);
            Assert.That(Get<int>("_strikesRemaining"), Is.Zero);
        }

        [Test]
        public void StrongWindIncreasesAverageStrikeCountAndFrequencyButKeepsRandomness()
        {
            Set("strikesPerGust", new Vector2Int(1, 3));
            var randomState = UnityEngine.Random.state;
            try
            {
                var weak = SampleGusts(0.36f);
                var strong = SampleGusts(1f);
                Assert.That(strong.Item1.Average(), Is.GreaterThan(weak.Item1.Average()));
                Assert.That(strong.Item2.Average(), Is.LessThan(weak.Item2.Average() * 0.6));
                Assert.That(weak.Item1.Distinct().Count(), Is.GreaterThan(1));
                Assert.That(strong.Item1.Distinct().Count(), Is.GreaterThan(1));
                Assert.That(strong.Item2.Distinct().Count(), Is.GreaterThan(1));
                Assert.That(strong.Item1.Min(), Is.EqualTo(1));
                Assert.That(strong.Item1.Max(), Is.EqualTo(6));
                Assert.That(_sourceOwner.GetComponent<AudioSource>().pitch, Is.EqualTo(1f));
            }
            finally { UnityEngine.Random.state = randomState; }
        }

        private Tuple<int[], float[]> SampleGusts(float power)
        {
            UnityEngine.Random.InitState(2718);
            var counts = new int[200];
            var intervals = new float[200];
            for (int i = 0; i < counts.Length; i++)
            {
                Set("_strikesRemaining", 0);
                Set("_nextGustTime", float.NegativeInfinity);
                Tick(power);
                counts[i] = Get<int>("_strikesRemaining") + 1;
                intervals[i] = Get<float>("_nextGustTime") - Time.time;
            }
            return Tuple.Create(counts, intervals);
        }

        [TestCase(0.94f)]
        [TestCase(1.06f)]
        public void SpeedChangesDurationWithoutChangingPitchOrStereoPhase(float speed)
        {
            const int sampleRate = 48000;
            const int frames = 24000;
            const float frequency = 440f;
            var input = new float[frames * 2];
            for (int n = 0; n < frames; n++)
            {
                input[n * 2] = Mathf.Sin(2f * Mathf.PI * frequency * n / sampleRate);
                input[n * 2 + 1] = -0.5f * input[n * 2];
            }
            var type = Type.GetType("Features.Sound.Scripts.PitchPreservingTimeStretch, Assembly-CSharp");
            var output = (float[])type.GetMethod("Stretch").Invoke(null, new object[] { input, 2, sampleRate, speed });
            Assert.That(output.Length / 2, Is.EqualTo(Mathf.RoundToInt(frames / speed)));
            int start = sampleRate / 20;
            int end = output.Length / 2 - sampleRate / 20;
            int crossings = 0;
            for (int n = start + 1; n < end; n++)
            {
                if (output[(n - 1) * 2] <= 0f && output[n * 2] > 0f) crossings++;
                Assert.That(output[n * 2 + 1], Is.EqualTo(-0.5f * output[n * 2]).Within(0.00001f));
            }
            float measuredHz = (float)crossings * sampleRate / (end - start);
            Assert.That(measuredHz, Is.EqualTo(frequency).Within(4f));
            for (int n = 0; n < 64; n++) Assert.That(output[n], Is.EqualTo(input[n]));
        }

        [Test]
        public void AttackDetectorFindsImpactsInsteadOfSplittingAtFixedIntervals()
        {
            const int rate = 8000;
            var samples = new float[rate * 2];
            var impacts = new[] { 0.1f, 0.65f, 1.15f };
            for (int n = 0; n < samples.Length; n++)
                foreach (float impact in impacts)
                {
                    float time = (float)n / rate - impact;
                    if (time >= 0f) samples[n] += Mathf.Exp(-time / 0.15f) * Mathf.Sin(2f * Mathf.PI * 600f * time);
                }
            var type = Type.GetType("Features.Sound.Scripts.Editor.WindChimeRecordingBuilder, Assembly-CSharp-Editor");
            var method = type.GetMethod("FindAttacks");
            var attacks = (int[])method.Invoke(null, new object[] { samples, 1, rate });
            Assert.That(attacks, Has.Length.EqualTo(3));
            for (int i = 0; i < impacts.Length; i++)
                Assert.That((float)attacks[i] / rate, Is.EqualTo(impacts[i]).Within(0.01f));
            Assert.That((int[])method.Invoke(null, new object[] { new float[rate], 1, rate }), Is.Empty);
        }

        [Test]
        public void StrongWindPrefersLongRecordingAndFasterVariants()
        {
            var type = Type.GetType("Features.Sound.Scripts.WindChimeRecordingBank, Assembly-CSharp");
            var bank = ScriptableObject.CreateInstance(type);
            var longClips = new[] { _clip };
            type.GetField("longStrikes").SetValue(bank, longClips);
            Set("recordings", bank);
            var state = UnityEngine.Random.state;
            try
            {
                var method = _director.GetType().GetMethod("SelectRecordedPool", PrivateInstance);
                int weakLong = 0, strongLong = 0; var weakSpeeds = new float[500]; var strongSpeeds = new float[500]; var speedMethod = _director.GetType().GetMethod("SelectPlaybackSpeed", PrivateInstance);
                UnityEngine.Random.InitState(718);
                for (int i = 0; i < 500; i++)
                {
                    var weak = (AudioClip[])method.Invoke(_director, new object[] { 0f });
                    var strong = (AudioClip[])method.Invoke(_director, new object[] { 1f });
                    if (weak != null) weakLong++;
                    if (strong != null) strongLong++;
                    weakSpeeds[i] = (float)speedMethod.Invoke(_director, new object[] { 0f, true });
                    strongSpeeds[i] = (float)speedMethod.Invoke(_director, new object[] { 1f, true });
                }
                Assert.That(strongLong, Is.GreaterThan(weakLong * 3));
                Assert.That(strongLong, Is.LessThan(500));
                Assert.That(strongSpeeds.Average(), Is.GreaterThan(weakSpeeds.Average()));
                Assert.That(strongSpeeds.Distinct().Count(), Is.GreaterThan(20));
            }
            finally
            {
                UnityEngine.Random.state = state;
                Set("recordings", null);
                Object.DestroyImmediate(bank);
            }
        }

        [TestCase("Title")]
        [TestCase("Sea")]
        [TestCase("Forest")]
        [TestCase("Lake")]
        [TestCase("River")]
        [TestCase("Result")]
        public void SceneHasOnePersistentChimeUnderSoundscape(string sceneName)
        {
            var scene = SceneManager.GetSceneByPath($"Assets/Projects/Scenes/{sceneName}.unity");
            bool opened = !scene.IsValid() || !scene.isLoaded;
            var previous = SceneManager.GetActiveScene();
            try
            {
                if (opened) scene = EditorSceneManager.OpenScene($"Assets/Projects/Scenes/{sceneName}.unity", OpenSceneMode.Additive);
                var root = scene.GetRootGameObjects().Single(go => go.name == "Soundscape");
                var emitters = root.GetComponentsInChildren(_director.GetType(), true);
                Assert.That(emitters, Has.Length.EqualTo(1));
                var chime = emitters[0];
                Assert.That(chime.transform.parent, Is.EqualTo(root.transform));
                Assert.That(chime.name, Is.EqualTo("Wind Chime"));
                Assert.That(PrefabUtility.IsPartOfPrefabInstance(chime), Is.True);
                var source = chime.GetComponent<AudioSource>();
                Assert.That(source, Is.Not.Null);
                Assert.That(source.playOnAwake, Is.False);
                Assert.That(source.outputAudioMixerGroup, Is.Not.Null);
                using (var settings = new SerializedObject(chime))
                {
                    Assert.That(settings.FindProperty("windChimeThreshold").floatValue, Is.EqualTo(0.35f));
                    var bank = settings.FindProperty("recordings").objectReferenceValue;
                    Assert.That(bank, Is.Not.Null);
                    using (var recordingSettings = new SerializedObject(bank))
                    {
                        Assert.That(recordingSettings.FindProperty("shortStrikes").arraySize, Is.GreaterThan(0));
                        Assert.That(recordingSettings.FindProperty("longStrikes").arraySize, Is.GreaterThan(0));
                    }
                }
            }
            finally
            {
                if (previous.IsValid() && previous.isLoaded) SceneManager.SetActiveScene(previous);
                if (opened && scene.IsValid() && scene.isLoaded) EditorSceneManager.CloseScene(scene, true);
            }
        }

        private void Tick(float power) =>
            _director.GetType().GetMethod("UpdateWindChime", PrivateInstance).Invoke(_director, new object[] { power });

        private void Set(string name, object value) =>
            _director.GetType().GetField(name, PrivateInstance).SetValue(_director, value);

        private T Get<T>(string name) =>
            (T)_director.GetType().GetField(name, PrivateInstance).GetValue(_director);
    }
}
