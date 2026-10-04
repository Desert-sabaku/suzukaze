using System;
using Cysharp.Threading.Tasks;
using Features.Common.Scripts;
using LitMotion;
using Sirenix.OdinInspector;
using Unity.Mathematics;
using UnityEngine;
using UnityEngine.Formats.Alembic.Importer;
using Random = Unity.Mathematics.Random;

namespace Features.Gesture_Effect.Scripts
{
    /// <summary>
    ///     所作によるエフェクトを制御するためのコンポーネント
    /// </summary>
    public class GestureEffectDirector : MonoBehaviour
    {
        private static readonly int AlphaPropId = Shader.PropertyToID("_Alpha");

        [Title("打ち水")] [SerializeField] private AlembicStreamPlayer uchimizuPlayer;

        [SerializeField] private Material uchimizuMat;
        [SerializeField] private float uchimizuDuration = 2f;
        [SerializeField] private float uchimizuPosRandomRange = 0.5f;

        private Gestures _gestures;
        private float _progress;
        private Random _random;
        private float3 _startUchimizuPos;

        private void Start()
        {
            uchimizuPlayer.enabled = false;
            _startUchimizuPos = uchimizuPlayer.transform.position;
            _random = new Random((uint)DateTime.Now.Ticks);
        }

        [Button("Play Effect")]
        public async UniTask PlayEffect(Gestures gesture)
        {
            _gestures = gesture;
            _progress = 0f;

            switch (gesture)
            {
                case Gestures.Uchimizu:
                {
                    if (!uchimizuPlayer || !uchimizuMat)
                    {
                        Debug.LogError("Uchimizu player or material is not assigned.");
                        return;
                    }

                    uchimizuPlayer.enabled = true;
                    uchimizuPlayer.transform.position = _startUchimizuPos + _random.NextFloat3(
                        new float3(-uchimizuPosRandomRange, 0f, -uchimizuPosRandomRange),
                        new float3(uchimizuPosRandomRange, 0f, uchimizuPosRandomRange)
                    );

                    var startTime = uchimizuPlayer.StartTime;
                    var endTime = uchimizuPlayer.EndTime;

                    await LSequence.Create()
                        .Join(LMotion.Create(0f, 1f, uchimizuDuration)
                            .Bind(v =>
                            {
                                uchimizuPlayer.CurrentTime = math.lerp(startTime, endTime, v);
                                _progress = math.lerp(0f, 0.8f, v);
                            })
                        )
                        .AppendInterval(uchimizuDuration * 0.8f)
                        .Append(LMotion.Create(1f, 0f, uchimizuDuration * 0.2f)
                            .Bind(v =>
                            {
                                uchimizuMat.SetFloat(AlphaPropId, v);
                                _progress = 0.8f + math.lerp(0f, 0.2f, v);
                            })
                        )
                        .Run();

                    uchimizuPlayer.enabled = false;
                    uchimizuMat.SetFloat(AlphaPropId, 1f);
                    break;
                }
                case Gestures.Yusuzumi:
                case Gestures.Ramune:
                case Gestures.Aogi:
                case Gestures.Rei:
                default:
                    Debug.LogWarning($"Gesture {gesture} is not implemented.");
                    break;
            }
        }
    }
}