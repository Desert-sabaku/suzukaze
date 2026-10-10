using Sirenix.OdinInspector;
using Suzukaze.Gesture;
using Suzukaze.Gesture.Protocol;
using UnityEngine;
using UnityEngine.Audio;

namespace Features.Sound.Scripts
{
    /// <summary>
    ///     Boosts environmental sound during relaxation. Wind chimes are controlled by WindChimeSoundEmitter.
    ///     各シーンの Soundscape に SoundscapeDirector と並べて 1 つ置く
    /// </summary>
    public class YusuzumiSoundDirector : MonoBehaviour
    {
        // 環境音のうち、夕涼みで大きくするレイヤー (残響の戻りは SoundscapeDirector が時刻で動かす)
        private static readonly string[] BoostedLayers =
        {
            SoundMixerParameters.AmbientVolume,
            SoundMixerParameters.CicadasVolume,
            SoundMixerParameters.InsectsVolume,
            SoundMixerParameters.BirdsVolume
        };

        [Title("Mixer")] [SerializeField] [Required]
        private AudioMixer mixer;

        [Tooltip("感覚が最も鋭くなったときに環境音を持ち上げる量 (dB)")] [SerializeField] [Range(0f, 12f)]
        private float boostDb = 8f;

        [Title("感覚の変化")] [Tooltip("夕涼みを始めてから感覚が最も鋭くなるまでの時間 (秒)")] [SerializeField] [Min(0.01f)]
        private float attackSeconds = 3f;

        [Tooltip("夕涼みをやめてから元の聞こえ方に戻るまでの時間 (秒)")] [SerializeField] [Min(0.01f)]
        private float releaseSeconds = 5f;

        [Title("デバッグ")] [Tooltip("夕涼みによる環境音の変化を、所作なしで確認する")] [SerializeField]
        private bool forceYusuzumi;

        [Title("現在の状態")] [ReadOnly] [ShowInInspector]
        private bool _relaxing;

        [ReadOnly] [ShowInInspector] [ProgressBar(0f, 1f)]
        private float _sensitivity;

        private GestureReceiverBehaviour _gestureReceiver;

        private void Update()
        {
            var target = _relaxing || forceYusuzumi ? 1f : 0f;
            var seconds = target > _sensitivity ? attackSeconds : releaseSeconds;
            _sensitivity = Mathf.MoveTowards(_sensitivity, target, Time.deltaTime / seconds);

            // 気づくように感覚がふっと開け、ゆっくり元に戻るよう、なめらかに変化させる
            var eased = Mathf.SmoothStep(0f, 1f, _sensitivity);
            SoundSensitivity.Level = eased;
            if (mixer)
                foreach (var layer in BoostedLayers)
                    mixer.SetFloat(layer, boostDb * eased);
        }

        private void OnEnable()
        {
            _gestureReceiver = GestureReceiverBehaviour.GetOrCreate();
            _gestureReceiver.Events.StateChanged += OnGestureStateChanged;
            OnGestureStateChanged(_gestureReceiver.Events.CurrentState);
        }

        private void OnDisable()
        {
            if (_gestureReceiver)
            {
                _gestureReceiver.Events.StateChanged -= OnGestureStateChanged;
                _gestureReceiver = null;
            }

            _relaxing = false;
            _sensitivity = 0f;
            SoundSensitivity.Level = 0f;
            if (mixer)
                foreach (var layer in BoostedLayers)
                    mixer.ClearFloat(layer);
        }

        private void OnGestureStateChanged(StateView state)
        {
            // 追跡が切れたり鮮度を失ったりすると Gesture は None になり、自然に元の聞こえ方へ戻る
            _relaxing = state.Fresh && state.Tracking && state.Gesture == ContinuousGesture.Relaxing;
        }

        [Button("夕涼みを切り替え")]
        private void ToggleForceYusuzumi()
        {
            forceYusuzumi = !forceYusuzumi;
        }
    }
}
