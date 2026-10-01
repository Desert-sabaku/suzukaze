# Unityへのジェスチャー通知

Windows のセットアップと実機確認は [Windows protobuf 運用ガイド](windows-protobuf.md)を参照してください。

## 構成と起動

同一Windows PC内の1組の認識プロセス、ブリッジ、Unityを対象にします。
Windows UnityとWSL/Linux Pythonの組み合わせや別PC間の配送には対応しません。

`gesture_detection → TCP 127.0.0.1:5001 → unity_bridge → WebSocket 127.0.0.1:5000 → Unity`

受信確認は逆方向に返ります。`feat/unitybridge` のWebSocket基盤を使用します。
ブリッジはメッセージを中継するだけで、シーン判断やイベント受信確認の代理をしません。
従来のシリアル中継は別モードです。ジェスチャー通知をシリアルへ流しません。

1. `gesture_detection/.env` に `GESTURE_DELIVERY_ENABLED=true` を設定する。
2. `gesture_detection/` で `uv run gesture-detection` を起動する。
3. `unity_bridge/` で `uv run python -m unity_bridge.core --gesture-port 5001` を起動する。
4. Unityを `ws://127.0.0.1:5000` に接続する。模擬Unityなら同じディレクトリで
   `uv run python -m unity_bridge.gesture_probe` を起動する。

起動順は任意ですが、認識側が未起動の場合はブリッジがWebSocketを切断します。
同梱のUnity受信実装は500ms間隔で再接続します。接続はUnity 1台に限定します。
プローブの `--ignore-events` は演出中の見送りを模擬します。実機は操作しません。
接続を終了するには各プロセスでCtrl+C、認識画面ではEscを使います。

通知は既定で無効です。`VIDEO_SOURCE` が設定された動画評価では、有効設定でも
サーバーを起動しません。ポート競合や未確認イベント容量超過は黙って無視せず、
認識ワーカーのエラーとしてアプリを終了させます。

2カメラ認識は[2カメラ認識ガイド](multicam-runtime.md)の設定で起動します。
両カメラの結果を統合し、共有の解除・新準備判定を通過したイベントを1つのサーバーから通知します。
`MULTICAM_VIDEO_SESSION`による録画再生でも通知サーバーは起動しません。

## 通信形式

既定はバイナリの `protobuf` です。認識側（1・2カメラ共通）、ブリッジ、
プローブは形式指定を省略して接続できます。新しいUnity受信実装はProtobuf専用です。
旧Python受信側との互換用に `GESTURE_DELIVERY_FORMAT=json|protobuf` で選択できます。
認識側、ブリッジ、受信側で同じ形式を指定してください。
自動判別・形式のネゴシエーションはありません。

既定のProtobufで起動する例（各プロジェクトで先に `uv sync --locked`）:

```bash
# gesture_detection/.env に GESTURE_DELIVERY_ENABLED=true を設定して起動
uv run gesture-detection
# unity_bridge/（別ターミナル）
uv run unity-bridge --gesture-port 5001
uv run unity-gesture-probe
```

ブリッジの `--gesture-format` とプローブの `--format` は環境変数
`GESTURE_DELIVERY_FORMAT` より優先されます。未指定なら環境変数、次に `protobuf` を使います。
この指定はジェスチャー配送専用です。シリアル中継の形式は変わりません。

Protobufは共有の [gesture protocol](../../gesture_protocol/README.md) を使用します。
TCPは4バイトの符号なしビッグエンディアン長 + ペイロード、WebSocketは1つの
バイナリメッセージに1ペイロード（長さヘッダーなし）です。ペイロードは1〜8192バイト。
分割・連結されたTCPフレームを復元し、不正な長さ・途中EOF・不正なProtobuf・
逆方向の種類（認識側へのstate/event、Unity側へのACK）は切断します。
ブリッジは検証後の元バイト列を転送するため、未知フィールドも保持します。
不正な接続でも配送ワーカーは動作を継続し、再接続を受け付けます。
期限・再送・ACK・重複判定の意味は両形式で同じです。

### 旧Python受信側向けの明示的なJSON互換モード

認識側の `.env` に `GESTURE_DELIVERY_FORMAT=json` を設定し、ブリッジは
`uv run unity-bridge --gesture-port 5001 --gesture-format json`、プローブは
`uv run unity-gesture-probe --format json` で起動します。新しいUnityには使えません。
この互換モードのみ、TCPではUTF-8のJSONを1行に1件、LFで区切ります。WebSocketではテキストフレーム
1件にJSONを1個載せます。1件8 KiB以内で、画像・ランドマーク・診断文字列は送りません。

### フィールドの診断用JSON表現

以下のJSON例はフィールドの意味を説明する診断用表現です。既定の実通信は
Protobufバイナリであり、JSONテキストではありません。
`version=1`、認識ワーカー起動ごとのUUID `session_id` を共通で含めます。
未知のバージョンは演出に使わず切断してください。追加フィールドは無視できます。

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
  通信スレッドが生きていても古い認識を延命しません。
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

同梱のUnity受信実装はWindows QPCを使用します。
Windowsは `QueryPerformanceCounter / QueryPerformanceFrequency` の商、
Linuxは `clock_gettime(CLOCK_MONOTONIC)` の秒です。別OSへ移植するときは
Pythonの時計実装を確認します。取得方法は
[Pythonの時計仕様](https://docs.python.org/3/library/time.html#time.monotonic)と
[WindowsのQPC仕様](https://learn.microsoft.com/en-us/windows/win32/sysinfo/acquiring-high-resolution-time-stamps)
を参照してください。これは同一OS・同一PC用で、別PC間の時刻同期には対応しません。

セッションが変わったら継続状態と重複履歴を解除します。送信側の未確認イベントは
メモリだけで保持し、再起動で破棄します。ブリッジ再起動は認識セッションを変更しません。
Unity自身の再起動では処理済み履歴が失われるため、期限内の再送を再採用する可能性が
あります。障害をまたぐ厳密な一度限りの実行は保証しません。

## 実装と検証

`recognition.py` が成立した入力にだけ `occurrences` を付けます。
`pose_worker.py` は表示用の最新値キューへ入れる前に `DeliveryOutbox` へ通知します。
現在値は上書きできますが、イベントはACKまたは期限まで別途保持します。
ソケット送受信は `GestureServer` の別スレッドで行います。
接続待ち・遅い受信側・切断は推論を待たせません。
未確認イベントは最大64件で、容量超過時は明示的にエラーにします。

認識側は `uv run python -m pytest`、ブリッジ側は `uv run python -m pytest`。
実ソケットテストにはループバックのTCP・WebSocket接続権限が必要です。
Python模擬受信側は `unity_bridge/src/unity_bridge/gesture_probe.py` にあります。
実際のC#受信実装、診断Prefab、シーンへの組み込み方法は
[Unity GestureDelivery](../../suzukaze/Assets/GestureDelivery/README.md)を参照してください。
Unity Windows Editor/standalone（Mono/IL2CPP）の実機検証と実カメラによる演出確認は
未完了です。Pythonテストの成功はWindows上での動作確認を代替しません。
