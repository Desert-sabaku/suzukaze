# Unity bridge

`feat/unitybridge` を基盤とするWebSocket中継アプリです。Python 3.14以上を使用します。
`uv sync --group dev` で環境を用意してください。

パッケージは `src/unity_bridge/` にあります。`src` 自体はパッケージでは
ありません。旧 `src.*` のimportは `unity_bridge.*` に変更しています。
インストール後は `unity-bridge` と `unity-gesture-probe` コマンドを使用できます。

## ファン

`--gesture` のWebSocket 1本で、ファンも扱います。ファンだけ使うときは、カメラを起動しない
`uv run unity-bridge --fan` を使います(`--gesture` は不要です)。電文は `proto/bridge/v1/bridge.proto` の
`BridgeEnvelope` です。Unityが `fan_command`(`fan.v1.Fan`)を送ると、ブリッジが記録して、
ファン6本のいまの出力を `fan_state` で返します(最初の指示を受けてから、状態通知と同じ周期)。
firmwareには回転数の読み出しがないので、出力は指示から推定します
(0 から value まで、firmwareと同じガンマ2.2のカーブ)。

環境変数 `FAN_PWM_PINS`(6本のGPIO番号、カンマ区切り。順は `channel` の1〜6)を設定すると、
`mcu` ライブラリでマイコンへ `PwmFade` も送ります。ポートは `MICROCONTROLLER_SERIAL_PORT`、
ボーレートは `MICROCONTROLLER_BAUDRATE` です。未設定ならマイコンへは送りません。
マイコンが未接続でもブリッジは落ちず、次の指示で再接続します(落とした指示は再送しません)。

## ジェスチャー通知

```bash
uv run unity-bridge --gesture
```

`gesture_detection` を子プロセスとして起動し、認識結果を `multiprocessing.Queue`
で受け取って、UnityのWebSocket `ws://127.0.0.1:5000` へProtobufで送ります。
このモードではシリアルポートを開きません。同時接続は1クライアントです。
状態通知・イベントの再送・UnityからのACKはブリッジ内の `DeliveryOutbox` が扱います。
状態通知には、準備を含む進行状態として省略可能なenum `action` と `phase` も
送ります（例: `gesture: NONE, action: RAMUNE, phase: READY`）。両フィールドは
一緒に存在し、アイドル・追跡喪失・失効時は省略します。`unity-gesture-probe` でも
表示されます。phaseの値とUnity側の利用例は下記の受信実装READMEを参照してください。
`action` と `phase` は受信実装READMEに記載した組み合わせだけを許容します。
`RAMUNE / NONE` などの未定義の組み合わせは送受信で拒否します。
phaseは最新状態であり、すべての段階の到達・順序を保証しません。成立の通知には
phaseではなく、再送・ACKのあるイベントを使用してください。

| フィールド | 所作の意味 |
|---|---|
| `State.gesture` | 継続中の所作（扇ぎ・夕涼み・礼）。ない場合は `NONE` |
| `Event.gesture` | 新規に成立した所作（ラムネ・打ち水）。成立ごとにイベントとして配送 |
| `State.action / phase` | 進行中の所作とその段階。準備中・成立後の状態も含む |

Python側の所作・フェーズは `gesture_detection.gesture_types.Gesture / Phase` に、
許容する組み合わせは同モジュールの `ACTION_PHASES` に集約しています。
認識器・ブリッジでこの `StrEnum` を共用し、通信時はProtobufから生成したenumに変換します。
JSONの表示は `RAMUNE / READY` などの文字列です。
旧文字列フィールドのタグ11・12は予約し、enum版はタグ13・14を使用します。

認識側・ブリッジ・Unityは同一Windows PCまたは同一64-bit Linux PCで実行します。
Windows UnityとWSL/Linux Pythonの組み合わせには対応しません。

模擬Unity（実機出力なし）:

```bash
uv run unity-gesture-probe
uv run unity-gesture-probe --ignore-events
```

### デバッグGUI（認識なしで所作を送る）

```bash
uv run unity-bridge --debug-gui
```

カメラと `gesture_detection` を起動せずに、ブラウザから所作をUnityへ送ります。
ブラウザで `http://127.0.0.1:5080/` を開いてください。ポートは `--debug-port` か
環境変数 `GESTURE_DEBUG_PORT` で変更できます。Unityの接続先は通常どおり
`ws://127.0.0.1:5000` で、ファンも `--gesture` と同じように扱います。

