using System;
using LitMotion;
using Sirenix.OdinInspector;
using UnityEngine;
using UnityEngine.Playables;

namespace Features.Gesture_Effect.Scripts
{
    [Serializable]
    public class RamuneGesturePlayer
    {
        [SerializeField] private PlayableDirector director;
        [SerializeField] private GameObject hand;
        [SerializeField] private Material handMat;
        [SerializeField] private GameObject bottle;

        [Title("ボトル落下アニメーション")] [SerializeField]
        private float bottleUpY = 8f;

        [SerializeField] private float bottleDownY = -8f;
        [SerializeField] private float bottleDropDuration = 0.5f;

        [Title("手出現アニメーション")] [SerializeField] private float handAppearDuration = 0.2f;

        // ボトルが落下しているかどうか
        private bool _isBottleDropped;

        public void Initialize()
        {
            _isBottleDropped = false;
            director.Stop();
            hand.SetActive(false);
            bottle.SetActive(false);
        }

        /// <summary>
        ///     ラムネを開ける準備が完了しているかを設定する
        /// </summary>
        /// <param name="isReady"></param>
        [Button]
        public void SetReadyOpen(bool isReady)
        {
            var bottlePos = bottle.transform.position;

            // 開ける準備が完了していて，まだボトルが落下していないなら
            if (isReady && !_isBottleDropped)
            {
                // ボトルを落下させて見えるようにする
                // 手も見えるようにする
                _isBottleDropped = true;
                
                bottle.SetActive(true);
                hand.SetActive(true);
                LSequence.Create()
                    .Append(
                        LMotion.Create(bottleUpY, 0f, bottleDropDuration)
                            .WithEase(Ease.OutSine)
                            .Bind(v => bottle.transform.position = bottlePos + new Vector3(0f, v, 0f))
                    )
                    .Join(
                        LMotion.Create(0f, 1f, handAppearDuration)
                            .Bind(v =>
                            {
                                var col = handMat.color;
                                col.a = v;
                                handMat.color = col;
                            })
                    )
                    .Run();
            }
            else if (!isReady && _isBottleDropped)
            {
                // ボトルを下に落として見えなくする
                _isBottleDropped = false;
                LSequence.Create()
                    .Append(
                        LMotion.Create(0f, bottleDownY, bottleDropDuration)
                            .WithEase(Ease.InSine)
                            .WithOnComplete(() =>
                            {
                                bottle.SetActive(false);
                                bottle.transform.position = bottlePos;
                            })
                            .Bind(v => bottle.transform.position = bottlePos + new Vector3(0, v, 0))
                    )
                    .Join(
                        LMotion.Create(1f, 0f, handAppearDuration)
                            .WithOnComplete(() => hand.SetActive(false))
                            .Bind(v =>
                            {
                                var col = handMat.color;
                                col.a = v;
                                handMat.color = col;
                            })
                    )
                    .Run();
            }
        }

        [Button]
        public void PlayOpenAnimation()
        {
            Debug.Assert(_isBottleDropped, "ボトルが落下していない状態でラムネを開けるアニメーションを再生しようとしました。");
            director.Play();
        }
    }
}