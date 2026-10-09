using System.Linq;
using Suzukaze.Fan;
using UnityEngine;

namespace Features.Sound.Scripts
{
    /// <summary>
    ///     シーン内に置く 1 個体分の音源。時刻に応じた活動度で鳴いたり休んだりする
    /// </summary>
    [RequireComponent(typeof(AudioSource))]
    public class CreatureSoundEmitter : MonoBehaviour
    {
        private const float SilentGain = 0.001f;
        private const float MaxCutoffHz = 22000f;

        /// <summary>
        ///     感覚が最も鋭いときに、高音の減衰を計算する距離に掛ける倍率
        /// </summary>
        private const float SharpenedDistanceScale = 0.35f;

        private static AudioListener _listener;

        [SerializeField] private CreatureSoundProfile profile;
        [SerializeField] [Range(0f, 2f)] private float volumeScale = 1f;

        private float _activity;
        private AnimationCurve _airAbsorption;
        private int _boutRemaining;
        private bool _isPaused;
        private AudioClip _lastClip;
        private float _loopGain;
        private AudioLowPassFilter _lowPass;
        private float _nextActionTime;
        private float _noiseSeed;
        private float _pitch = 1f;
        private bool _singing;
        private AudioSource _source;

        /// <summary>
        ///     ループの個体が鳴き始める活動度。個体ごとにずらし、夕方に少しずつ鳴き出すようにする
        /// </summary>
        private float _threshold;

        private WindFanController _wind;

        public CreatureSoundProfile Profile => profile;

        private void Awake()
        {
            _source = GetComponent<AudioSource>();
            if (!profile)
            {
                Debug.LogWarning($"[Sound] {name} に CreatureSoundProfile が設定されていません。", this);
                enabled = false;
                return;
            }

            _pitch = 1f + Random.Range(-profile.individualPitchVariance, profile.individualPitchVariance);
            _threshold = Random.Range(0f, 0.5f);
            _noiseSeed = Random.Range(0f, 1000f);
            Configure(_source, profile);
            if (profile.windDrivenLoop)
                _wind = FindObjectsByType<WindFanController>()
                    .FirstOrDefault(candidate => candidate.gameObject.scene == gameObject.scene);

            _lowPass = GetComponent<AudioLowPassFilter>();
            var absorbs = profile.airAbsorption && profile.spatialBlend > 0f;
            if (absorbs && !_lowPass) _lowPass = gameObject.AddComponent<AudioLowPassFilter>();
            if (_lowPass) _lowPass.enabled = absorbs;
            if (absorbs) _airAbsorption = SpatialCurves.AirAbsorption();
        }

        private void Update()
        {
            if (!profile.HasClips) return;

            var target = profile.Activity(SoundTimeOfDay.CurrentHour);
            _activity += (target - _activity) * (1f - Mathf.Exp(-Time.deltaTime / profile.activitySmoothing));

            if (profile.mode == CreatureSoundProfile.PlaybackMode.Loop)
            {
                if (!profile.windDrivenLoop) UpdateLoop();
            }
            else
            {
                UpdateCall();
            }

            if (_airAbsorption != null) UpdateAirAbsorption();
        }

        private void LateUpdate()
        {
            // SceneWindDirector writes this frame's wind in Update.
            if (profile && profile.HasClips && profile.windDrivenLoop
                && profile.mode == CreatureSoundProfile.PlaybackMode.Loop) UpdateLoop();
        }

        private void OnEnable()
        {
            if (!profile || !profile.HasClips) return;

            // シーン開始時はフェードせず、その時刻の鳴き具合から始める
            _activity = profile.Activity(SoundTimeOfDay.CurrentHour);

            if (profile.mode == CreatureSoundProfile.PlaybackMode.Loop)
            {
                var clip = profile.PickClip(null);
                _source.clip = clip;
                _source.loop = true;
                _source.pitch = _pitch;
                _source.time = Random.Range(0f, clip.length);
                _singing = true;
                _nextActionTime = Time.time + RandomRange(profile.singSeconds);
                _loopGain = LoopTargetGain();
                _source.volume = profile.volume * volumeScale * _loopGain * profile.WindVolumeScale;
                _source.Play();
                _isPaused = false;
            }
            else
            {
                // 同じ種類の個体が一斉に鳴き出さないようにずらす
                _nextActionTime = Time.time + Random.Range(0f, profile.restSeconds.y);
            }
        }

        private void OnDisable()
        {
            if (_source) _source.Stop();
            _boutRemaining = 0;
        }

        private void OnDrawGizmos()
        {
            Gizmos.color = GizmoColor();
            Gizmos.DrawSphere(transform.position, 0.3f);
        }

        private void OnDrawGizmosSelected()
        {
            if (!profile) return;
            Gizmos.color = GizmoColor();
            Gizmos.DrawWireSphere(transform.position, profile.minDistance);
            Gizmos.color *= new Color(1f, 1f, 1f, 0.3f);
            Gizmos.DrawWireSphere(transform.position, profile.maxDistance);
        }

