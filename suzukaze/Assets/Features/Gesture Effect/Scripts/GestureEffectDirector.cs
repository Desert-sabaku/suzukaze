using System;
using System.Threading;
using Cysharp.Threading.Tasks;
using LitMotion;
using Sirenix.OdinInspector;
using Suzukaze.Gesture;
using Suzukaze.Gesture.Protocol;
using Unity.Mathematics;
using UnityEngine;
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

        [Title("現在の状態")] [ReadOnly] [ShowInInspector]
        private bool _isAogiPlaying;

        [ReadOnly] [ShowInInspector] private bool _isUchimizuPlaying;

        private GestureReceiverBehaviour _gestureReceiver;
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
        }

        private void OnGestureStateChanged(StateView state)
        {
            // 追跡が切れると Gesture は None、Action は null になるため、ここで自然に停止する
            SetAogiPlaying(state.Gesture == ContinuousGesture.Fanning);

            ramune.SetAnimState(state.Action == Action.Ramune
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
                    ramune.SetAnimState(RamuneGesturePlayer.AnimState.Open);
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

        private void SetUchimizuVisible(bool visible)
        {
            if (_uchimizuRenderer) _uchimizuRenderer.enabled = visible;
            uchimizuPlayer.enabled = visible;
        }
    }
}
