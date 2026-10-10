using System;
using System.Linq;
using System.Reflection;
using NUnit.Framework;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;
using Object = UnityEngine.Object;

namespace Suzukaze.Gesture.Tests
{
    public class ShishiOdoshiTests
    {
        private const BindingFlags PrivateInstance = BindingFlags.Instance | BindingFlags.NonPublic;
        private Component _emitter;
        private GameObject _owner;

        [SetUp]
        public void SetUp()
        {
            _owner = new GameObject("Shishi odoshi test");
            _owner.SetActive(false);
            var type = Type.GetType("Features.Sound.Scripts.ShishiOdoshiSoundEmitter, Assembly-CSharp");
            Assert.That(type, Is.Not.Null);
            _emitter = _owner.AddComponent(type);
            Set("sensitivityThreshold", 0.5f);
            Set("firstStrikeDelaySeconds", new Vector2(1f, 1f));
            Set("refillSeconds", new Vector2(12f, 12f));
            Set("minimumIntervalSeconds", 8f);
        }

        [TearDown]
        public void TearDown()
        {
            Object.DestroyImmediate(_owner);
        }

        [Test]
        public void DoesNotStrikeBeforeSensesOpen()
        {
            Tick(0.49f, 0f);
            Tick(0.49f, 30f);
            Assert.That(LastStrike, Is.EqualTo(float.NegativeInfinity));
        }

        [Test]
        public void StrikesAfterPauseOnceSensesOpen()
        {
            Tick(0.5f, 10f);
            Tick(0.6f, 10.9f);
            Assert.That(LastStrike, Is.EqualTo(float.NegativeInfinity), "所作に即答せず、ひと呼吸おく");
            Tick(0.7f, 11f);
            Assert.That(LastStrike, Is.EqualTo(11f));
        }

        [Test]
        public void StrikesAgainOnlyAfterBambooRefills()
        {
            Tick(1f, 0f);
            Tick(1f, 1f);
            Tick(1f, 12.9f);
            Assert.That(LastStrike, Is.EqualTo(1f));
            Tick(1f, 13f);
            Assert.That(LastStrike, Is.EqualTo(13f));
        }

        [Test]
        public void FlickeringRelaxationDoesNotRestrikeEarly()
        {
            Tick(1f, 0f);
            Tick(1f, 1f);
            Tick(0f, 2f);
            Tick(1f, 3f);
            Tick(1f, 8.9f);
            Assert.That(LastStrike, Is.EqualTo(1f));
            Tick(1f, 9f);
            Assert.That(LastStrike, Is.EqualTo(9f));
        }

        [Test]
        public void StopsWhenRelaxationEnds()
        {
            Tick(1f, 0f);
            Tick(1f, 1f);
            Tick(0.2f, 5f);
            Tick(0.2f, 60f);
            Assert.That(LastStrike, Is.EqualTo(1f));
        }

        [TestCase("Forest")]
        [TestCase("Lake")]
        [TestCase("River")]
        [TestCase("Sea")]
        public void YusuzumiSceneHasOneShishiOdoshiWithClip(string name)
        {
            var type = Type.GetType("Features.Sound.Scripts.ShishiOdoshiSoundEmitter, Assembly-CSharp");
            var director = Type.GetType("Features.Sound.Scripts.YusuzumiSoundDirector, Assembly-CSharp");
            var path = "Assets/Projects/Scenes/" + name + ".unity";
            var scene = SceneManager.GetSceneByPath(path);
            var openedHere = !scene.IsValid() || !scene.isLoaded;
            try
            {
                if (openedHere) scene = EditorSceneManager.OpenScene(path, OpenSceneMode.Additive);
                var emitters = scene.GetRootGameObjects()
                    .SelectMany(root => root.GetComponentsInChildren(type, true)).ToArray();
                Assert.That(emitters, Has.Length.EqualTo(1), path);
                Assert.That(emitters[0].GetComponentInParent(director, true), Is.Not.Null,
                    "夕涼みの音と同じ Soundscape の下に置く");
                using var serialized = new SerializedObject(emitters[0]);
                Assert.That(serialized.FindProperty("clip").objectReferenceValue, Is.Not.Null);
                var source = emitters[0].GetComponent<AudioSource>();
                Assert.That(source.outputAudioMixerGroup, Is.Not.Null);
                Assert.That(source.playOnAwake, Is.False);
            }
            finally
            {
                if (openedHere && scene.IsValid()) EditorSceneManager.CloseScene(scene, true);
            }
        }

        private float LastStrike => (float)Field("_lastStrikeTime").GetValue(_emitter);

        private void Tick(float sensitivity, float now)
        {
            _emitter.GetType().GetMethod("Tick", PrivateInstance)!.Invoke(_emitter, new object[] { sensitivity, now });
        }

        private void Set(string name, object value)
        {
            Field(name).SetValue(_emitter, value);
        }

        private FieldInfo Field(string name)
        {
            var field = _emitter.GetType().GetField(name, PrivateInstance);
            Assert.That(field, Is.Not.Null, name);
            return field;
        }
    }
}
