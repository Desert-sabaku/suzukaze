using Features.senkoUI;
using UnityEngine;

namespace Features.Result.Scripts
{
    /// <summary>
    ///     線香花火 (Senko Hanabi VFX) の燃え具合を線香花火のゲージに反映する．
    ///     着火から火玉が落ちるまでゲージを燃やし，進み具合は燃え尽きるまでの時間 (BurnDuration) に対する経過時間の割合にする．
    ///     火玉が早く落ちたときはゲージも途中で止まる．
    /// </summary>
    [DisallowMultipleComponent]
    [RequireComponent(typeof(SenkoHanabiController))]
    public class SenkoHanabiGauge : MonoBehaviour
    {
        [SerializeField] private SparklerGaugeController gauge;

        private SenkoHanabiController _hanabi;
        private bool _isBurning;

        private void Awake()
        {
            _hanabi = GetComponent<SenkoHanabiController>();
            if (gauge) return;
            Debug.LogError("Gaugeを設定してください。", this);
            enabled = false;
        }

        private void Update()
        {
            var burning = _hanabi.IsPlaying && !_hanabi.IsDropped;
            if (burning != _isBurning)
            {
                if (burning) gauge.StartBurning();
                else gauge.EndBurning();
                _isBurning = burning;
            }

            if (burning) gauge.SetProgress(_hanabi.Elapsed / _hanabi.BurnDuration);
        }
    }
}
