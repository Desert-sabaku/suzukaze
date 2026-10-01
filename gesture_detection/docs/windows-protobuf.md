# Windows 同一 PC での protobuf 配送

## 対象と導入状況

Windows ネイティブの Python、unity_bridge、Unity 6000.5.8f1 を同じ PC で
起動します。Unity が演出の採用を判断し、マイコン制御アプリは別系統です。
WSL 上の Python と Windows Unity は時計の原点が異なるため対象外です。

```text
gesture_detection → TCP 127.0.0.1:5001 → unity_bridge
                                           ↕ binary WebSocket
                                    Unity 127.0.0.1:5000
```

この統合変更で既定形式を protobuf に切り替えます。通知機能自体は引き続き
`GESTURE_DELIVERY_ENABLED=false` が既定です。旧 JSON 接続は各 Python プロセスで
明示選択すれば使えますが、同梱 C# 受信器は protobuf 専用です。

共有スキーマ、Python 配送、C# 受信器、結合・切替の順に導入します。
Python/C# の自動検証と Unity Editor/Windows プレイヤー検証は別です。
後者を実施するまでは、本番移行の確認は未完了です。

## 1. 準備

- Windows 版 uv と Git LFS を用意し、リポジトリ全体を取得します。
- 認識用モデルとカメラ設定は [認識アプリの README](../README.md) に従います。
- Unity Hub から上記バージョンで `suzukaze/` を開きます。
- 配送先はループバックのみです。5000/5001 番を他のプロセスが使用していないことを確認します。

リポジトリルートの PowerShell で依存を準備します。

```powershell
git lfs pull
uv sync --locked --project gesture_detection
uv sync --locked --project unity_bridge
uv run --project unity_bridge python tools/restore_unity_protobuf.py
```

最後のコマンドは NuGet パッケージの SHA-256 を照合し、固定バージョンの
Google.Protobuf/Unsafe DLL を復元します。Unity の通常の利用に .NET SDK や protoc
は不要です。共有 Python パッケージは隣接パスからインストールされるため、
`gesture_protocol/` も含めて配置してください。

## 2. 起動

**PowerShell A**（リポジトリルートから）：

```powershell
Set-Location gesture_detection
$env:GESTURE_DELIVERY_ENABLED = "true"
$env:GESTURE_DELIVERY_FORMAT = "protobuf"
uv run --locked gesture-detection
```

**PowerShell B**（別ウィンドウ、リポジトリルートから）：

```powershell
Set-Location unity_bridge
uv run --locked unity-bridge --gesture-port 5001 --gesture-format protobuf
```

明示的な形式指定により、以前の `.env` や環境変数に JSON が残っていても
形式を揃えられます。`VIDEO_SOURCE` または `MULTICAM_VIDEO_SESSION` による
動画再生時はサーバーが起動しないので、ライブ認識を使用します。

Unity の確認用シーンのルートに
`Assets/GestureDelivery/Prefabs/GestureReceiverDiagnostic.prefab` を配置し、再生します。

- Endpoint は `ws://127.0.0.1:5000`。
- 既定の診断 Sink はイベントを `ignored` として記録します。
- Inspector で `acceptEvents` を有効にすると診断目的の採用を記録します。
- 実際の演出には `IGestureSink` を実装し、演出を採用した場合だけ `true` を返します。
  ラムネや打ち水に対応する演出の割当ては、この通信実装では定義していません。
- Receiver はシーン遷移後も存続します。シーン固有 Sink は `SetSink` で差し替えます。
- Player Settings の **Run In Background** は有効です。Editor の Pause は解除してください。

起動順は任意で、C# 受信器は切断後500ms間隔で再接続します。Unity と模擬受信器を
同時に接続しないでください。ブリッジは1受信器のみを許可します。

Unity を起動する前の切り分けには、別の PowerShell で次を使用できます。

```powershell
Set-Location unity_bridge
uv run --locked unity-gesture-probe --format protobuf
# 見送りの確認には --ignore-events を追加
```

終了は認識画面の Esc、各 Python プロセスの Ctrl+C、Unity の再生停止です。

