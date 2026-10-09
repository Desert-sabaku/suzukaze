using System;
using System.Collections.Concurrent;
using System.IO;
using System.Threading;
using Google.Protobuf;
using Suzukaze.Bridge.Protocol;

namespace Suzukaze.Gesture
{
    // unity_bridge の設定画面との窓口。届いた設定を保ち、Unity の状態とエラーを bridge へ送る。
    // 設定は WebSocket のスレッドが書いてメインスレッドが読み、状態とログはその逆。
    public sealed class RuntimeControl
    {
        public const double MaxTimeScaleMultiplier = 100;
        // 送らずに溜めておくログの上限。切断中に出たエラーも、つながったら送る。
        public const int MaxPendingLogs = 32;
        // UnityLog 1件が WireMessage.MaxBytes に収まるよう、文字数で切り詰める(UTF-8 で1文字最大3バイト)。
        public const int MaxMessageChars = 500;
        public const int MaxStackTraceChars = 1500;

        public static RuntimeControl Instance { get; private set; } = new();

        public static void ResetInstance() => Instance = new RuntimeControl();

        private readonly object gate = new();
        // bridge から設定が届くまでは、設定画面の既定値と同じ値で動く。
        private RuntimeSettings settings = new() { DiffuserEnabled = true, TimeScaleMultiplier = 1 };
        private byte[] status;
        private readonly ConcurrentQueue<byte[]> logs = new();

        public bool DiffuserEnabled { get { lock (gate) return settings.DiffuserEnabled; } }
        public double TimeScaleMultiplier { get { lock (gate) return settings.TimeScaleMultiplier; } }

        // 次の状態に載せる値。BetweenSceneTimeManager が毎フレーム書く。時間を動かさないシーンでは CurrentHour は null。
        public double? CurrentHour { get; set; }
        public double EffectiveTimeScale { get; set; }

        public static void Validate(RuntimeSettings received)
        {
            var multiplier = received.TimeScaleMultiplier;
            if (double.IsNaN(multiplier) || multiplier < 0 || multiplier > MaxTimeScaleMultiplier)
                throw new InvalidDataException("Invalid runtime settings");
        }

        public void Apply(RuntimeSettings received)
        {
            Validate(received);
            lock (gate) settings = received.Clone();
        }

        // いまの状態を送る。まだ送っていない前の状態は捨てる。
        public void ReportStatus(string scene, double fps)
        {
            RuntimeSettings applied;
            lock (gate) applied = settings.Clone();
            var report = new RuntimeStatus
            {
                Settings = applied, Scene = scene ?? "", EffectiveTimeScale = EffectiveTimeScale, Fps = fps
            };
            if (CurrentHour is { } hour) report.CurrentHour = hour;
            Interlocked.Exchange(ref status, new BridgeEnvelope { RuntimeStatus = report }.ToByteArray());
        }

        public void ReportLog(UnityLogLevel level, string message, string stackTrace)
        {
            // 溢れたら新しいほうを捨てる。最初のエラーのほうが原因に近い。
            if (logs.Count >= MaxPendingLogs) return;
            var log = new UnityLog
            {
                Level = level,
                Message = Truncate(message, MaxMessageChars),
                StackTrace = Truncate(stackTrace, MaxStackTraceChars)
            };
            logs.Enqueue(new BridgeEnvelope { UnityLog = log }.ToByteArray());
        }

        // bridge へ送る次の電文。なければ null。トランスポートが呼ぶ。
        public byte[] TakeOutgoing() =>
            Interlocked.Exchange(ref status, null) ?? (logs.TryDequeue(out var bytes) ? bytes : null);

        private static string Truncate(string text, int max) =>
            string.IsNullOrEmpty(text) ? "" : text.Length <= max ? text : text.Substring(0, max) + "…";
    }
}
