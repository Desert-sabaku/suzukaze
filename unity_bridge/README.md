# Unity bridge

`feat/unitybridge` を基盤とするWebSocket中継アプリです。Python 3.14以上を使用します。
`uv sync --group dev` で環境を用意してください。

パッケージは `src/unity_bridge/` にあります。`src` 自体はパッケージでは
ありません。旧 `src.*` のimportは `unity_bridge.*` に変更しています。
インストール後は `unity-bridge` と `unity-gesture-probe` コマンドを使用できます。

## ジェスチャー通知

```bash
uv run unity-bridge --gesture-port 5001
```

認識側のTCP `127.0.0.1:5001` とUnityのWebSocket `ws://127.0.0.1:5000`
を接続します。認識側・ブリッジ・Unityは同一Windows PCまたは同一64-bit Linux PCで実行します。
Windows UnityとWSL/Linux Pythonの組み合わせには対応しません。
このモードではシリアルポートを開きません。
Unityが未接続の間は認識側にも接続せず、UnityからのACKだけを認識側へ返します。
どちらかの接続が切れたらUnityが再接続します。同時接続は1クライアントです。

模擬Unity（実機出力なし）:

```bash
uv run unity-gesture-probe
uv run unity-gesture-probe --ignore-events
```

既定の形式はバイナリのProtobufです。上のコマンドは形式指定なしでProtobufを使います。
新しいUnity受信実装はProtobuf専用です。旧Python受信側とのJSON互換モードは、
認識側に `GESTURE_DELIVERY_FORMAT=json` を設定し、明示的に選択してください:

```bash
uv run unity-bridge --gesture-port 5001 --gesture-format json
uv run unity-gesture-probe --format json
```

両CLIは `GESTURE_DELIVERY_FORMAT=json|protobuf` も読みます（CLI指定が優先、未設定はProtobuf）。
認識側・ブリッジ・受信側で同じ形式にしてください。自動判別はありません。
ProtobufはTCPの4バイトBE長付きフレームと、WebSocketのバイナリメッセージ
（1ペイロード、ヘッダーなし）を使い、最大8192バイトです。検証後も元ペイロードを
転送して未知フィールドを保持します。シリアル中継は別モードです。

認識側の有効化、メッセージ仕様、時計、期限と受信側責務は
[Unityへのジェスチャー通知](../gesture_detection/docs/unity-delivery.md)を参照してください。
認識側の `GESTURE_DELIVERY_ENABLED` は引き続き既定で `false` です。
仕様のJSON例やプローブのJSON出力は診断用表現で、既定の通信はProtobufバイナリです。
同梱の[C#受信実装と診断Prefab](../suzukaze/Assets/GestureDelivery/README.md)を
Unityへの組み込みに使用できます。Unity Windows Editor/standalone（Mono/IL2CPP）の
実機検証は未完了で、Pythonテストはその代替にはなりません。
Fedora 44 / Unity 6000.5.8f1 Editor の実通信確認結果と起動方法は
[Fedora 運用ガイド](../gesture_detection/docs/fedora-protobuf.md)を参照してください。

## 既存のシリアル中継

```bash
uv run unity-bridge --serial-port COM3
uv run unity-bridge --no-serial
```

シリアルを無効にした従来モードはエコーサーバーです。
ジェスチャーを接続する際は `--gesture-port` を指定してください。
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

両Pythonプロジェクトは軽量な `../gesture_protocol` を直接依存として使います。
既存の `gesture_detection` 依存もあるため、通常の `uv sync` は認識モデルの
依存パッケージもインストールします。統合テストは実際のTCPサーバー・WebSocket
中継・プローブ受信処理をJSON/Protobufの両形式で検証し、カメラは不要です。
