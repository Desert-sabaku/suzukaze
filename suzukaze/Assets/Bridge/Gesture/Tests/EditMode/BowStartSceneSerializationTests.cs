using System;
using System.IO;
using System.Linq;
using NUnit.Framework;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;

namespace Suzukaze.Gesture.Receiver.Tests
{
    public class BowStartSceneSerializationTests
    {
        [Test]
        public void StartSceneHasOneEnabledLoaderWithPlayableDestinations()
        {
            const string path = "Assets/MyScenes/Scene_ch.unity";
            var type = Type.GetType("RandomSceneLoader, Assembly-CSharp");
            Assert.That(type, Is.Not.Null);
            var scene = SceneManager.GetSceneByPath(path);
            bool openedHere = !scene.IsValid() || !scene.isLoaded;
            var previousActive = SceneManager.GetActiveScene();
            try
            {
                if (openedHere) scene = EditorSceneManager.OpenScene(path, OpenSceneMode.Additive);
                var loaders = scene.GetRootGameObjects()
                    .SelectMany(root => root.GetComponentsInChildren(type, true)).ToArray();
                Assert.That(loaders, Has.Length.EqualTo(1),
                    "Changing the script is not enough: the start scene must instantiate it");
                var loader = (MonoBehaviour)loaders[0];
                Assert.That(loader.enabled, Is.True);
                Assert.That(loader.gameObject.activeInHierarchy, Is.True);
                var script = AssetDatabase.LoadAssetAtPath<MonoScript>(
                    "Assets/My_script/FOR SCENE/RandomSceneLoader.cs");
                Assert.That(MonoScript.FromMonoBehaviour(loader), Is.EqualTo(script));

                var destinations = EditorBuildSettings.scenes
                    .Where(item => item.enabled && item.path != path)
                    .Select(item => Path.GetFileNameWithoutExtension(item.path)).ToArray();
                Assert.That(destinations, Is.Not.Empty);
                using (var serialized = new SerializedObject(loader))
                {
                    var names = serialized.FindProperty("sceneNames");
                    var actual = Enumerable.Range(0, names.arraySize)
                        .Select(index => names.GetArrayElementAtIndex(index).stringValue).ToArray();
                    Assert.That(actual, Is.EquivalentTo(destinations));
                    Assert.That(actual.Distinct().Count(), Is.EqualTo(actual.Length));
                }
            }
            finally
            {
                if (previousActive.IsValid() && previousActive.isLoaded)
                    SceneManager.SetActiveScene(previousActive);
                if (openedHere && scene.IsValid() && scene.isLoaded)
                    EditorSceneManager.CloseScene(scene, true);
            }
        }
    }
}
