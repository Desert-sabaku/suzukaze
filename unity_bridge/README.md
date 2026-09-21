# Unity bridge

`feat/unitybridge` を基盤とするWebSocket中継アプリです。Python 3.14以上を使用します。
`uv sync --group dev` で環境を用意してください。

## ジェスチャー通知

```bash
uv run python -m src.core --gesture-port 5001
```

認識側のTCP `127.0.0.1:5001` とUnityのWebSocket `ws://127.0.0.1:5000`
を接続します。このモードではシリアルポートを開きません。
Unityが未接続の間は認識側にも接続せず、UnityからのACKだけを認識側へ返します。
どちらかの接続が切れたらUnityが再接続します。同時接続は1クライアントです。

模擬Unity（実機出力なし）:

```bash
uv run python -m src.gesture_probe
uv run python -m src.gesture_probe --ignore-events
```

認識側の有効化、メッセージ仕様、時計、期限と受信側責務は
[Unityへのジェスチャー通知](../gesture_detection/docs/unity-delivery.md)を参照してください。
UnityのC#コードはこのブランチに含まれていません。

## 既存のシリアル中継

```bash
uv run python -m src.core --serial-port COM3
uv run python -m src.core --no-serial
```

シリアルを無効にした従来モードはエコーサーバーです。
ジェスチャーを接続する際は `--gesture-port` を指定してください。
WebSocket APIは[websockets公式ドキュメント](https://websockets.readthedocs.io/en/stable/reference/asyncio/server.html)
に従っています。

## 検証

```bash
uv run python -m pytest
uv run pyright
uv run ruff check src test
uv run ruff format --check src test
```
