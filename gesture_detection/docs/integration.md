# Unity連携・OS別セットアップ・2カメラ

このページに、Unityへの通知、Windows/Linuxのセットアップ、2カメラ認識をまとめます。

## 構成と起動

同一Windows PCまたは同一64-bit Linux PC内の1組の認識プロセス、ブリッジ、Unityを対象にします。
Windows UnityとWSL/Linux Pythonの組み合わせや別PC間の配送には対応しません。

`unity_bridge ─(子プロセス起動 + multiprocessing.Queue)─ gesture_detection`
`unity_bridge → WebSocket 127.0.0.1:5000 → Unity`

`unity_bridge` が認識アプリ（`gesture_detection.app.main`）を子プロセスとして起動し、
`GestureSample`（`recognition_types.py`）をキューで受け取ります。キューはPython標準の
`multiprocessing.Queue`（pickle）で、ソケットやポートは使いません。
状態通知・成立イベントの保持と再送・ACKの処理は `unity_bridge` の `DeliveryOutbox` が行い、
Unityの受信確認は認識側へは返しません。シーン判断はUnityが行います。
従来のシリアル中継は別モードです。ジェスチャー通知をシリアルへ流しません。

1. `unity_bridge/` で `uv run unity-bridge --gesture` を起動する（認識画面も開きます）。
2. Unityを `ws://127.0.0.1:5000` に接続する。模擬Unityなら同じディレクトリで
   `uv run unity-gesture-probe` を起動する。

Unityが未接続の間も認識結果は受け取り、状態とイベントの期限を進めます。
Unity側は切断時に再接続してください（Unityの受信実装は500ms間隔）。接続はUnity 1台に限定します。
プローブの `--ignore-events` は演出中の見送りを模擬します。実機は操作しません。
終了はブリッジでCtrl+C、または認識画面でEscです。認識側が終了するとブリッジも終了します。

`gesture-detection` を単体で起動した場合は送信しません。`VIDEO_SOURCE` を設定した
動画評価や `MULTICAM_VIDEO_SESSION` による録画再生でも送信しません（時刻が入力元の時刻のため）。
未確認イベントの容量超過は黙って無視せず、ブリッジのエラーとして終了させます。

