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

        /// <summary>
        ///     障子が開いているときの pivot.x。閉じた位置は 1 - 開いた位置
        /// </summary>
        private float[] _openPivotX;

        /// <summary>
        ///     遷移中に別の遷移が始まると、同じ障子を 2 つのモーションが動かして途中で止まるため、遷移は 1 つずつ行う
        /// </summary>
        private bool _isTransitioning;

        /// <summary>
        ///     遷移を始めたときのアクティブシーンの handle。遷移中の要求がどのシーンから来たかの判定に使う
        /// </summary>
        private SceneHandle _sourceSceneHandle;

        /// <summary>
        ///     障子が開いている間に新しいシーンから要求された遷移先。開き終わってから遷移する
        /// </summary>
        private string _pendingScene;

        /// <summary>
        ///     シーンを遷移する。遷移中に呼ばれた場合、遷移元のシーンからの要求は重複として無視し、
        ///     遷移先のシーンからの要求は障子が開き終わってから実行する。後者の場合は要求を受け付けた時点で完了する
        /// </summary>
        public async UniTask LoadSceneAsync(string sceneName)
        {
            if (_isTransitioning)
            {
                // 呼び出し側は遷移を要求したら自身を無効化するため、新しいシーンからの要求を捨てると遷移しなくなる
                if (SceneManager.GetActiveScene().handle != _sourceSceneHandle && _pendingScene == null)
                    _pendingScene = sceneName;
                else
                    Debug.LogWarning($"シーン遷移中のため {sceneName} への遷移を無視しました");
                return;
            }

            _isTransitioning = true;
            try
            {
                if (_images == null)
                {
                    var transitionPanel = await Addressables.InstantiateAsync("Transition Canvas", transform);
                    _images = transitionPanel.GetComponentsInChildren<Image>();
                    _openPivotX = new float[_images.Length];
                    for (var i = 0; i < _images.Length; i++) _openPivotX[i] = _images[i].rectTransform.pivot.x;
                }

                _gameSettings ??= await GameSettings.GetInstanceAsync();

                while (sceneName != null)
                {
                    _sourceSceneHandle = SceneManager.GetActiveScene().handle;
                    await TransitionAsync(sceneName);

                    sceneName = _pendingScene;
                    _pendingScene = null;
                }
            }
            finally
            {
                _isTransitioning = false;
                _pendingScene = null;
            }
        }

        private async UniTask TransitionAsync(string sceneName)
        {
            // 障子が閉じるのに合わせて環境音を絞る。次のシーンでは SoundscapeDirector がフェードインする
            await UniTask.WhenAll(
                MoveShojiAsync(false),
                SoundscapeDirector.FadeOutAsync(_gameSettings.sceneTransitionDuration));

            await UniTask.WaitForSeconds(0.05f);
            await SceneManager.LoadSceneAsync(sceneName, LoadSceneMode.Single);
            await UniTask.WaitForSeconds(0.05f);

            await MoveShojiAsync(true);
        }

        /// <summary>
        ///     現在位置ではなく固定の開閉位置へ動かし、前の遷移が中断されていても正しい位置に戻す
        /// </summary>
        private UniTask MoveShojiAsync(bool open)
        {
            return UniTask.WhenAll(_images.Select((image, i) =>
            {
                var target = open ? _openPivotX[i] : 1f - _openPivotX[i];
                return LMotion.Create(image.rectTransform.pivot.x, target, _gameSettings.sceneTransitionDuration)
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
