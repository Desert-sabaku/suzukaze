# Unity bridge

`feat/unitybridge` を基盤とするWebSocket中継アプリです。Python 3.14以上を使用します。

## セットアップ

`uv sync --group dev` で環境を用意してください。`gesture_detection` に依存するため、通常の `uv sync` は認識モデルの依存パッケージもインストールします。

Pythonのバインディング `src/unity_bridge/gen/` はコミットしていません。clone後やスキーマ変更後に `../proto` で次を実行して生成してください。

```bash
buf generate
```

リポジトリ直下から `invoke proto` でも生成できます。

パッケージは `src/unity_bridge/` にあります。`src` 自体はパッケージではありません。旧 `src.*` のimportは `unity_bridge.*` に変更しています。インストール後は `unity-bridge` と `unity-gesture-probe` コマンドを使用できます。

## 起動

| コマンド(`unity_bridge/` で実行) | `invoke`(リポジトリ直下で実行) | 内容 |
|---|---|---|
| `uv run unity-bridge --gesture` | `uv run invoke unity` | 認識を子プロセスとして起動し、ジェスチャーとファンをUnityへ中継する |
| `uv run unity-bridge --fan` | なし | カメラを起動せず、ファンだけを扱う(`--gesture` は不要) |
| `uv run unity-bridge --debug-gui` | `uv run invoke unity-debug` | カメラと認識を起動せず、ブラウザから所作を送る |
| `uv run unity-gesture-probe` | `uv run invoke unity-probe` | 模擬Unity(実機出力なし) |

`invoke` のタスクは、`unity_bridge/` に移動して同じコマンドを実行します。仮想環境を有効にしていれば、`uv run` を省いて `invoke unity` と書けます。タスクの一覧は、リポジトリ直下で `invoke --list` を実行すると確認できます。

`uv run python -m unity_bridge` でも起動できます。シリアル中継の従来モードは「既存のシリアル中継」を参照してください。

## 設定

設定は、リポジトリ直下の `suzukaze.local.yaml`、`suzukaze.yaml` の順に探します。既定値はありません。どれにも書かれていないキーがあるときと、yamlに知らないキーがあるときは、起動時にエラーになります。

- `suzukaze.yaml` は共有する設定です。`suzukaze.local.yaml` はマシンごとの違い(シリアルポートなど)に使い、コミットしません。
- yamlのキーは `suzukaze.yaml` を見てください。
- ピンの一覧は、yamlの配列で書きます。
- `microcontroller_serial_port` は、`suzukaze.yaml` では Windows の `COM3` です。Linux は `/dev/ttyACM0` などになるので、`suzukaze.local.yaml` に書きます。

ピンのキーは次のとおりです。本数が違うときと、重複があるときは、どちらも起動時にエラーになります。

| キー | 本数 | 並び順 |
|---|---|---|
| `fan_pwm_pins` | 6本 | `channel` の1〜6の順。firmwareの `fanPins`(GP2〜GP7)と同じにする |
| `diffuser_pins` | 2本 | `DiffuserChannel` の値の順(ラムネ、森) |

## ファン

`--gesture` のWebSocket 1本で、ファンも扱います。ファンだけ使うときは `--fan` を使います。電文は `proto/bridge/v1/bridge.proto` の `BridgeEnvelope` です。

Unityが `fan_command`(`fan.v1.Fan`)を送ると、ブリッジが記録して、ファン6本のいまの出力を `fan_state` で返します(最初の指示を受けてから、状態通知と同じ周期)。firmwareには回転数の読み出しがないので、出力は指示から推定します(0 から value まで、firmwareと同じガンマ2.2のカーブ)。

`fan_pwm_pins` を設定すると、`mcu` ライブラリでマイコンへ `PwmFade` も送ります。ポートは `microcontroller_serial_port`、ボーレートは `microcontroller_baudrate` です。マイコンが未接続でもブリッジは落ちず、次の指示で再接続します(落とした指示は再送しません)。

## ジェスチャー通知

`gesture_detection` を子プロセスとして起動し、認識結果を `multiprocessing.Queue` で受け取って、UnityのWebSocket `ws://127.0.0.1:5000` へProtobufで送ります。このモードではシリアルポートを開きません。同時接続は1クライアントです。

状態通知・イベントの再送・UnityからのACKは、ブリッジ内の `DeliveryOutbox` が扱います。

認識側・ブリッジ・Unityは、同一Windows PCまたは同一64-bit Linux PCで実行します。Windows UnityとWSL/Linux Pythonの組み合わせには対応しません。

