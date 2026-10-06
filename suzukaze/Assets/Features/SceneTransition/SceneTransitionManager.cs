using Cysharp.Threading.Tasks;
using Features.Common.Scripts;
using Features.Sound.Scripts;
using LitMotion;
using UnityEngine;
using UnityEngine.AddressableAssets;
using UnityEngine.SceneManagement;
using UnityEngine.UI;

namespace Features.SceneTransition
{
    public class SceneTransitionManager : SingletonMonoBehaviourAutoCreate<SceneTransitionManager>
    {
        private GameSettings _gameSettings;
        private Image[] _images;

        public async UniTask LoadSceneAsync(string sceneName)
        {
            if (_images == null)
            {
                var transitionPanel = await Addressables.InstantiateAsync("Transition Canvas", transform);
                _images = transitionPanel.GetComponentsInChildren<Image>();
            }

            _gameSettings ??= await GameSettings.GetInstanceAsync();

            // 障子が閉じるのに合わせて環境音を絞る。次のシーンでは SoundscapeDirector がフェードインする
            await UniTask.WhenAll(
                UniTask.WhenAll(_images.Select(image =>
                {
                    var pivotX = image.rectTransform.pivot.x;

                    return LMotion.Create(pivotX, 1f - pivotX, _gameSettings.sceneTransitionDuration)
                        .Bind(v =>
                        {
                            var pivot = image.rectTransform.pivot;
                            pivot.x = v;
                            image.rectTransform.pivot = pivot;
                        }).ToUniTask();
                })),
                SoundscapeDirector.FadeOutAsync(_gameSettings.sceneTransitionDuration));

            await UniTask.WaitForSeconds(0.05f);
            await SceneManager.LoadSceneAsync(sceneName, LoadSceneMode.Single);
            await UniTask.WaitForSeconds(0.05f);

            await UniTask.WhenAll(_images.Select(image =>
            {
                var pivotX = image.rectTransform.pivot.x;
                return LMotion.Create(pivotX, 1f - pivotX, _gameSettings.sceneTransitionDuration)
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