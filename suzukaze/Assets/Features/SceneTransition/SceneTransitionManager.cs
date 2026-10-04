using Cysharp.Threading.Tasks;
using Features.Common.Scripts;
using LitMotion;
using UnityEngine;
using UnityEngine.AddressableAssets;
using UnityEngine.SceneManagement;
using UnityEngine.UI;

namespace Features.SceneTransition
{
    public class SceneTransitionManager : SingletonMonoBehaviourAutoCreate<SceneTransitionManager>
    {
        [SerializeField] private float transitionDuration = 0.5f;

        private Image[] _images;

        public async UniTask LoadSceneAsync(string sceneName)
        {
            if (_images == null)
            {
                var transitionPanel = await Addressables.InstantiateAsync("Transition Canvas", transform);
                _images = transitionPanel.GetComponentsInChildren<Image>();
            }

            await UniTask.WhenAll(_images.Select(image =>
            {
                var pivotX = image.rectTransform.pivot.x;
                return LMotion.Create(pivotX, 1f - pivotX, transitionDuration)
                    .Bind(v =>
                    {
                        var pivot = image.rectTransform.pivot;
                        pivot.x = v;
                        image.rectTransform.pivot = pivot;
                    }).ToUniTask();
            }));

            await SceneManager.LoadSceneAsync(sceneName, LoadSceneMode.Single);

            await UniTask.WhenAll(_images.Select(image =>
            {
                var pivotX = image.rectTransform.pivot.x;
                return LMotion.Create(pivotX, 1f - pivotX, transitionDuration)
                    .Bind(v =>
                    {
                        var pivot = image.rectTransform.pivot;
                        pivot.x = v;
                        image.rectTransform.pivot = pivot;
                    }).ToUniTask();
            }));
        }
    }
}