### 通知の内容

| フィールド | 所作の意味 |
|---|---|
| `State.gesture` | 継続中の所作(扇ぎ・夕涼み・礼)。ない場合は `NONE` |
| `Event.gesture` | 新規に成立した所作(ラムネ・打ち水)。成立ごとにイベントとして配送 |
| `State.action / phase` | 進行中の所作とその段階。準備中・成立後の状態も含む |

状態通知には、準備を含む進行状態として、省略可能なenum `action` と `phase` も送ります(例: `gesture: NONE, action: RAMUNE, phase: READY`)。

- 両フィールドは一緒に存在し、アイドル・追跡喪失・失効時は省略します。
- `action` と `phase` は、受信実装READMEに記載した組み合わせだけを許容します。`RAMUNE / NONE` などの未定義の組み合わせは、送受信で拒否します。
- phaseの値とUnity側の利用例は、受信実装READMEを参照してください。
- `unity-gesture-probe` でも表示されます。
- phaseは最新状態であり、すべての段階の到達・順序を保証しません。成立の通知には、phaseではなく、再送・ACKのあるイベントを使用してください。

### 型の対応

- Python側の所作・フェーズは `gesture_detection.gesture_types.Gesture / Phase` に、許容する組み合わせは同モジュールの `ACTION_PHASES` に集約しています。
- 認識器・ブリッジでこの `StrEnum` を共用し、通信時はProtobufから生成したenumに変換します。
- JSONの表示は `RAMUNE / READY` などの文字列です。
- 旧文字列フィールドのタグ11・12は予約し、enum版はタグ13・14を使用します。

WebSocketは1メッセージに1つのProtobufペイロード(バイナリ、最大8192バイト)です。

### 模擬Unity

```bash
uv run unity-gesture-probe
uv run unity-gesture-probe --ignore-events
```

### デバッグGUI

カメラと `gesture_detection` を起動せずに、ブラウザから所作をUnityへ送ります。

```bash
uv run unity-bridge --debug-gui
```

ブラウザで `http://127.0.0.1:5080/` を開いてください。ポートは `--debug-port` か、yamlの `gesture_debug_port` で変更できます。Unityの接続先は通常どおり `ws://127.0.0.1:5000` で、ファンも `--gesture` と同じように扱います。`--fan` とは併用できません。

送った値は認識結果と同じ `DeliveryOutbox` を通るので、状態の再送・イベントの再送・ACKの扱いは本番と同じです。画面では次の操作ができます。

- 継続所作(`State.gesture`)・`tracking`・`booth_present`・`action_accuracy` の切り替え
- 進行状態(`action / phase`)の切り替え。許容する組み合わせだけを選べます
- ラムネ・打ち水のイベント送信と、準備のphaseを順に送ってから成立させるシーケンス
- 未ACKのイベントと、UnityからのACKの一覧

キーボードでは次のキーを使えます。

| キー | 操作 |
|---|---|
| `1`〜`4` | 継続所作の切り替え |
| `T` | 追跡の切り替え |
| `B` | 在室の切り替え |
| `R` | ラムネを送る |
| `U` | 打ち水を送る |

### 関連ドキュメント

- 送信間隔などの設定、メッセージ仕様、時計、期限と受信側責務は、[Unityへのジェスチャー通知](../gesture_detection/docs/unity-delivery.md)を参照してください。
- Unity側の受信実装は [`suzukaze/Assets/Bridge/Gesture/`](../suzukaze/Assets/Bridge/Gesture/README.md) です。
- Fedora 44 / Unity 6000.5.8f1 Editor の実通信確認結果は、[Fedora 運用ガイド](../gesture_detection/docs/fedora-protobuf.md)を参照してください。

## 既存のシリアル中継

```bash
uv run unity-bridge --serial-port COM3
uv run unity-bridge --no-serial
```

シリアルを無効にした従来モードは、エコーサーバーです。ジェスチャーを送る際は `--gesture` を指定してください。WebSocket APIは[websockets公式ドキュメント](https://websockets.readthedocs.io/en/stable/reference/asyncio/server.html)に従っています。

## 検証

```bash
uv run python -m pytest
uv run pyright
uv run ruff check src test
uv run ruff format --check src test
```

pytestは、リポジトリ直下から `invoke unity-tests` でも実行できます。統合テストは、実際の子プロセス・キュー・WebSocket・プローブ受信処理を検証し、カメラは不要です。
