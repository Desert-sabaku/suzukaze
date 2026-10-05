# firmware

Raspberry Pi Pico向けファームウェア(TinyGo)。ファンコン(PWMフェード制御)を実装しています。
ホスト側のクライアントは [`mcu/`](../mcu/README.md) です。

## 構成

- `cmd/main.go`: USBシリアルの受信ループ。受け取った `Packet` を各ハンドラへ振り分ける
- `cmd/packet.go`: フレーミング(`SZ 0xAA 0x55` の4バイト + 2バイトBE長 + protobufの `Packet`、最大512バイト)
- `cmd/handlers.go`: `HandshakeReq` に自分の `VersionInfo` を返す(スキーマハッシュで一致判定)
- `cmd/pwm.go`: `PwmFade`(`value` は0-255)をピンごとのPWMフェードに変換する
- `cmd/heartbeat.go`: オンボードLEDを点滅させ、生存確認ログを送信する
- `cmd/logger.go`: ホストへ送る `LogEntry`

スキーマは `../proto/micon/v1/*.proto` です。

## 生成

`gen/` はコミットしていません。clone後やスキーマ変更後に `../proto` で生成してください。

```bash
buf generate
```

## ビルド

```bash
make build  # firmware.uf2 をビルド
make flash  # tinygo flash で直接書き込む
```

`Makefile` はコミットハッシュ(`git describe --always --dirty`)と、
`proto/micon/v1/*.proto` のsha256先頭8文字をスキーマハッシュとして埋め込みます。
ハンドシェイクではスキーマハッシュだけで一致を判定します。

`make build` の `.uf2` を使う場合は、BOOTSELボタンを押しながらPicoを接続し、
マウントされたドライブにコピーして書き込みます。

## シリアルコンソールの確認

`cat /dev/ttyACM0` などで読む前に、必ず以下を実行してください。

```bash
stty -F /dev/ttyACM0 raw -echo
```

これをしないとホストの端末がecho設定のままになり、受信したバイト(ファームウェアのログ出力)をそのままデバイスに送り返してしまいます。結果としてファームウェアが自分自身の出力をコマンドとして誤受信します。
通常は `mcu` のCLI(`uv run mcu --port /dev/ttyACM0`)を使えば、pyserialがraw modeで開くためこの設定は不要です。
