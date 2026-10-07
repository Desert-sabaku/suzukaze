# mcu

`firmware/`(TinyGoファンコン)とUSBシリアルで通信するPythonライブラリ。
通信はprotobufの `Packet`(`../proto/micon/v1/`)を、ファームウェアと同じフレーミングで送受信します。
今後は `unity_bridge` からライブラリとして呼び出して使う予定です。

```python
from mcu import MCUClient

with MCUClient("/dev/ttyACM0") as client:
    resp = client.handshake()  # スキーマハッシュの一致を確認
    if resp.matched:
        client.send_fade(pin=25, value=200, duration_ms=1000)  # value は0-255
```

`MCUClient` の第1引数は `serial.serial_for_url` に渡すURLです。
テストでは `loop://` を使って実機なしでフレーミングとハンドシェイクを確認しています。
pyserialがポートをraw modeで開くため、`stty raw -echo`は不要です。

## 生成

`mcu/gen/` はコミットしていません。clone後やスキーマ変更後に `../proto` で生成してください。

```bash
buf generate
```

## CLI(デバッグ用)

```bash
uv run mcu --port /dev/ttyACM0
```

接続後にハンドシェイクの結果を表示し、ファームウェアのログを流しながら、
対話的に `fade`(pin・value・duration_ms)を送れます。`quit` で終了します。

## 検証

```bash
uv run pytest
uv run pyright
uv run ruff check .
```
