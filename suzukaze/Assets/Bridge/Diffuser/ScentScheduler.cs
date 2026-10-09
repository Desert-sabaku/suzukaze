using System;
using System.Collections.Generic;
using Suzukaze.Diffuser.Protocol;

namespace Suzukaze.Diffuser
{
    // チャンネルごとに、いつまで香りを出すかを覚え、ON/OFF が変わるときだけボタンを押す。
    // ディフューザーはトグル式で状態を読めないので、自分が押した結果を ON/OFF として覚える。
    public sealed class ScentScheduler
    {
        private readonly Action<DiffuserChannel> press;
        private readonly Dictionary<DiffuserChannel, double> until = new();
        private readonly HashSet<DiffuserChannel> on = new();

        public ScentScheduler(Action<DiffuserChannel> press) => this.press = press;

        /// <summary>
        /// [now]から[seconds]秒は香りを出す。出している間に呼ぶと、止める時刻を延ばす。
        /// </summary>
        public void Emit(DiffuserChannel channel, double now, double seconds)
        {
            var end = now + seconds;
            if (!until.TryGetValue(channel, out var current) || current < end) until[channel] = end;
        }

        // 出し始める・止める時刻になったチャンネルのボタンを押す。毎フレーム呼ぶ。
        public void Update(double now)
        {
            foreach (var (channel, end) in until)
            {
                var want = now < end;
                if (want == on.Contains(channel)) continue;
                if (want) on.Add(channel);
                else on.Remove(channel);
                press(channel);
            }
        }

        // 出している香りをすべて止める。
        public void StopAll()
        {
            foreach (var channel in on) press(channel);
            on.Clear();
            until.Clear();
        }

        public bool IsOn(DiffuserChannel channel) => on.Contains(channel);
    }
}
