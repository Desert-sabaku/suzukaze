using UnityEngine;

namespace Features.Result.Scripts
{
    /// <summary>
    ///     ゲームシーンで集計したプレイ全体の正確性 (0-1) をリザルトシーンへ渡す．
    ///     一度受け取ると消えるので，リザルトシーンを直接再生したときは Inspector の既定値になる．
    /// </summary>
    public static class PlayScore
    {
        private static float? _pending;

        public static void Submit(float score)
        {
            _pending = Mathf.Clamp01(score);
            Debug.Log($"PlayScore.Submit: {score}");
        }

        public static bool TryTake(out float score)
        {
            score = _pending.GetValueOrDefault();
            var exists = _pending.HasValue;
            _pending = null;
            return exists;
        }
    }
}