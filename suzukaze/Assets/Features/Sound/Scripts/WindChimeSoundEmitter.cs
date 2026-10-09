using System.Linq;
using System.Collections.Generic;
using System.Threading.Tasks;
using Sirenix.OdinInspector;
using Suzukaze.Fan;
using UnityEngine;
using UnityEngine.Audio;

namespace Features.Sound.Scripts
{
    [RequireComponent(typeof(AudioSource))]
    public class WindChimeSoundEmitter : MonoBehaviour
    {
        [Title("風鈴")] [Tooltip("未設定なら同じシーンの WindFanController を使う")]
        [SerializeField]
        private WindFanController wind;

        [Tooltip("空なら合成した風鈴の音を使う")] [SerializeField]
        private AudioClip[] windChimeClips;

        [SerializeField] private WindChimeRecordingBank recordings;

        [SerializeField] private AudioMixerGroup windChimeOutput;
        [SerializeField] [Range(0f, 1f)] private float windChimeVolume = 0.6f;

        [Tooltip("WindFanController.CurrentPower がこの値を超えると鳴る。夕涼みの所作には依存しない")]
        [SerializeField] [Range(0f, 1f)]
        private float windChimeThreshold = 0.35f;

        [Tooltip("風が吹いて風鈴が鳴る間隔 (秒)")] [SerializeField] [MinMaxSlider(0.5f, 20f, true)]
        private Vector2 windChimeIntervalSeconds = new(2.5f, 7f);

        [Tooltip("一度の風で舌が当たる回数")] [SerializeField]
        private Vector2Int strikesPerGust = new(1, 3);

        [SerializeField] [MinMaxSlider(0.05f, 1f, true)]
        private Vector2 gapBetweenStrikesSeconds = new(0.12f, 0.4f);

        [SerializeField, Range(0.1f, 1f)] private float strongWindIntervalScale = 0.45f;
        [SerializeField, Min(0)] private int strongWindExtraStrikes = 3;
        [SerializeField] private Vector2 playbackSpeedRange = new(0.94f, 1.06f);
        [SerializeField] private Vector2 strongRecordingSpeedRange = new(1.02f, 1.18f);

        [Tooltip("聞き手から見た風鈴の位置。軒先に吊るした風鈴を想定し、少し上の前方に置く")] [SerializeField]
        private Vector3 windChimeOffset = new(0.8f, 1.2f, 1.5f);

        private AudioClip[] _clips;
        private AudioClip _lastClip;
        private AudioSource _windChime;
        private AudioListener _listener;
        private float _nextGustTime;
        private float _nextStrikeTime;
        private int _strikesRemaining;
        private float _strikeGain;
        private bool _ownsClips;
        private sealed class ClipData
        {
            public float[] Samples;
            public int Channels;
            public int Frequency;
        }

        private sealed class PendingStrike
        {
            public Task<float[]> Samples;
            public ClipData Original;
            public string Name;
            public float Gain;
        }

        private readonly Dictionary<AudioClip, ClipData> _pcmClips = new();
        private readonly List<PendingStrike> _pendingStrikes = new();
        private readonly List<(AudioClip clip, float releaseTime)> _liveClips = new();
        [ShowInInspector, ReadOnly] public float CurrentPlaybackSpeed { get; private set; } = 1f;

        private void Awake()
        {
            _windChime = GetComponent<AudioSource>();
            if (!wind)
                wind = FindObjectsByType<WindFanController>(FindObjectsSortMode.None)
                    .FirstOrDefault(candidate => candidate.gameObject.scene == gameObject.scene);
            _listener = FindObjectsByType<AudioListener>(FindObjectsSortMode.None)
                .FirstOrDefault(candidate => candidate.isActiveAndEnabled && candidate.gameObject.scene == gameObject.scene);
            _clips = recordings ? recordings.shortStrikes.Where(clip => clip).ToArray()
                : windChimeClips?.Where(clip => clip).ToArray();
            _ownsClips = _clips == null || _clips.Length == 0;
            if (_ownsClips) _clips = WindChimeSynth.CreateClips();
            var allClips = recordings ? _clips.Concat(recordings.longStrikes) : _clips;
            foreach (var clip in allClips.Where(clip => clip).Distinct())
            {
                var samples = new float[clip.samples * clip.channels];
                if (clip.GetData(samples, 0))
                    _pcmClips.Add(clip, new ClipData { Samples = samples, Channels = clip.channels, Frequency = clip.frequency });
                else Debug.LogWarning($"[Sound] {clip.name} requires Decompress On Load for pitch-preserving playback.", clip);
            }
            _windChime.playOnAwake = false;
            _windChime.loop = false;
            if (windChimeOutput) _windChime.outputAudioMixerGroup = windChimeOutput;
        }

        private void OnEnable() => _nextGustTime = Time.time;

        private void LateUpdate()
        {
            CompletePendingStrikes();
            for (int i = _liveClips.Count - 1; i >= 0; i--)
                if (Time.unscaledTime >= _liveClips[i].releaseTime)
                {
                    Destroy(_liveClips[i].clip);
                    _liveClips.RemoveAt(i);
                }
            // Keep the emitter under Soundscape while retaining its listener-relative placement.
            if (_listener) transform.position = _listener.transform.TransformPoint(windChimeOffset);
            UpdateWindChime(wind && wind.isActiveAndEnabled ? wind.CurrentPower : 0f);
        }

