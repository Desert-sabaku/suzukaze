using System;
using System.Reflection;
using NUnit.Framework;
using UnityEditor;
using UnityEngine;
using Object = UnityEngine.Object;

namespace Suzukaze.Gesture.Tests
{
    public class LeafWindTests
    {
        private const BindingFlags Fields = BindingFlags.Instance | BindingFlags.NonPublic;
        private ScriptableObject _profile;
        private Component _emitter;
        private Component _wind;
        private GameObject _owner;
        private GameObject _windOwner;

        [SetUp]
        public void SetUp()
        {
            _profile = ScriptableObject.CreateInstance(Type.GetType("Features.Sound.Scripts.CreatureSoundProfile, Assembly-CSharp"));
            SetProfile("windDrivenLoop", true);
            SetProfile("windThreshold", 0.5f);
            _owner = new GameObject("Leaf test");
            _owner.SetActive(false);
            _emitter = _owner.AddComponent(Type.GetType("Features.Sound.Scripts.CreatureSoundEmitter, Assembly-CSharp"));
            SetEmitter("profile", _profile);
            SetEmitter("_singing", true);
            SetEmitter("_activity", 0.8f);
            SetEmitter("_threshold", 0.2f);
            SetProfile("modulationDepth", 0.6f);
            _windOwner = new GameObject("Leaf wind");
            _wind = _windOwner.AddComponent(Type.GetType("Suzukaze.Fan.WindFanController, Suzukaze.Fan"));
            SetEmitter("_wind", _wind);
        }

        [TearDown]
        public void TearDown()
        {
            Object.DestroyImmediate(_owner);
            Object.DestroyImmediate(_windOwner);
            Object.DestroyImmediate(_profile);
        }

        [TestCase(0f)]
        [TestCase(0.35f)]
        [TestCase(0.5f)]
        public void LeafTargetIsSilentUntilWindExceedsHigherThreshold(float power)
        {
            SetWind(power);
            Assert.That(TargetGain(), Is.Zero);
        }

        [Test]
        public void WindMultipliesExistingActivityAndNoiseWithoutIncreasingMaximum()
        {
            SetProfile("windDrivenLoop", false);
            float original = TargetGain();
            Assert.That(original, Is.GreaterThan(0f));
            SetProfile("windDrivenLoop", true);
            SetWind(0.75f);
            Assert.That(TargetGain(), Is.EqualTo(original * 0.5f).Within(0.00001f));
            SetWind(1f);
            Assert.That(TargetGain(), Is.EqualTo(original).Within(0.00001f));
            SetEmitter("_wind", null);
            Assert.That(TargetGain(), Is.Zero);
            SetProfile("windDrivenLoop", false);
            Assert.That(TargetGain(), Is.EqualTo(original).Within(0.00001f));
        }

        [Test]
        public void DisabledWindDoesNotProduceLeafSound()
        {
            SetWind(1f);
            ((Behaviour)_wind).enabled = false;
            Assert.That(TargetGain(), Is.Zero);
        }

        [Test]
        public void WindOnlyVolumeBoostIsOnePointFiveAndPreservesFadeGain()
        {
            SetWind(0.75f);
            var source = _owner.GetComponent<AudioSource>();
            SetEmitter("_source", source);
            SetEmitter("_loopGain", TargetGain());
            var update = _emitter.GetType().GetMethod("UpdateLoop", Fields);
            update.Invoke(_emitter, null);
            float originalVolume = source.volume;
            float originalGain = TargetGain();
            SetProfile("windVolumeMultiplier", 1.5f);
            update.Invoke(_emitter, null);
            Assert.That(source.volume, Is.EqualTo(originalVolume * 1.5f).Within(0.00001f));
            Assert.That(TargetGain(), Is.EqualTo(originalGain).Within(0.00001f));
            SetProfile("windDrivenLoop", false);
            Assert.That((float)_profile.GetType().GetProperty("WindVolumeScale").GetValue(_profile), Is.EqualTo(1f));
        }

        [Test]
        public void LeafProfileKeepsOriginalTimeVolumeAndModulationSettings()
        {
            var profile = AssetDatabase.LoadAssetAtPath<ScriptableObject>("Assets/Features/Sound/Profiles/Ambience_PlantsSwayingBed.asset");
            using var settings = new SerializedObject(profile);
            Assert.That(settings.FindProperty("windDrivenLoop").boolValue, Is.True);
            Assert.That(settings.FindProperty("windThreshold").floatValue, Is.EqualTo(0.5f));
            Assert.That(settings.FindProperty("windVolumeMultiplier").floatValue, Is.EqualTo(1.5f));
            Assert.That(settings.FindProperty("volume").floatValue, Is.EqualTo(0.3f));
            Assert.That(settings.FindProperty("modulationDepth").floatValue, Is.EqualTo(0.6f));
            Assert.That(settings.FindProperty("modulationPeriod").floatValue, Is.EqualTo(6f));
            Assert.That(settings.FindProperty("fadeSeconds").floatValue, Is.EqualTo(1.5f));
            Assert.That(settings.FindProperty("pauseSeconds").vector2Value, Is.EqualTo(Vector2.zero));
            var curve = settings.FindProperty("activityByHour").animationCurveValue;
            Assert.That(curve.Evaluate(8f), Is.EqualTo(0.6f).Within(0.00001f));
            Assert.That(curve.Evaluate(11f), Is.EqualTo(1f).Within(0.00001f));
            Assert.That(curve.Evaluate(19f), Is.EqualTo(0.6f).Within(0.00001f));
        }

        private float TargetGain() => (float)_emitter.GetType().GetMethod("LoopTargetGain", Fields).Invoke(_emitter, null);
        private void SetProfile(string name, object value) => _profile.GetType().GetField(name).SetValue(_profile, value);
        private void SetEmitter(string name, object value) => _emitter.GetType().GetField(name, Fields).SetValue(_emitter, value);
        private void SetWind(float power) => _wind.GetType().GetMethod("SetWind").Invoke(_wind, new object[] { Vector3.back, power });
    }
}
