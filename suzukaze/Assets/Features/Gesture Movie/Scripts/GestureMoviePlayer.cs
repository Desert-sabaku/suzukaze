using Features.Common.Scripts;
using Sirenix.OdinInspector;
using UnityEngine;

namespace Features.Gesture_Movie.Scripts
{
    /// <summary>
    ///     各ジェスチャーの動きをアーマチュアに行わせる
    /// </summary>
    public class GestureMoviePlayer : MonoBehaviour
    {
        [SerializeField] private Animator animator;

        [InfoBox("設定したジェスチャーをスタート時にループ再生します．SetAnimationを呼ぶと，そのジェスチャーに切り替わります．")]
        [SerializeField]
        private bool playOnStart = true;

        [SerializeField] private Gestures playOnStartGesture = Gestures.Yusuzumi;

        private void Start()
        {
            if (playOnStart)
                SetAnimation(playOnStartGesture);
        }

        [Button]
        public void SetAnimation(Gestures gesture)
        {
            animator.Play(gesture.ToString(), 0, 0f);
        }
    }
}
