using System.Net.WebSockets;
using System.Threading;
using System.Threading.Tasks;

namespace Suzukaze.Core
{
    // Transceiver が接続の管理だけを持つため、接続の状態と、受信・送信の中身はここで受け取る。
    // token は接続ごとに Begin が払い出し、古い接続からの呼び出しを見分けるのに使う。
    public interface ITransceiverHandler
    {
        // 新しい接続を始める。0 を返すと接続しない(停止中)。
        long Begin();

        bool IsConnected(long token);

        void End(long token);

        // 接続が終わる(または終わっている)と完了する。
        Task WaitForEndAsync(long token);

        // メッセージを1つ受信して処理する。false を返すと接続を閉じる。
        Task<bool> ReceiveAsync(WebSocket socket, long token, CancellationToken cancellation);

        // 次に送るバイト列。送るものがなければ null。
        byte[] TakeOutgoing(long token);
    }
}
