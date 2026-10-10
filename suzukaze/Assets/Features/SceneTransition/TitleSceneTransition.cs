using System.Collections.Generic;
using System.Linq;
using Cysharp.Threading.Tasks;
using Features.Common.Scripts;
using Features.Gesture_Movie.Scripts;
using Sirenix.OdinInspector;
using Suzukaze.Gesture;
using Suzukaze.Gesture.Protocol;
using UnityEngine;
using UnityEngine.InputSystem;

namespace Features.SceneTransition
{
    public class TitleSceneTransition : MonoBehaviour
    {
        [SerializeField] private CanvasGroup gestureCanvasGroup;
        [SerializeField] private GestureMoviePlayer gestureMoviePlayer;
        [SerializeField] private float gestureDisplayDuration = 2f;

        /// <summary>
        ///     まだ遷移していないゲームシーン。空になったらシャッフルして補充する
        /// </summary>
        private static readonly Queue<string> RemainingScenes = new();

        private static string _lastScene;

        private GestureReceiverBehaviour _gestureReceiver;
        private GameInputs _input;

        [ShowInInspector] private bool _isShowingGesture;

        /// <summary>
        ///     前のシーンから礼が継続している間は遷移しないよう、礼以外の姿勢を一度確認してから礼を受け付ける
        /// </summary>
        [ShowInInspector] private bool _isBowReleased;

        private void Start()
        {
            _input = new GameInputs();
            _input.Debug.Enable();

            gestureCanvasGroup.alpha = 0f;
            _input.Debug.NextStep.performed += OnTransition;
        }

        private void Update()
        {
            if (Keyboard.current != null && Keyboard.current.escapeKey.wasPressedThisFrame)
            {
                Quit();
                return;
            }

            gestureCanvasGroup.alpha = Mathf.MoveTowards(
                gestureCanvasGroup.alpha, _isShowingGesture ? 1f : 0f,
                Time.deltaTime * gestureDisplayDuration
            );
        }

        private void OnEnable()
        {
            if (_gestureReceiver) return;
            _gestureReceiver = GestureReceiverBehaviour.GetOrCreate();
            _isBowReleased = false;
            UpdateBowReleased(_gestureReceiver.Events.CurrentState);
            _gestureReceiver.Events.StateChanged += OnGestureStateChanged;
        }

        private void OnDisable()
        {
            if (_gestureReceiver)
                _gestureReceiver.Events.StateChanged -= OnGestureStateChanged;
            _gestureReceiver = null;
        }

        private void OnDestroy()
        {
            _input.Debug.NextStep.performed -= OnTransition;
            _input.Disable();
            _input.Dispose();
        }

        private void OnGestureStateChanged(StateView state)
        {
            if (state.BoothPresent && !_isShowingGesture)
                gestureMoviePlayer.SetAnimation(Gestures.Rei);

            _isShowingGesture = state.BoothPresent;

            UpdateBowReleased(state);
            if (_isBowReleased && state.Tracking && state.Gesture == ContinuousGesture.Bow)
            {
                OnTransition(default);
                _gestureReceiver.Events.StateChanged -= OnGestureStateChanged;
                _gestureReceiver = null;
            }
        }

        private void UpdateBowReleased(StateView state)
        {
            if (state.Tracking && state.Gesture != ContinuousGesture.Bow) _isBowReleased = true;
        }

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.SubsystemRegistration)]
        private static void ResetStatics()
        {
            RemainingScenes.Clear();
            _lastScene = null;
        }

        private static void Quit()
        {
#if UNITY_EDITOR
            UnityEditor.EditorApplication.isPlaying = false;
#else
            Application.Quit();
#endif
        }

        private static void OnTransition(InputAction.CallbackContext ctx)
        {
            TransitionToRandomSceneAsync().Forget();
        }

        private static async UniTaskVoid TransitionToRandomSceneAsync()
        {
            var settings = await GameSettings.GetInstanceAsync();
            var scene = PickNextScene(settings.gameScenes);
            if (scene == null)
            {
                Debug.LogError("GameSettings.gameScenes にシーンが設定されていません");
                return;
            }

            SceneTransitionManager.Instance.LoadSceneAsync(scene).Forget();
        }

        /// <summary>
        ///     全シーンを一巡するまで同じシーンを選ばないようにランダムに選ぶ
        /// </summary>
        private static string PickNextScene(string[] scenes)
        {
            if (RemainingScenes.Count == 0)
            {
                var candidates = scenes?.Where(s => !string.IsNullOrEmpty(s)).Distinct().ToList() ?? new List<string>();
                if (candidates.Count == 0) return null;

                // Fisher–Yates でシャッフルする
                for (var i = candidates.Count - 1; i > 0; i--)
                {
                    var j = Random.Range(0, i + 1);
                    (candidates[i], candidates[j]) = (candidates[j], candidates[i]);
                }

                // 一巡の境目で直前と同じシーンが続かないようにする
                if (candidates.Count > 1 && candidates[0] == _lastScene)
                    (candidates[0], candidates[^1]) = (candidates[^1], candidates[0]);

                foreach (var candidate in candidates) RemainingScenes.Enqueue(candidate);
            }

            _lastScene = RemainingScenes.Dequeue();
            return _lastScene;
        }
    }
}