## 3. カメラなしの Python ↔ C# 結合検証

.NET SDK 8 と uv が必要です。以下はリポジトリルートの **PowerShell** で実行します。
専用の小さな環境へ実パッケージをインストールし、モデル関連依存は読み込みません。

```powershell
uv sync --locked --project tools/gesture-integration
$python = (Resolve-Path tools/gesture-integration/.venv/Scripts/python.exe).Path
uv pip install --python $python --no-deps -e gesture_protocol -e gesture_detection -e unity_bridge
& $python tools/restore_unity_protobuf.py
$env:GESTURE_E2E_PYTHON = $python
$env:GESTURE_E2E_FIXTURE = (Resolve-Path tools/gesture-integration/fixture.py).Path
dotnet restore tools/GestureDelivery.Integration --locked-mode
dotnet test tools/GestureDelivery.Integration --no-restore
```

同じテストを CI の Ubuntu/Windows ジョブでも実行します。Windows ジョブは実際の
`WindowsQpcClock` を使い、Python `time.monotonic()` のサンプルを C# 時計で挟んで
同じ時刻系であることも検証します。Linux ジョブも本番の `LinuxMonotonicClock` を使用します。

確認する経路は、実 `DeliveryOutbox` → 実 TCP サーバー → 実 WebSocket ブリッジ
→ 実 C# 受信コア → ACK → Outbox です。採用、見送り、重複、メインスレッド待ち中の
失効、ACK 後の再送停止を確認します。Unity の MonoBehaviour/シーンは実行しません。

## 4. Unity/Windows で残る確認

Unity Test Runner の EditMode/PlayMode テストと、実カメラを使った以下の確認を行い、
結果・Unity バージョン・OS・スクリプティングバックエンドを PR に記録します。

| 操作 | 期待結果 |
|---|---|
| Editor で読み込み・Play | DLL/アセンブリの解決に成功し、接続できる |
| 扇ぎ・夕涼み、追跡喪失 | 継続状態が更新され、古い状態が解除される |
| ラムネ・打ち水 | 1成立につき1回だけ Sink に渡り、判断後に ACK が返る |
| Sink を未設定／見送りにする | `ignored`、後の再送で採用し直さない |
| ブリッジ再起動 | 再接続し、期限内の処理済みイベントを二重採用しない |
| 認識側再起動 | 新 session を認識し、旧状態と履歴を解除する |
| フォーカス移動 | standalone の Update と受信処理が継続する |
| Editor Pause／処理停止後に再開 | 古いイベントを採用しない。満杯なら切断後に回復する |
| シーン切替／受信所有者の交換 | 接続所有者が1つで、期限内の重複履歴が残る |
| Windows standalone | 採用する Mono または IL2CPP 構成でビルド・実行が成功する |

Unity 起動のたびに重複履歴は初期化されます。プロセス再起動をまたぐ厳密な
exactly-once 実行は保証しません。

## 5. トラブルシュート

- **接続できない**：Unity の `GestureReceiverBehaviour.LastError`、ブリッジの待受表示、
  ライブ入力であること、通知有効化、ポート競合を確認します。
- **接続してもすぐ切れる**：送信側とブリッジの形式を protobuf に揃え、WSL を使用していないか
  確認します。別の受信器が接続していないかも確認します。
- **演出が始まらない**：診断 Sink の既定は見送りです。実 Sink の設定と `TryAcceptEvent`
  の判断を確認します。通信の ACK は演出完了通知ではありません。
- **DLL を解決できない**：LFS オブジェクトを取得するか復元スクリプトを実行し、
  同名 DLL が他の Unity プラグインに重複していないことを確認します。
- **旧 JSON 消費側を使う**：認識側の `GESTURE_DELIVERY_FORMAT=json`、ブリッジの
  `--gesture-format json`、プローブの `--format json` を揃えます。C# 受信器は停止します。

フィールドの意味と期限は [配送仕様](unity-delivery.md)、C# API とライフサイクルは
[Unity 受信器 README](../../suzukaze/Assets/GestureDelivery/README.md) を参照してください。