        private void UpdateCall()
        {
            if (_source.isPlaying || Time.time < _nextActionTime) return;

            if (_boutRemaining > 0)
            {
                _boutRemaining--;
                PlayCall();
                return;
            }

            // 活動度が低い時間帯ほど鳴く機会を見送り、間隔が空く
            if (Random.value < _activity)
            {
                _boutRemaining = Random.Range(profile.callsPerBout.x, profile.callsPerBout.y + 1) - 1;
                PlayCall();
            }
            else
            {
                _nextActionTime = Time.time + RandomRange(profile.restSeconds);
            }
        }

        private void PlayCall()
        {
            var clip = profile.PickClip(_lastClip);
            if (!clip) return;
            _lastClip = clip;

            var pitch = _pitch * (1f + Random.Range(-profile.callPitchVariance, profile.callPitchVariance));
            var gainDb = Random.Range(-profile.callVolumeVarianceDb, 0f);
            _source.clip = clip;
            _source.loop = false;
            _source.pitch = pitch;
            _source.volume = profile.volume * volumeScale * Mathf.Pow(10f, gainDb / 20f);
            _source.Play();

            var wait = _boutRemaining > 0 ? RandomRange(profile.gapInBoutSeconds) : RandomRange(profile.restSeconds);
            _nextActionTime = Time.time + clip.length / pitch + wait;
        }

        private void UpdateLoop()
        {
            var hasPause = profile.pauseSeconds.y > 0f;
            if (hasPause && Time.time >= _nextActionTime)
            {
                _singing = !_singing;
                _nextActionTime = Time.time + RandomRange(_singing ? profile.singSeconds : profile.pauseSeconds);
            }

            _loopGain = Mathf.MoveTowards(_loopGain, LoopTargetGain(), Time.deltaTime / profile.fadeSeconds);
            _source.volume = profile.volume * volumeScale * _loopGain * profile.WindVolumeScale;

            // 聞こえないあいだは止めておき、ボイスを他の音源に譲る
            var silent = _loopGain <= SilentGain;
            switch (silent)
            {
                case true when !_isPaused:
                    _source.Pause();
                    _isPaused = true;
                    break;
                case false when _isPaused:
                    _source.UnPause();
                    _isPaused = false;
                    break;
            }
        }

        /// <summary>
        ///     聞き手からの距離に応じて高音を削る
        /// </summary>
        private void UpdateAirAbsorption()
        {
            if (!_listener) _listener = FindAnyObjectByType<AudioListener>();
            if (!_listener) return;

            // 感覚が鋭いときは遠くの音も近くにあるように澄んで聞こえる
            var distance = Vector3.Distance(transform.position, _listener.transform.position) *
                           Mathf.Lerp(1f, SharpenedDistanceScale, SoundSensitivity.Level);
            _lowPass.cutoffFrequency = MaxCutoffHz * _airAbsorption.Evaluate(distance);
        }

        private float LoopTargetGain()
        {
            if (!_singing) return 0f;
            var activity = Mathf.InverseLerp(_threshold, 1f, _activity);
            var noise = Mathf.PerlinNoise(Time.time / profile.modulationPeriod, _noiseSeed);
            var windPower = _wind && _wind.isActiveAndEnabled ? _wind.CurrentPower : 0f;
            return activity * (1f - profile.modulationDepth * noise) * profile.WindGain(windPower);
        }

        private Color GizmoColor()
        {
            var group = profile && profile.output ? profile.output.name : "";
            return group switch
            {
                "Cicadas" => new Color(1f, 0.6f, 0.1f),
                "Insects" => new Color(0.4f, 0.4f, 1f),
                "Birds" => new Color(0.2f, 0.9f, 0.3f),
                "Ambient" => new Color(0.2f, 0.8f, 1f),
                _ => Color.white
            };
        }

        private static float RandomRange(Vector2 range)
        {
            return Random.Range(range.x, range.y);
        }

        /// <summary>
        ///     プロファイルの立体音響の設定を AudioSource に反映する
        /// </summary>
        public static void Configure(AudioSource source, CreatureSoundProfile profile)
        {
            source.playOnAwake = false;
            source.outputAudioMixerGroup = profile.output;
            source.loop = profile.mode == CreatureSoundProfile.PlaybackMode.Loop;
            source.priority = profile.priority;
            source.spatialBlend = profile.spatialBlend;
            source.dopplerLevel = 0f;
            source.spread = profile.spread;
            source.reverbZoneMix = 1f;
            source.minDistance = profile.minDistance;
            source.maxDistance = profile.maxDistance;
            source.rolloffMode = AudioRolloffMode.Custom;
            source.SetCustomCurve(AudioSourceCurveType.CustomRolloff,
                SpatialCurves.InverseDistance(profile.minDistance, profile.maxDistance));
        }
    }
}