2カメラ認識は、このページの[2カメラ認識](#2カメラ認識)の設定で起動します。
両カメラの結果を統合し、共有の解除・新準備判定を通過したイベントを1つのキューへ送ります。

送信間隔などは `unity_bridge` の環境変数で変更します（既定値）:
`GESTURE_STATE_INTERVAL=0.1`、`GESTURE_STALE_TIMEOUT=0.5`、`GESTURE_EVENT_TTL=1.0`、
`GESTURE_RETRY_INTERVAL=0.1`、`GESTURE_MAX_PENDING=64`。
`GESTURE_EVENT_TTL` は2カメラ統合でも使うため、`gesture_detection/.env` と同じ値にしてください。

## 通信形式

WebSocketでは1つのバイナリメッセージに1つのProtobufペイロード（`../../proto/gesture/v1/gesture.proto`
の `GestureEnvelope`、長さヘッダーなし）を載せます。ペイロードは1〜8192バイトです。
Python側は `proto/` で `buf generate` して生成した
`unity_bridge/src/unity_bridge/gen/` を使い、C#側も同じコマンドで
`suzukaze/Assets/Bridge/Generated/Gesture.cs` を生成します。
不正なProtobuf、テキストフレーム、Unityからのstate/eventは切断します。
画像・ランドマーク・診断文字列は送りません。
`version=1`、認識セッションごとのUUID `session_id` を共通で含めます。
未知のバージョンは演出に使わず切断してください。未知フィールドは無視できます。

以下はフィールドの意味をJSON表記で示したものです。

### 継続状態

```json
{"version":1,"type":"state","session_id":"uuid","sequence":42,"sent_at":100.2,"stale_timeout":0.5,"fresh":true,"gesture":"FANNING","tracking":true,"observed_at":100.1,"frame_id":300,"source_timestamp":100.1}
```

- 既定で100ms間隔。状態のACKは不要です。
- `gesture` は `NONE / FANNING / RELAXING`。同時成立時は既存の代表動作の
  優先順位を維持し、独立した複数動作には展開しません。
- ラムネ・打ち水が代表動作の間、継続状態は `NONE` です。
- `fresh=true, tracking=false` は、新しい入力で人物を検出できなかった状態です。
- 認識入力が500ms古くなると `fresh=false, tracking=false, gesture=NONE`。
  通信が続いていても古い認識を延命しません。
- Unityでも状態受信から500msの途絶、または `observed_at + stale_timeout`
  到達の早い方で解除します。送信された `fresh` だけでなく、Unityで処理するときの
  時刻を確認します。Unityメインスレッドへの待ち行列でも古くなるためです。
- `sequence` は状態通知ごとの連番です。同じセッションの古い連番は無視します。
  初回推論前は `observed_at/frame_id/source_timestamp` がnullになります。

### 成立イベント

```json
{"version":1,"type":"event","session_id":"uuid","event_id":7,"gesture":"RAMUNE","occurred_at":100.1,"expires_at":101.1,"frame_id":300,"source_timestamp":100.1}
```

- `gesture` は `RAMUNE / UCHIMIZU`。成立した入力に対して1件発行します。
  フィードバック保持中は再発行せず、解除・再準備後の成立で次のIDを発行します。
  両手同時の打ち水は現行の代表動作に合わせて1件です。
- 成立入力の取得時刻から1秒で失効します。推論に費やした時間も期限に含みます。
- 未確認分を既定100ms間隔で再送し、再接続時にも期限内の未確認分を送ります。
  ID、成立時刻、有効期限は再送で変えません。
- 送信側は期限切れを破棄します。受信側も演出への採用直前に
  `now >= expires_at` を確認し、期限切れなら演出を開始しません。
- `event_id` はイベント専用連番です。重複判定キーは `(session_id, event_id)`。
  Unity側は再接続をまたいで処理済みIDを期限まで保持します。

### 受信確認

```json
{"version":1,"type":"ack","session_id":"uuid","event_id":7,"status":"accepted"}
```

`status` は `accepted / ignored / expired / duplicate`。
Unityが採用・演出中などによる見送り・期限切れ・重複を判断してから返します。
どの結果でも再送を止めます。演出の再生完了を待つACKではありません。
演出の完了や次のシーンへの遷移はUnity内部の責務です。
Unityは見送ったイベントも処理済みに記録し、後の再送で再採用しません。

## 時刻と再起動

`sent_at / observed_at / occurred_at / expires_at` の単位は秒（double）です。
同じホストのPython `time.monotonic()` と同じ時計・原点を使用します。
`DateTime.UtcNow`、Unityの起動後経過時間、Stopwatchインスタンスの経過時間とは
比較できません。`source_timestamp` は診断用の入力元時刻で、配送の時計とは区別します。

2カメラ時の`frame_id`・`source_timestamp`は統合tickの連番・時刻です。
`observed_at`は最後に取得した入力の時刻、イベントの`occurred_at`はそのイベントを生成した
元フレームの取得時刻を保持します。別カメラの新しい入力や統合処理によってイベントの期限を延ばしません。
状態統合には直近0.2秒の視点を使うため、配送側の0.5秒の失効より先に`NONE`へ戻る場合があります。

同梱のUnity受信実装はOSに合わせてWindows QPCまたはLinux CLOCK_MONOTONICを選択します。
Windowsは `QueryPerformanceCounter / QueryPerformanceFrequency` の商、
Linuxは `clock_gettime(CLOCK_MONOTONIC)` の秒です。別OSへ移植するときは
Pythonの時計実装を確認します。取得方法は
[Pythonの時計仕様](https://docs.python.org/3/library/time.html#time.monotonic)と
[WindowsのQPC仕様](https://learn.microsoft.com/en-us/windows/win32/sysinfo/acquiring-high-resolution-time-stamps)
を参照してください。これは同一OS・同一PC用で、別PC間の時刻同期には対応しません。

セッションが変わったら継続状態と重複履歴を解除します。送信側の未確認イベントは
ブリッジのメモリだけで保持し、ブリッジ（と認識）の再起動で破棄して新しいセッションになります。
Unity自身の再起動では処理済み履歴が失われるため、期限内の再送を再採用する可能性が
あります。障害をまたぐ厳密な一度限りの実行は保証しません。

## 実装と検証

`recognition.py` が成立した入力にだけ `occurrences` を付けます。
`pose_worker.py`（2カメラでは `multicam_app.py`）は表示用の最新値キューへ入れる前に
`GestureSample` をキューへ送ります。このキューは最新値優先ではないため、イベントは落ちません。
`unity_bridge` の `GestureRelay.pump` が受け取って `DeliveryOutbox` へ渡し、
WebSocketの送受信は別タスクで行います。接続待ち・遅い受信側・切断は推論を待たせません。
未確認イベントは最大64件で、容量超過時は明示的にエラーにします。

認識側・ブリッジ側とも `uv run python -m pytest`。ブリッジ側の統合テストは実際の子プロセス・
キュー・WebSocket・プローブ受信処理を通します（カメラは不要）。
Unityの受信実装は `suzukaze/Assets/Bridge/Gesture/`（[README](../../suzukaze/Assets/Bridge/Gesture/README.md)）、
Pythonの参照実装は `unity_bridge/src/unity_bridge/gesture_probe.py` にあります。
Unityの受信実装はWindows（QPC）と64-bit Linux（`CLOCK_MONOTONIC`）の時計に対応しています。
実機Unityと実カメラによる演出確認は別途必要です。

## OS別セットアップ

### 共通条件

Python、uv、buf、Unity 6000.5.8f1を同一PCに用意します。Windows UnityとWSL/Linux
Pythonの混在、別PC間の配送、時計名前空間が異なるコンテナは対象外です。

リポジトリルートでprotobuf生成と依存関係の同期を行います。

```bash
(cd proto && buf generate)
uv sync --locked --project unity_bridge
```

Unityは `suzukaze/` を開き、`GestureReceiverDiagnostic.prefab` を確認用シーンへ配置します。
接続先は常に `ws://127.0.0.1:5000` です。`Google.Protobuf` はNuGetForUnityで復元します。

### Windows

PowerShellから起動します。

```powershell
Set-Location unity_bridge
uv run --locked unity-bridge --gesture
```

WindowsではUnityとPythonをネイティブ環境で動かします。QPCを使うため、WSL側のPythonから
Windows Unityへ接続しません。Unity EditorのRun In Backgroundを有効にし、Editor Pauseを
解除します。

### Fedora/Linux

Linuxネイティブ環境から起動します。

```bash
uv run --directory unity_bridge --locked unity-bridge --gesture
```

Linuxでは `CLOCK_MONOTONIC` を使います。カメラのデバイス番号は環境により異なるため、
`v4l2-ctl --list-devices` で確認します。Unity Editorのbatchmodeテストは、必要な場合に
`suzukaze/` を対象として実行します。

### OS共通の切り分け

Unityを使わずに受信を確認する場合は、`unity_bridge/` で次を実行します。

```bash
uv run --locked unity-gesture-probe
```

接続できない場合は、`--gesture`、ライブ入力、ポート競合、受信器の二重起動を確認します。
診断Sinkの既定値は `ignored` なので、演出を採用する場合は `IGestureSink` を実装します。

## 2カメラ認識

`.env` に次を設定して実行します。

```dotenv
MULTICAM_ENABLED=true
MULTICAM_CAMERA_INDICES=1,2
MULTICAM_FIRST_SELECT_SUBJECT=true
MULTICAM_SECOND_SELECT_SUBJECT=false
MULTICAM_VIDEO_SESSION=
VIDEO_SOURCE=
POSE_RUNNING_MODE=VIDEO
RAMUNE_DETECTOR=rules
MULTICAM_HEADLESS=false
```

```bash
uv run gesture-detection
```

最初のカメラは人物選択、2台目は全画面解析です。Linuxでは1台のカメラが複数の
`/dev/video*` として見えることがあるため、実際のデバイス番号を指定してください。
2台の入力は同じ実演者を撮影する構成で使います。

録画セッションを再生する場合は `MULTICAM_VIDEO_SESSION` に `session.json` を指定します。
録画再生ではUnityへ通知しません。`MULTICAM_TRACE_PATH` を指定すると統合結果をJSONLへ
保存できます。統合は直近の入力時刻を使い、古いイベントの期限を新しい入力で延長しません。

2カメラの責任分界は、各カメラの取得・推論を子プロセスで行い、親側で結果を統合してから
`GestureSample` としてブリッジへ渡す構成です。詳細な通信形式、イベント期限、ACK、時計の
扱いはこのページ上部の[通信形式](#通信形式)と[時刻と再起動](#時刻と再起動)を正本とします。
