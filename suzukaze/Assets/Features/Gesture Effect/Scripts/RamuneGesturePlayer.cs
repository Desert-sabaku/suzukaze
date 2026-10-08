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

        // アニメーションの基準位置．再生途中の位置を基準にするとずれが蓄積するため，初期化時に一度だけ記録する
        private Vector3 _bottleBasePos;
        private Vector3 _handBaseLocalPos;

        // 状態が素早く切り替わったとき，古いモーションの OnComplete が新しい表示を打ち消さないようにキャンセルする
        private MotionHandle _bottleMotion;
        private MotionHandle _handFadeMotion;
        private MotionHandle _handDropMotion;

        public AnimState State { get; private set; }

        public void Initialize()
        {
            _isBottleDropped = false;
            _bottleBasePos = bottle.transform.position;
            _handBaseLocalPos = hand.transform.localPosition;
            ramune.Close();
            hand.SetActive(false);
            bottle.SetActive(false);
        }

        [Button]
        public void SetAnimState(AnimState state)
        {
            if (state != State)
            {
                if (state == AnimState.Open)
                {
                    ramune.Open();

                    var handPos = _handBaseLocalPos;
                    CancelMotion(ref _handDropMotion);
                    _handDropMotion = LMotion.Create(0f, -handDropY, handDropDuration)
                        .WithEase(Ease.InSine)
                        .WithOnComplete(() => hand.transform.localPosition = handPos)
                        .WithOnCancel(() => hand.transform.localPosition = handPos)
                        .Bind(v => hand.transform.localPosition = handPos + new Vector3(0f, v, 0f));
                }
                else
                {
                    ramune.Close();
                }

                if (State != AnimState.ReadyOpen && state == AnimState.ReadyOpen)
                {
                    hand.SetActive(true);
                    CancelMotion(ref _handFadeMotion);
                    var motion = LMotion.Create(0f, 1f, handAppearDuration)
                        .WithEase(Ease.OutSine);
                    if (State == AnimState.None) motion.WithDelay(bottleDropDuration * 0.8f);
                    _handFadeMotion = motion
                        .Bind(v =>
                        {
                            var handCol = handMat.color;
                            handCol.a = v;
                            handMat.color = handCol;
                        });
                }
                else if (State == AnimState.ReadyOpen && state != AnimState.ReadyOpen)
                {
                    CancelMotion(ref _handFadeMotion);
                    _handFadeMotion = LMotion.Create(handMat.color.a, 0f, handAppearDuration)
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

            State = state;
        }

        /// <summary>
        ///     ラムネを表示するべきかどうかを設定する
        /// </summary>
        /// <param name="isBottleAppear"></param>
        private void SetBottleAppear(bool isBottleAppear)
        {
            var bottlePos = _bottleBasePos;

            switch (isBottleAppear)
            {
                // 開ける準備が完了していて，まだボトルが落下していないなら
                case true when !_isBottleDropped:
                    // ボトルを落下させて見えるようにする
                    // 手も見えるようにする
                    _isBottleDropped = true;

                    CancelMotion(ref _bottleMotion);
                    bottle.SetActive(true);
                    _bottleMotion = LMotion.Create(bottleUpY, 0f, bottleDropDuration)
                        .WithEase(Ease.OutSine)
                        .Bind(v => bottle.transform.position = bottlePos + new Vector3(0f, v, 0f));
                    break;
                case false when _isBottleDropped:
                    // ボトルを下に落として見えなくする
                    _isBottleDropped = false;

                    CancelMotion(ref _bottleMotion);
                    _bottleMotion = LMotion.Create(0f, bottleDownY, bottleDropDuration)
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

        private static void CancelMotion(ref MotionHandle handle)
        {
            if (handle.IsActive()) handle.Cancel();
            handle = default;
        }
    }
}