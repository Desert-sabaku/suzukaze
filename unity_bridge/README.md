# Unity bridge

`feat/unitybridge` を基盤とするWebSocket中継アプリです。Python 3.14以上を使用します。
`uv sync --group dev` で環境を用意してください。

パッケージは `src/unity_bridge/` にあります。`src` 自体はパッケージでは
ありません。旧 `src.*` のimportは `unity_bridge.*` に変更しています。
インストール後は `unity-bridge` と `unity-gesture-probe` コマンドを使用できます。

## ジェスチャー通知

```bash
uv run unity-bridge --gesture
```

`gesture_detection` を子プロセスとして起動し、認識結果を `multiprocessing.Queue`
で受け取って、UnityのWebSocket `ws://127.0.0.1:5000` へProtobufで送ります。
このモードではシリアルポートを開きません。同時接続は1クライアントです。
状態通知・イベントの再送・UnityからのACKはブリッジ内の `DeliveryOutbox` が扱います。
状態通知には、準備を含む進行状態として任意の文字列 `phase_action` と `phase` も
送ります（例: `gesture: NONE, phase_action: RAMUNE, phase: READY`）。両フィールドは
一緒に存在し、アイドル・追跡喪失・失効時は省略します。`unity-gesture-probe` でも
表示されます。phaseの値とUnity側の利用例は下記の受信実装READMEを参照してください。
`phase_action` は既知の動作名に限定し、`phase` は拡張可能な空でない文字列です。
phaseは最新状態であり、すべての段階の到達・順序を保証しません。成立の通知には
phaseではなく、再送・ACKのあるイベントを使用してください。
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
