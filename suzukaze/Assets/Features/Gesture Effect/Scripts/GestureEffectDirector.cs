using System;
using System.Threading;
using Cysharp.Threading.Tasks;
using LitMotion;
using Sirenix.OdinInspector;
using Suzukaze.Gesture;
using Suzukaze.Gesture.Protocol;
using Unity.Mathematics;
using UnityEngine;
using UnityEngine.Audio;
using UnityEngine.Formats.Alembic.Importer;
using UnityEngine.VFX;
using Action = Suzukaze.Gesture.Protocol.Action;
using Event = Suzukaze.Gesture.Protocol.Event;
using Random = Unity.Mathematics.Random;

namespace Features.Gesture_Effect.Scripts
{
    /// <summary>
    ///     所作によるエフェクトを制御するためのコンポーネント
    /// </summary>
    /// <remarks>
    ///     継続的なエフェクト（扇ぎ・ラムネ）は受信した最新の状態から毎回導出し、
    ///     単発のエフェクト（打ち水）はイベントを受けて一度だけ再生する。
    ///     エフェクト同士は状態を共有しない。
    ///     音はエフェクトの再生に合わせて鳴らす。
    /// </remarks>
    public class GestureEffectDirector : MonoBehaviour
    {
        private static readonly int AlphaPropId = Shader.PropertyToID("_Alpha");

        [Title("打ち水")] [SerializeField] [ChildGameObjectsOnly]
        private AlembicStreamPlayer uchimizuPlayer;

        [SerializeField] private Material uchimizuMat;
        [SerializeField] private float uchimizuDuration = 2f;
        [SerializeField] private float uchimizuPosRandomRange = 0.5f;

        [Title("扇ぎ")] [SerializeField] [ChildGameObjectsOnly]
        private VisualEffect aogiVfx;

        [Title("ラムネ")] [SerializeField] private RamuneGesturePlayer ramune;

        [Tooltip("ラムネの進行状態が途切れてから表示を消すまでの猶予 (秒)。認識の一瞬の欠けで出し直さないようにする")]
        [SerializeField] [Min(0f)] private float ramuneExitGraceSeconds = 0.3f;

        [Title("音")] [SerializeField] private AudioMixerGroup soundOutput;

        [SerializeField] private AudioClip uchimizuClip;

        [SerializeField] [Range(0f, 1f)] private float uchimizuVolume = 0.8f;

        [Tooltip("ループして鳴らす")] [SerializeField]
        private AudioClip aogiLoopClip;

        [SerializeField] [Range(0f, 1f)] private float aogiVolume = 0.6f;

        [Tooltip("扇ぎ始め・やめたときに音量を変える時間 (秒)")] [SerializeField] [Min(0.01f)]
        private float aogiFadeSeconds = 0.3f;

        [SerializeField] private AudioClip ramuneOpenClip;

        [SerializeField] [Range(0f, 1f)] private float ramuneOpenVolume = 0.8f;

        [Title("現在の状態")] [ReadOnly] [ShowInInspector]
        private bool _isAogiPlaying;

        [ReadOnly] [ShowInInspector] private bool _isUchimizuPlaying;

        private AudioSource _aogiSource;
        private GestureReceiverBehaviour _gestureReceiver;
        private AudioSource _oneShotSource;

        // ラムネの表示を消す予定時刻。消す予定がないときは null
        private float? _ramuneExitAt;

        private Random _random;
        private float3 _startUchimizuPos;
        private MeshRenderer _uchimizuRenderer;

        // OnEnable で現在の状態を反映するため、初期化は Start ではなく Awake で行う
        private void Awake()
        {
            _random = new Random((uint)DateTime.Now.Ticks | 1u);
            _uchimizuRenderer = uchimizuPlayer.GetComponentInChildren<MeshRenderer>();
            _startUchimizuPos = uchimizuPlayer.transform.position;
            SetUchimizuVisible(false);
            aogiVfx.Stop();
            ramune.Initialize();
            InitializeSound();
        }

        private void Update()
        {
            if (_ramuneExitAt is { } exitAt && Time.unscaledTime >= exitAt)
            {
                _ramuneExitAt = null;
                ramune.SetAnimState(RamuneGesturePlayer.AnimState.None);
            }

            if (!_aogiSource) return;
            var target = _isAogiPlaying ? aogiVolume : 0f;
            _aogiSource.volume = Mathf.MoveTowards(_aogiSource.volume, target, aogiVolume * Time.deltaTime / aogiFadeSeconds);
            if (_aogiSource.volume <= 0f && _aogiSource.isPlaying) _aogiSource.Stop();
        }

        private void OnEnable()
        {
            _gestureReceiver = GestureReceiverBehaviour.GetOrCreate();
            _gestureReceiver.Events.StateChanged += OnGestureStateChanged;
            _gestureReceiver.Events.Occurred += OnGestureOccurred;
            OnGestureStateChanged(_gestureReceiver.Events.CurrentState);
        }

        private void OnDisable()
        {
            if (_gestureReceiver)
            {
                _gestureReceiver.Events.StateChanged -= OnGestureStateChanged;
                _gestureReceiver.Events.Occurred -= OnGestureOccurred;
                _gestureReceiver = null;
            }

            SetAogiPlaying(false);
            _ramuneExitAt = null;
            if (_aogiSource)
            {
                _aogiSource.Stop();
                _aogiSource.volume = 0f;
            }
        }

