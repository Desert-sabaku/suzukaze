using System.Linq;
using Cysharp.Threading.Tasks;
using LitMotion;
using LitMotion.Extensions;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.Rendering.Universal;
using UnityEngine.SceneManagement;

namespace Features.SceneTransition
{
    /// <summary>
    ///     シーン遷移を管理する
    /// </summary>
    public static class SceneTransitionUtils
    {
        public static async UniTask LoadSceneAsync(string sceneName, float transitionDuration = 0.5f)
        {
            var currentScene = SceneManager.GetActiveScene();

            var currentVolume = FindObjectInScene<Volume>(currentScene);
            currentVolume.profile.TryGet(typeof(LensDistortion), out LensDistortion lensDistortion);

            var currentCamera = FindObjectInScene<Camera>(currentScene);

            await SceneManager.LoadSceneAsync(sceneName, LoadSceneMode.Additive);
            var nextScene = SceneManager.GetSceneByName(sceneName);
            var nextSceneCamera = FindObjectInScene<Camera>(nextScene);
            nextSceneCamera.gameObject.SetActive(false);
            var nextVolume = FindObjectInScene<Volume>(nextScene);
            nextVolume.gameObject.SetActive(false);

            await LSequence.Create()
                .Append(
                    LMotion.Create(0f, -1f, transitionDuration * 0.1f)
                        .Bind(v => lensDistortion.intensity.value = v)
                )
                .Join(
                    LMotion.Create(1f, 0.3f, transitionDuration * 0.1f)
                        .Bind(v => lensDistortion.scale.value = v)
                )
                .Join(
                    LMotion.Create(currentCamera.transform.position, nextSceneCamera.transform.position,
                            transitionDuration)
                        .WithOnComplete(() =>
                            {
                                SceneManager.SetActiveScene(nextScene);
                                nextSceneCamera.gameObject.SetActive(true);
                                lensDistortion.intensity.value = 0;
                                nextVolume.gameObject.SetActive(true);
                                SceneManager.UnloadSceneAsync(currentScene);
                            }
                        )
                        .BindToPosition(currentCamera.transform)
                )
                .AppendInterval(transitionDuration * 0.8f)
                .Append(
                    LMotion.Create(-1f, 0f, transitionDuration * 0.1f)
                        .Bind(v => lensDistortion.intensity.value = v)
                )
                .Join(
                    LMotion.Create(.3f, 1f, transitionDuration * 0.1f)
                        .Bind(v => lensDistortion.scale.value = v)
                )
                .Join(
                    LMotion.Create(currentCamera.transform.rotation, nextSceneCamera.transform.rotation,
                            transitionDuration * 0.1f)
                        .BindToRotation(currentCamera.transform)
                )
                .Run();
        }

        private static T FindObjectInScene<T>(UnityEngine.SceneManagement.Scene scene) where T : Component
        {
            return scene.GetRootGameObjects()
                .Select(rootGameObject => rootGameObject.GetComponentInChildren<T>())
                .FirstOrDefault(component => component != null);
        }
    }
}