送った値は認識結果と同じ `DeliveryOutbox` を通るので、状態の再送・イベントの再送・
ACKの扱いは本番と同じです。画面では次の操作ができます。

- 継続所作（`State.gesture`）・`tracking`・`booth_present`・`action_accuracy` の切り替え
- 進行状態（`action / phase`）の切り替え。許容する組み合わせだけを選べます
- ラムネ・打ち水のイベント送信と、準備のphaseを順に送ってから成立させるシーケンス
- 未ACKのイベントと、UnityからのACKの一覧

キーボードでは `1`〜`4` で継続所作、`T` で追跡、`B` で在室を切り替え、
`R` でラムネ、`U` で打ち水を送ります。`--fan` とは併用できません。

### 設定画面（会場のスマホから見る・変える）

`--gesture`・`--fan`・`--debug-gui` のどれで起動しても、設定画面も一緒に起動します。
Unity用のソケットはloopbackのままで、設定画面だけをLANに公開します（既定は `0.0.0.0:5081`）。
起動時に `Admin page: http://<PCのLAN側IP>:5081/` と表示されるので、同じWi-Fiにつないだスマホで開いてください。
インターネットへの接続は不要です。

| 表示・操作 | 内容 |
|---|---|
| 設定 | ディフューザーを使うか（止めると出している香りも止めます）、時間の速さの倍率（`GameSettings.timeScale` に掛けます） |
| Unity | 接続状態、シーン、ゲーム内時刻、FPS |
| 所作解析 | 最新の認識結果と、最近成立した所作 |
| ファン | 6本の出力（指示からの推定値）と、マイコンへの送信状態 |
| ディフューザー | ON/OFF（押した回数からの推定）と、押した回数 |
| エラー | bridge・マイコン・Unity（`Debug.LogError` と例外）のエラー |

設定はUnityが正本です。ブリッジは最後に変えた値を `runtime_settings.json`（`RUNTIME_SETTINGS_PATH` で変更可）に保存し、
Unityが接続するたびに送ります。Unityは反映した値を返すので、画面には「反映済み／反映待ち」が出ます。

| オプション・環境変数 | 内容 |
|---|---|
| `--admin-host` / `ADMIN_HOST` | 待ち受けるアドレス。既定は `0.0.0.0` |
| `--admin-port` / `ADMIN_PORT` | ポート。既定は `5081` |
| `--no-admin` | 設定画面を起動しない |
| `ADMIN_TOKEN` | 設定すると、URLに `?token=<値>` が必要になります |

ポートが使用中などで設定画面を起動できなくても、Unityへの配信は続けます。
WindowsではファイアウォールでPythonの受信（プライベートネットワーク）を許可してください。

WebSocketは1メッセージに1つのProtobufペイロード（バイナリ、最大8192バイト）です。
Pythonのバインディング `src/unity_bridge/gen/` はコミットしていません。
clone後やスキーマ変更後に `../proto` で次を実行して生成してください。

```bash
buf generate
```

送信間隔などの設定、メッセージ仕様、時計、期限と受信側責務は
[Unityへのジェスチャー通知](../gesture_detection/docs/unity-delivery.md)を参照してください。
Unity側の受信実装は [`suzukaze/Assets/Bridge/Gesture/`](../suzukaze/Assets/Bridge/Gesture/README.md) です。
Fedora 44 / Unity 6000.5.8f1 Editor の実通信確認結果は
[Fedora 運用ガイド](../gesture_detection/docs/fedora-protobuf.md)を参照してください。

## 既存のシリアル中継

```bash
uv run unity-bridge --serial-port COM3
uv run unity-bridge --no-serial
```

シリアルを無効にした従来モードはエコーサーバーです。
ジェスチャーを送る際は `--gesture` を指定してください。
`uv run python -m unity_bridge` でも起動できます。
WebSocket APIは[websockets公式ドキュメント](https://websockets.readthedocs.io/en/stable/reference/asyncio/server.html)
に従っています。

## 検証

```bash
uv run python -m pytest
uv run pyright
uv run ruff check src test
uv run ruff format --check src test
```

`gesture_detection` に依存するため、通常の `uv sync` は認識モデルの
依存パッケージもインストールします。統合テストは実際の子プロセス・キュー・
WebSocket・プローブ受信処理を検証し、カメラは不要です。
