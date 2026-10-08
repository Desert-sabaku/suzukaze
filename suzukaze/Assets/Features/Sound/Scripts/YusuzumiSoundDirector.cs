using System.Linq;
using Sirenix.OdinInspector;
using Suzukaze.Gesture;
using Suzukaze.Gesture.Protocol;
using UnityEngine;
using UnityEngine.Audio;

namespace Features.Sound.Scripts
{
    /// <summary>
    ///     夕涼みのあいだ感覚が研ぎ澄まされ、周りの音が大きく澄んで聞こえ、風鈴の音も聞こえてくる。
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

        [Title("風鈴")] [Tooltip("空なら合成した風鈴の音を使う")] [SerializeField]
        private AudioClip[] windChimeClips;

        [SerializeField] private AudioMixerGroup windChimeOutput;
        [SerializeField] [Range(0f, 1f)] private float windChimeVolume = 0.6f;

        [Tooltip("感覚がこの鋭さを超えると風鈴が聞こえ始める")] [SerializeField] [Range(0f, 1f)]
        private float windChimeThreshold = 0.35f;

        [Tooltip("風が吹いて風鈴が鳴る間隔 (秒)")] [SerializeField] [MinMaxSlider(0.5f, 20f, true)]
        private Vector2 windChimeIntervalSeconds = new(2.5f, 7f);

        [Tooltip("一度の風で舌が当たる回数")] [SerializeField]
        private Vector2Int strikesPerGust = new(1, 3);

        [SerializeField] [MinMaxSlider(0.05f, 1f, true)]
        private Vector2 gapBetweenStrikesSeconds = new(0.12f, 0.4f);

        [Tooltip("聞き手から見た風鈴の位置。軒先に吊るした風鈴を想定し、少し上の前方に置く")] [SerializeField]
        private Vector3 windChimeOffset = new(0.8f, 1.2f, 1.5f);

        [Title("デバッグ")] [Tooltip("有効にすると、所作が無くても夕涼みしているものとして鳴らす")] [SerializeField]
        private bool forceYusuzumi;

        [Title("現在の状態")] [ReadOnly] [ShowInInspector]
        private bool _relaxing;

        [ReadOnly] [ShowInInspector] [ProgressBar(0f, 1f)]
        private float _sensitivity;

        private AudioClip[] _clips;
        private AudioClip _lastClip;
        private GestureReceiverBehaviour _gestureReceiver;
        private float _nextGustTime;
        private float _nextStrikeTime;
        private int _strikesRemaining;
        private float _strikeGain;
        private AudioSource _windChime;

        private void Awake()
        {
            _clips = windChimeClips != null && windChimeClips.Any(c => c)
                ? windChimeClips.Where(c => c).ToArray()
                : WindChimeSynth.CreateClips();
            if (!windChimeOutput && mixer)
                windChimeOutput = mixer.FindMatchingGroups("Gesture Effect").FirstOrDefault();
        }

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

            UpdateWindChime(eased);
        }

        private void OnEnable()
        {
            _gestureReceiver = GestureReceiverBehaviour.GetOrCreate();
            _gestureReceiver.Events.StateChanged += OnGestureStateChanged;
            OnGestureStateChanged(_gestureReceiver.Events.CurrentState);
            _nextGustTime = Time.time;
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
            _strikesRemaining = 0;
            SoundSensitivity.Level = 0f;
            if (mixer)
                foreach (var layer in BoostedLayers)
                    mixer.ClearFloat(layer);
            if (_windChime) _windChime.Stop();
        }

        private void OnDestroy()
        {
            if (_windChime) Destroy(_windChime.gameObject);
            if (_clips == null || windChimeClips != null && windChimeClips.Any(c => c)) return;
            foreach (var clip in _clips) Destroy(clip);
        }

        private void OnGestureStateChanged(StateView state)
        {
            // 追跡が切れたり鮮度を失ったりすると Gesture は None になり、自然に元の聞こえ方へ戻る
            _relaxing = state.Fresh && state.Tracking && state.Gesture == ContinuousGesture.Relaxing;
        }

        private void UpdateWindChime(float sensitivity)
        {
            if (_clips.Length == 0) return;

            if (_strikesRemaining > 0 && Time.time >= _nextStrikeTime)
            {
                Strike(sensitivity);
                return;
            }

            if (sensitivity < windChimeThreshold || Time.time < _nextGustTime) return;

            _strikesRemaining = Random.Range(strikesPerGust.x, strikesPerGust.y + 1);
            _strikeGain = Random.Range(0.6f, 1f);
            _nextGustTime = Time.time + Random.Range(windChimeIntervalSeconds.x, windChimeIntervalSeconds.y);
            Strike(sensitivity);
        }

        /// <summary>
        ///     舌が 1 回ガラスに当たる。風の一吹きの中では、当たるたびに弱くなる
        /// </summary>
        private void Strike(float sensitivity)
        {
            _strikesRemaining--;
            _nextStrikeTime = Time.time + Random.Range(gapBetweenStrikesSeconds.x, gapBetweenStrikesSeconds.y);

            var source = EnsureWindChime();
            if (!source) return;

            var clip = _clips.Length == 1 ? _clips[0] : _clips.Where(c => c != _lastClip).ElementAt(
                Random.Range(0, _clips.Length - 1));
            _lastClip = clip;

            var audibility = Mathf.InverseLerp(windChimeThreshold, 1f, sensitivity);
            source.pitch = 1f + Random.Range(-0.01f, 0.01f);
            source.PlayOneShot(clip, windChimeVolume * audibility * _strikeGain);
            _strikeGain *= Random.Range(0.5f, 0.8f);
        }

        /// <summary>
        ///     風鈴の音源を聞き手の近くに用意する。カメラがシーンごとに違うため、鳴らすときに探す
        /// </summary>
        private AudioSource EnsureWindChime()
        {
            if (_windChime) return _windChime;
            var listener = FindAnyObjectByType<AudioListener>();
            if (!listener) return null;

            var go = new GameObject("Wind Chime");
            go.transform.SetParent(listener.transform, false);
            go.transform.localPosition = windChimeOffset;
            _windChime = go.AddComponent<AudioSource>();
            _windChime.playOnAwake = false;
            _windChime.outputAudioMixerGroup = windChimeOutput;
            _windChime.spatialBlend = 0.6f;
            _windChime.dopplerLevel = 0f;
            _windChime.minDistance = 3f;
            _windChime.maxDistance = 30f;
            _windChime.reverbZoneMix = 1f;
            _windChime.priority = 64;
            return _windChime;
        }

        [Button("夕涼みを切り替え")]
        private void ToggleForceYusuzumi()
        {
            forceYusuzumi = !forceYusuzumi;
        }
    }
}
