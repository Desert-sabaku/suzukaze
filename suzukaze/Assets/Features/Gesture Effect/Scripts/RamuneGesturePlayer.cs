using System;
using LitMotion;
using Sirenix.OdinInspector;
using UnityEngine;

namespace Features.Gesture_Effect.Scripts
{
    [Serializable]
    public class RamuneGesturePlayer
    {
        public enum AnimState
        {
            None,
            ReadyOpen,
            Open
        }

        [SerializeField] private RamuneOpenEffect ramune;
        [SerializeField] private GameObject hand;
        [SerializeField] private Material handMat;
        [SerializeField] private GameObject bottle;

        [Title("ボトル落下アニメーション")] [SerializeField]
        private float bottleUpY = 8f;

        [SerializeField] private float bottleDownY = -8f;
        [SerializeField] private float bottleDropDuration = 0.5f;

        [Title("手出現アニメーション")] [SerializeField] private float handAppearDuration = 0.2f;
        [SerializeField] private float handDropDuration = 0.2f;
        [SerializeField] private float handDropY = 2f;

        // ボトルが落下しているかどうか
        private bool _isBottleDropped;
        private AnimState _state;

        public void Initialize()
        {
            _isBottleDropped = false;
            ramune.Close();
            hand.SetActive(false);
            bottle.SetActive(false);
        }

        [Button]
        public void SetAnimState(AnimState state)
        {
            if (state != _state)
            {
                if (state == AnimState.Open)
                {
                    ramune.Open();

                    var handPos = hand.transform.localPosition;
                    LMotion.Create(0f, -handDropY, handDropDuration)
                        .WithEase(Ease.InSine)
                        .WithOnComplete(() => hand.transform.localPosition = handPos)
                        .Bind(v => hand.transform.localPosition = handPos + new Vector3(0f, v, 0f));
                }
                else
                {
                    ramune.Close();
                }

                if (_state != AnimState.ReadyOpen && state == AnimState.ReadyOpen)
                {
                    hand.SetActive(true);
                    var motion = LMotion.Create(0f, 1f, handAppearDuration)
                        .WithEase(Ease.OutSine);
                    if (_state == AnimState.None) motion.WithDelay(bottleDropDuration * 0.8f);
                    motion
                        .Bind(v =>
                        {
                            var handCol = handMat.color;
                            handCol.a = v;
                            handMat.color = handCol;
                        });
                }
                else if (_state == AnimState.ReadyOpen && state != AnimState.ReadyOpen)
                {
                    LMotion.Create(1f, 0f, handAppearDuration)
                        .WithEase(Ease.InSine)
                        .WithOnComplete(() => hand.SetActive(false))
                        .Bind(v =>
                        {
                            var handCol = handMat.color;
                            handCol.a = v;
                            handMat.color = handCol;
                        });
                }

                SetBottleAppear(state is AnimState.ReadyOpen or AnimState.Open);
            }

            _state = state;
        }

        /// <summary>
        ///     ラムネを表示するべきかどうかを設定する
        /// </summary>
        /// <param name="isBottleAppear"></param>
        private void SetBottleAppear(bool isBottleAppear)
        {
            var bottlePos = bottle.transform.position;

            switch (isBottleAppear)
            {
                // 開ける準備が完了していて，まだボトルが落下していないなら
                case true when !_isBottleDropped:
                    // ボトルを落下させて見えるようにする
                    // 手も見えるようにする
                    _isBottleDropped = true;

                    bottle.SetActive(true);
                    LMotion.Create(bottleUpY, 0f, bottleDropDuration)
                        .WithEase(Ease.OutSine)
                        .Bind(v => bottle.transform.position = bottlePos + new Vector3(0f, v, 0f));
                    break;
                case false when _isBottleDropped:
                    // ボトルを下に落として見えなくする
                    _isBottleDropped = false;

                    LMotion.Create(0f, bottleDownY, bottleDropDuration)
                        .WithEase(Ease.InSine)
                        .WithOnComplete(() =>
                        {
                            bottle.SetActive(false);
                            bottle.transform.position = bottlePos;
                        })
                        .Bind(v => bottle.transform.position = bottlePos + new Vector3(0, v, 0));
                    break;
            }
        }
    }
}