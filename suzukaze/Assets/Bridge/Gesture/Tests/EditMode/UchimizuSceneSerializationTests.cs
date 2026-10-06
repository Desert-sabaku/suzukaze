using System;
using System.Linq;
using NUnit.Framework;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;
using Object = UnityEngine.Object;

namespace Suzukaze.Gesture.Tests
{
    public class UchimizuSceneSerializationTests
    {
        private const string ScriptGuid = "baba8db9ee1893a4ebbcd90a5fc639cb";
        private const string ParticleGuid = "534983ee0594fd04dbdf44833ca76a63";
        private const string PlayerGuid = "daff3dab948141347802502ed953c7f1";

        // These are the six existing scenes containing ParticleOnEnter, with their
        // original offsets. Open one at a time so the large waterfall scene is released.
        [TestCase("Forest", 0.125f)]
        [TestCase("river", 0.25f)]
        [TestCase("sea", 0.1f)]
        [TestCase("Sea2", 0.125f)]
        [TestCase("☆1湖", 0.125f)]
        [TestCase("滝", 0.125f)]
        public void ExistingSceneResolvesRealEffectAndPreservesConfiguration(string name, float heightOffset)
        {
            var type = Type.GetType("ParticleOnEnter, Assembly-CSharp");
            Assert.That(type, Is.Not.Null);
            var script = AssetDatabase.LoadAssetAtPath<MonoScript>(AssetDatabase.GUIDToAssetPath(ScriptGuid));
            Assert.That(script, Is.Not.Null);
            Assert.That(script.GetClass(), Is.EqualTo(type));
            var tryPlay = type.GetMethod("TryPlay", Type.EmptyTypes);
            Assert.That(tryPlay, Is.Not.Null, "The real effect must expose manual playback");
            Assert.That(tryPlay.IsPublic, Is.True);
            Assert.That(tryPlay.IsStatic, Is.False);
            Assert.That(tryPlay.ReturnType, Is.EqualTo(typeof(bool)));

            string path = "Assets/MyScenes/" + name + ".unity";
            var scene = SceneManager.GetSceneByPath(path);
            bool wasPresent = scene.IsValid();
            bool openedHere = !wasPresent || !scene.isLoaded;
            var previousActive = SceneManager.GetActiveScene();
            try
            {
                if (openedHere) scene = EditorSceneManager.OpenScene(path, OpenSceneMode.Additive);
                Assert.That(scene.isLoaded, Is.True);
                var effects = scene.GetRootGameObjects()
                    .SelectMany(root => root.GetComponentsInChildren(type, true)).ToArray();
                Assert.That(effects, Has.Length.EqualTo(1), path);
                var effect = (MonoBehaviour)effects[0];
                Assert.That(MonoScript.FromMonoBehaviour(effect), Is.EqualTo(script));
                Assert.That(effect.enabled, Is.True);

                using (var serialized = new SerializedObject(effect))
                {
                    var particle = serialized.FindProperty("particlePrefab").objectReferenceValue as ParticleSystem;
                    AssertAssetIdentity(particle, ParticleGuid, 5486873766020292339L);
                    var neck = serialized.FindProperty("neck").objectReferenceValue as Transform;
                    var player = serialized.FindProperty("player").objectReferenceValue as Transform;
                    Assert.That(neck, Is.Not.Null, path + " neck must deserialize");
                    Assert.That(player, Is.Not.Null, path + " player must deserialize");
                    Assert.That(neck.gameObject.scene, Is.EqualTo(scene));
                    Assert.That(player.gameObject.scene, Is.EqualTo(scene));
                    AssertAssetIdentity(PrefabUtility.GetCorrespondingObjectFromSource(neck),
                        PlayerGuid, 221575539347151033L);
                    AssertAssetIdentity(PrefabUtility.GetCorrespondingObjectFromSource(player),
                        PlayerGuid, 9047742808143547557L);
                    Assert.That(PrefabUtility.GetOutermostPrefabInstanceRoot(neck),
                        Is.EqualTo(PrefabUtility.GetOutermostPrefabInstanceRoot(player)));
                    Assert.That(serialized.FindProperty("heightOffset").floatValue,
                        Is.EqualTo(heightOffset).Within(0.00001f));
                    Assert.That(serialized.FindProperty("receiveGestures").boolValue, Is.True,
                        "Old scene data must receive gestures without saving the scene again");
                }
            }
            finally
            {
                if (previousActive.IsValid() && previousActive.isLoaded)
                    SceneManager.SetActiveScene(previousActive);
                // Never close or save a scene that was already open in the Editor.
                if (openedHere && scene.IsValid() && scene.isLoaded)
                    EditorSceneManager.CloseScene(scene, !wasPresent);
            }
        }

        private static void AssertAssetIdentity(Object asset, string expectedGuid, long expectedFileId)
        {
            Assert.That(asset, Is.Not.Null);
            Assert.That(AssetDatabase.TryGetGUIDAndLocalFileIdentifier(asset, out string guid, out long fileId),
                Is.True);
            Assert.That(guid, Is.EqualTo(expectedGuid));
            Assert.That(fileId, Is.EqualTo(expectedFileId));
        }
    }
}
