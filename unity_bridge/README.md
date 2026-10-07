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
