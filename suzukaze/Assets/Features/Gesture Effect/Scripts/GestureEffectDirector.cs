using System;
using System.Linq;
using Cysharp.Threading.Tasks;
using Features.Common.Scripts;
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
    public class GestureEffectDirector : MonoBehaviour
    {
        private static readonly int AlphaPropId = Shader.PropertyToID("_Alpha");

        [Title("全体設定")] [SerializeField] [InfoBox("上書き可能な所作の種類")]
        private Gestures[] overridableGestures = { Gestures.Yusuzumi, Gestures.Aogi };

        [Title("打ち水")] [SerializeField] [ChildGameObjectsOnly]
        private AlembicStreamPlayer uchimizuPlayer;

        [SerializeField] private Material uchimizuMat;
        [SerializeField] private float uchimizuDuration = 2f;
        [SerializeField] private float uchimizuPosRandomRange = 0.5f;

        [Title("扇ぎ")] [SerializeField] [ChildGameObjectsOnly]
        private VisualEffect aogiVfx;
        
        [Title("ラムネ")] [SerializeField] private RamuneGesturePlayer ramune;

        private GestureReceiverBehaviour _gestureReceiver;

        [Title("現在の所作")] [ReadOnly] [ShowInInspector]
        private Gestures _gestures;

        private Random _random;
        private float3 _startUchimizuPos;
        private MeshRenderer _uchimizuRenderer;

        private void Start()
        {
            _uchimizuRenderer = uchimizuPlayer.GetComponentInChildren<MeshRenderer>();
            
            SetUchimizuEnabled(false);
            _startUchimizuPos = uchimizuPlayer.transform.position;
            _random = new Random((uint)DateTime.Now.Ticks);
            aogiVfx.Stop();
            ramune.Initialize();
        }
        
        private void SetUchimizuEnabled(bool uchimizuEnable)
        {
            if (_uchimizuRenderer) _uchimizuRenderer.enabled = uchimizuEnable;
            uchimizuPlayer.enabled = uchimizuEnable;
        }

        private void OnEnable()
        {
            if (_gestureReceiver) return;
            _gestureReceiver = GestureReceiverBehaviour.GetOrCreate();
            _gestureReceiver.Events.StateChanged += OnGestureStateChanged;
            _gestureReceiver.Events.Occurred += OnGestureOccurred;
        }

        private void OnDisable()
        {
            if (!_gestureReceiver) return;
            _gestureReceiver.Events.StateChanged -= OnGestureStateChanged;
            _gestureReceiver.Events.Occurred -= OnGestureOccurred;
            _gestureReceiver = null;
        }

        [Button("Play Effect")]
        public async UniTask PlayEffect(Gestures gesture, bool force = false)
        {
            // すでに再生中の所作が上書き可能な所作でない場合、forceがtrueでない限り警告を出す
            if (!overridableGestures.Contains(_gestures) && !force)
            {
                Debug.LogWarning($"Gesture {_gestures} is already playing. Use force=true to override.");
                return;
            }

            _gestures = gesture;

            switch (gesture)
            {
                case Gestures.Uchimizu:
                    await PlayUchimizu();
                    _gestures = Gestures.Yusuzumi;
                    break;
                case Gestures.Aogi:
                    await PlayAogi();
                    // すでに_gesturesがGestures.Aogi以外になっているので、ここで変更する必要はない
                    break;
                case Gestures.Rei:
                case Gestures.Yusuzumi:
                case Gestures.Ramune:
                default:
                    Debug.LogWarning($"Gesture {gesture} is not implemented.");
                    _gestures = Gestures.Yusuzumi;
                    break;
            }
        }

        private async UniTask PlayAogi()
        {
            if (!aogiVfx)
            {
                Debug.LogError("Aogi VFX is not assigned.");
                return;
            }

            aogiVfx.Play();
            // TODO: これでいいのかはわからない
            await UniTask.WaitWhile(() => _gestures == Gestures.Aogi);
            aogiVfx.Stop();
        }

        private async UniTask PlayUchimizu()
        {
            if (!uchimizuPlayer || !uchimizuMat)
            {
                Debug.LogError("Uchimizu player or material is not assigned.");
                return;
            }
            
            SetUchimizuEnabled(true);
            uchimizuPlayer.transform.position = _startUchimizuPos + _random.NextFloat3(
                new float3(-uchimizuPosRandomRange, 0f, -uchimizuPosRandomRange),
                new float3(uchimizuPosRandomRange, 0f, uchimizuPosRandomRange)
            );

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
                .Run();

            SetUchimizuEnabled(false);
            uchimizuMat.SetFloat(AlphaPropId, 1f);
        }

        private void OnGestureStateChanged(StateView state)
        {
            if (!state.Tracking) return;

            switch (state.Gesture)
            {
                case ContinuousGesture.Fanning:
                    PlayEffect(Gestures.Aogi).Forget();
                    break;
                case ContinuousGesture.Bow:
                case ContinuousGesture.None:
                case ContinuousGesture.Unspecified:
                case ContinuousGesture.Relaxing:
                default:
                    break;
            }
            
            if (state.Action is Action.Ramune)
            {
                ramune.SetAnimState(state.Phase switch
                {
                    Phase.Forming or Phase.Ready => RamuneGesturePlayer.AnimState.ReadyOpen,
                    Phase.Opened or Phase.WaitRelease => RamuneGesturePlayer.AnimState.Open,
                    _ => RamuneGesturePlayer.AnimState.None
                });
            }
            else
            {
                ramune.SetAnimState(RamuneGesturePlayer.AnimState.None);
            }
        }

        private bool OnGestureOccurred(string sessionId, Event events)
        {
            switch (events.Gesture)
            {
                case OccurrenceGesture.Ramune:
                    ramune.SetAnimState(RamuneGesturePlayer.AnimState.Open);
                    break;
                case OccurrenceGesture.Uchimizu:
                    PlayEffect(Gestures.Uchimizu).Forget();
                    break;
                case OccurrenceGesture.Unspecified:
                    break;
                default:
                    throw new ArgumentOutOfRangeException();
            }

            return true;
        }
    }
}