        private void OnDisable()
        {
            _strikesRemaining = 0;
            if (_windChime) _windChime.Stop();
            _pendingStrikes.Clear();
            foreach (var entry in _liveClips) if (entry.clip) Destroy(entry.clip);
            _liveClips.Clear();
        }

        private void OnDestroy()
        {
            if (!_ownsClips || _clips == null) return;
            foreach (var clip in _clips) if (clip) Destroy(clip);
        }

        private void UpdateWindChime(float power)
        {
            if (_clips.Length == 0) return;

            if (power <= windChimeThreshold)
            {
                _strikesRemaining = 0;
                return;
            }

            if (_strikesRemaining > 0)
            {
                if (Time.time >= _nextStrikeTime) Strike(power);
                return;
            }

            if (Time.time < _nextGustTime) return;

            _strikesRemaining = Random.Range(strikesPerGust.x,
                strikesPerGust.y + Mathf.RoundToInt(strongWindExtraStrikes * WindLevel(power)) + 1);
            _strikeGain = Random.Range(0.6f, 1f);
            _nextGustTime = Time.time + Random.Range(windChimeIntervalSeconds.x, windChimeIntervalSeconds.y)
                * Mathf.Lerp(1f, strongWindIntervalScale, WindLevel(power));
            Strike(power);
        }

        /// <summary>
        ///     舌が 1 回ガラスに当たる。風の一吹きの中では、当たるたびに弱くなる
        /// </summary>
        private void Strike(float power)
        {
            _strikesRemaining--;
            _nextStrikeTime = Time.time + Random.Range(gapBetweenStrikesSeconds.x, gapBetweenStrikesSeconds.y)
                * Mathf.Lerp(1f, 0.75f, WindLevel(power));

            var source = _windChime;
            if (!source) return;

            var recordedPool = SelectRecordedPool(WindLevel(power));
            var pool = recordedPool ?? _clips;
            var candidates = pool.Where(c => c && c != _lastClip).ToArray();
            if (candidates.Length == 0) candidates = pool.Where(c => c).ToArray();
            if (candidates.Length == 0) return;
            var clip = candidates[Random.Range(0, candidates.Length)];
            _lastClip = clip;

            var audibility = Mathf.Lerp(0.4f, 1f, WindLevel(power));
            CurrentPlaybackSpeed = SelectPlaybackSpeed(WindLevel(power), recordedPool != null);
            source.pitch = 1f;
            float gain = windChimeVolume * audibility * _strikeGain;
            if (_pcmClips.TryGetValue(clip, out var original))
            {
                float speed = CurrentPlaybackSpeed;
                _pendingStrikes.Add(new PendingStrike
                {
                    Samples = Task.Run(() => PitchPreservingTimeStretch.Stretch(original.Samples, original.Channels, original.Frequency, speed)),
                    Original = original, Name = $"{clip.name}_RuntimeSpeed_{speed:F3}", Gain = gain
                });
            }
            else source.PlayOneShot(clip, gain);
            _strikeGain *= Random.Range(0.5f, 0.8f);
        }

        private float WindLevel(float power) => Mathf.InverseLerp(windChimeThreshold, 1f, power);

        private AudioClip[] SelectRecordedPool(float level)
        {
            if (!recordings || Random.value >= Mathf.Lerp(0.1f, 0.85f, level)) return null;
            var pool = recordings.longStrikes;
            return pool != null && pool.Length > 0 ? pool : null;
        }

        private float SelectPlaybackSpeed(float level, bool longRecording)
        {
            if (!longRecording) return Random.Range(playbackSpeedRange.x, playbackSpeedRange.y);
            float target = Mathf.Lerp(strongRecordingSpeedRange.x, strongRecordingSpeedRange.y, level);
            return Mathf.Clamp(target + Random.Range(-0.04f, 0.04f), strongRecordingSpeedRange.x, strongRecordingSpeedRange.y);
        }

        private void CompletePendingStrikes()
        {
            if (!wind || !wind.isActiveAndEnabled || wind.CurrentPower <= windChimeThreshold)
            {
                _pendingStrikes.Clear();
                return;
            }
            for (int i = 0; i < _pendingStrikes.Count;)
            {
                var pending = _pendingStrikes[i];
                if (!pending.Samples.IsCompleted) { i++; continue; }
                _pendingStrikes.RemoveAt(i);
                if (pending.Samples.IsFaulted) { Debug.LogException(pending.Samples.Exception, this); continue; }
                var samples = pending.Samples.Result;
                var clip = AudioClip.Create(pending.Name, samples.Length / pending.Original.Channels,
                    pending.Original.Channels, pending.Original.Frequency, false);
                clip.SetData(samples, 0);
                _windChime.PlayOneShot(clip, pending.Gain);
                _liveClips.Add((clip, Time.unscaledTime + clip.length + 0.25f));
            }
        }

        private void OnValidate()
        {
            playbackSpeedRange.x = Mathf.Clamp(playbackSpeedRange.x, 0.9f, 1.1f);
            playbackSpeedRange.y = Mathf.Clamp(playbackSpeedRange.y, playbackSpeedRange.x, 1.1f);
            strongRecordingSpeedRange.x = Mathf.Clamp(strongRecordingSpeedRange.x, 0.9f, 1.3f);
            strongRecordingSpeedRange.y = Mathf.Clamp(strongRecordingSpeedRange.y, strongRecordingSpeedRange.x, 1.3f);
            strikesPerGust.x = Mathf.Max(1, strikesPerGust.x);
            strikesPerGust.y = Mathf.Max(strikesPerGust.x, strikesPerGust.y);
        }
    }
}
