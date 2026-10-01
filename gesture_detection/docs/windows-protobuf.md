# Windows 同一 PC での protobuf 配送

## 対象と導入状況

Windows ネイティブの Python、unity_bridge、Unity 6000.5.8f1 を同じ PC で
起動します。Unity が演出の採用を判断します。
WSL 上の Python と Windows Unity は時計の原点が異なるため対象外です。

```text
unity_bridge ─ 子プロセス + multiprocessing.Queue ─ gesture_detection
     ↕ binary WebSocket
Unity 127.0.0.1:5000
```

`unity_bridge --gesture` が認識アプリを子プロセスとして起動します。
認識アプリを単体で起動した場合は送信しません。

## 1. 準備

- Windows 版 uv と buf を用意し、リポジトリ全体を取得します。
- 認識用モデルとカメラ設定は [認識アプリの README](../README.md) に従います。
- 配送先はループバックのみです。5000 番を他のプロセスが使用していないことを確認します。

リポジトリルートの PowerShell で生成物と依存を準備します。

```powershell
Set-Location proto
buf generate
Set-Location ..
uv sync --locked --project unity_bridge
```

Unity Hub から 6000.5.8f1 で `suzukaze/` を開きます。`Google.Protobuf` は
NuGetForUnity が `Assets/packages.config` から復元します。生成物がない場合は
Console に `buf generate` を案内するエラーが出ます。

## 2. 起動

**PowerShell A**（リポジトリルートから）：

```powershell
Set-Location unity_bridge
uv run --locked unity-bridge --gesture
```

認識画面が開き、`ws://127.0.0.1:5000` で Unity を待ち受けます。
`VIDEO_SOURCE` または `MULTICAM_VIDEO_SESSION` による動画再生時は送信しないので、
ライブ認識を使用します。

Unity の確認用シーンのルートに
`Assets/Bridge/Gesture/Prefabs/GestureReceiverDiagnostic.prefab` を配置し、再生します。

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
uv run --locked unity-gesture-probe
# 見送りの確認には --ignore-events を追加
```

終了は認識画面の Esc（ブリッジも終了します）、ブリッジの Ctrl+C、Unity の再生停止です。

## 3. 自動テスト

- Python：`unity_bridge/` で `uv run python -m pytest`。実際の子プロセス・キュー・
  WebSocket・プローブ受信処理を通します（カメラ不要）。
- Unity：Test Runner の EditMode/PlayMode（`Assets/Bridge/Gesture/Tests/`）。
  `NativeClockTests` は実際の `WindowsQpcClock` を使います。

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
  `--gesture` を付けて起動したこと、ライブ入力であること、ポート競合を確認します。
- **接続してもすぐ切れる**：WSL を使用していないか確認します。
  別の受信器（プローブなど）が接続していないかも確認します。
- **演出が始まらない**：診断 Sink の既定は見送りです。実 Sink の設定と `TryAcceptEvent`
  の判断を確認します。通信の ACK は演出完了通知ではありません。
- **`Google.Protobuf` や生成コードを解決できない**：NuGetForUnity の復元（`Assets/Packages/`）と
  `buf generate` を確認し、同名 DLL が他の Unity プラグインに
  重複していないことを確認します。

フィールドの意味と期限は [配送仕様](unity-delivery.md)、C# API とライフサイクルは
[Unity 受信器 README](../../suzukaze/Assets/Bridge/Gesture/README.md) を参照してください。