        private void OnGestureStateChanged(StateView state)
        {
            // 追跡が切れると Gesture は None、Action は null になるため、ここで自然に停止する
            SetAogiPlaying(state.Gesture == ContinuousGesture.Fanning);

            UpdateRamuneState(state.Action == Action.Ramune
                ? state.Phase switch
                {
                    Phase.Forming or Phase.Ready => RamuneGesturePlayer.AnimState.ReadyOpen,
                    Phase.Opened or Phase.WaitRelease => RamuneGesturePlayer.AnimState.Open,
                    _ => RamuneGesturePlayer.AnimState.None
                }
                : RamuneGesturePlayer.AnimState.None);
        }

        private bool OnGestureOccurred(string sessionId, Event occurrence)
        {
            switch (occurrence.Gesture)
            {
                case OccurrenceGesture.Ramune:
                    // 開栓音はイベントで一度だけ鳴らす。状態の揺れで鳴り直さない
                    _ramuneExitAt = null;
                    ramune.SetAnimState(RamuneGesturePlayer.AnimState.Open);
                    PlayOneShot(ramuneOpenClip, ramuneOpenVolume);
                    return true;
                case OccurrenceGesture.Uchimizu:
                    return TryPlayUchimizu();
                case OccurrenceGesture.Unspecified:
                default:
                    return false;
            }
        }

        [Button("扇ぎを切り替え")]
        private void SetAogiPlaying(bool playing)
        {
            if (playing == _isAogiPlaying || !aogiVfx) return;
            _isAogiPlaying = playing;
            if (playing) aogiVfx.Play();
            else aogiVfx.Stop();
            // 音量は Update でなめらかに変える
            if (playing && _aogiSource && _aogiSource.clip && !_aogiSource.isPlaying) _aogiSource.Play();
        }

        /// <summary>
        ///     受信した状態からラムネの表示を切り替える。表示を消すときだけ猶予を置く
        /// </summary>
        private void UpdateRamuneState(RamuneGesturePlayer.AnimState state)
        {
            if (state != RamuneGesturePlayer.AnimState.None)
            {
                _ramuneExitAt = null;
                ramune.SetAnimState(state);
            }
            else if (ramune.State != RamuneGesturePlayer.AnimState.None)
            {
                _ramuneExitAt ??= Time.unscaledTime + ramuneExitGraceSeconds;
            }
        }

        /// <summary>
        ///     打ち水を再生する。再生中の場合は何もしない。
        /// </summary>
        /// <returns>再生を開始した場合は true</returns>
        [Button("打ち水を再生")]
        public bool TryPlayUchimizu()
        {
            if (_isUchimizuPlaying) return false;
            if (!uchimizuPlayer || !uchimizuMat)
            {
                Debug.LogError("Uchimizu player or material is not assigned.");
                return false;
            }

            PlayUchimizuAsync(destroyCancellationToken).Forget();
            return true;
        }

        private async UniTaskVoid PlayUchimizuAsync(CancellationToken cancellationToken)
        {
            _isUchimizuPlaying = true;
            try
            {
                uchimizuPlayer.transform.position = _startUchimizuPos + _random.NextFloat3(
                    new float3(-uchimizuPosRandomRange, 0f, -uchimizuPosRandomRange),
                    new float3(uchimizuPosRandomRange, 0f, uchimizuPosRandomRange)
                );
                uchimizuMat.SetFloat(AlphaPropId, 1f);
                SetUchimizuVisible(true);
                PlayOneShot(uchimizuClip, uchimizuVolume);

                var startTime = uchimizuPlayer.StartTime;
                var endTime = uchimizuPlayer.EndTime;

                await LSequence.Create()
                    .Join(LMotion.Create(0f, 1f, uchimizuDuration)
                        .Bind(v => uchimizuPlayer.CurrentTime = math.lerp(startTime, endTime, v))
                    )
                    .AppendInterval(uchimizuDuration * 0.8f)
                    .Append(LMotion.Create(1f, 0f, uchimizuDuration * 0.2f)
                        .Bind(v => uchimizuMat.SetFloat(AlphaPropId, v))
                    )
                    .Run()
                    .ToUniTask(cancellationToken);
            }
            finally
            {
                // マテリアルはアセットなので、破棄時でも不透明度を元に戻す
                uchimizuMat.SetFloat(AlphaPropId, 1f);
                if (this) SetUchimizuVisible(false);
                _isUchimizuPlaying = false;
            }
        }

        private void InitializeSound()
        {
            // 所作への手応えとして確実に聞こえるよう、どちらも 2D で鳴らす
            _oneShotSource = CreateSource();
            _aogiSource = CreateSource();
            _aogiSource.clip = aogiLoopClip;
            _aogiSource.loop = true;
            _aogiSource.volume = 0f;
        }

        private AudioSource CreateSource()
        {
            var source = gameObject.AddComponent<AudioSource>();
            source.playOnAwake = false;
            source.outputAudioMixerGroup = soundOutput;
            source.spatialBlend = 0f;
            source.priority = 64;
            return source;
        }

        private void PlayOneShot(AudioClip clip, float volume)
        {
            if (_oneShotSource && clip) _oneShotSource.PlayOneShot(clip, volume);
        }

        private void SetUchimizuVisible(bool visible)
        {
            if (_uchimizuRenderer) _uchimizuRenderer.enabled = visible;
            uchimizuPlayer.enabled = visible;
        }
    }
}
