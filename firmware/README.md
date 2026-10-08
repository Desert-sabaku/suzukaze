# firmware

Raspberry Pi Pico向けファームウェア(TinyGo)。ファンコン(PWMフェード制御)と、単押しボタン用のGPIOパルスを実装しています。
ホスト側のクライアントは [`mcu/`](../mcu/README.md) です。

## 構成

- `cmd/main.go`: USBシリアルの受信ループ。受け取った `Packet` を各ハンドラへ振り分ける
- `cmd/packet.go`: フレーミング(`SZ 0xAA 0x55` の4バイト + 2バイトBE長 + protobufの `Packet`、最大512バイト)
- `cmd/handlers.go`: `HandshakeReq` に自分の `VersionInfo` を返す(スキーマハッシュで一致判定)
- `cmd/pwm.go`: `PwmFade`(`value` は0-255)をピンごとのPWMフェードに変換する
- `cmd/gpio.go`: `GpioPulse` を受け取り、指定ピンを `duration_ms` だけ HIGH にして LOW に戻す
- `cmd/heartbeat.go`: オンボードLEDを1秒ごとに点滅させ、2秒ごとに生存確認ログを送信する
- `cmd/logger.go`: ホストへ送る `LogEntry`

スキーマは `../proto/micon/v1/*.proto` です。

## 受け取るコマンド

| `Packet` | 動作 |
| --- | --- |
| `HandshakeReq` | 自分の `VersionInfo` を返す。`matched` はスキーマハッシュだけで決める |
| `PwmFade` | 指定ピンのPWMを、`duration_ms` かけて0から `value`(0-255)まで上げる。実行中のフェードは新しい指示で中断される。`duration_ms` が0なら即座に切り替える |
| `GpioPulse` | 指定ピンを `duration_ms` だけ HIGH にして LOW に戻す。受信ループを止めないよう、別goroutineで実行する |

どのピンを使うかは、ホスト側(`unity_bridge` の `FAN_PWM_PINS` と `DIFFUSER_PINS`)が決めます。
ファームウェアは、受け取ったピンを検査せずにそのまま使います。
ファンのピンに `GpioPulse` を送ると、ファンの出力が壊れます。

## ハードウェアの前提

### ファン(PWM)

- ファンのPWM線は、PC817(フォトカプラ)経由でつなぎます。出力が反転するため、`pwm.go` の `pwmInverted` が `true` のときは、デューティを反転して出します。`PwmFade.value` は、反転していても大きいほど速くなります。
- **GPIOをファンのPWM線へ直接つないではいけません。** マイコンが壊れた実績があります。
- PWM周期は1kHzです(`pwmPeriod`)。4ピンファンの規格(21〜28kHz)から外れますが、PC817を25kHzで駆動すると中間のデューティが通らなかったため、下げています。確認できたファンは Thermalright TL-C12C だけです。
- 速度の曲線は、ガンマ2.2です。
- 起動時に、`fanPins`(GP2〜GP7)を最小(`value=0`)で出力します。ホストの指示を待たずに、ファンを止めておくためです。反転配線では、ピンがLowのままだとファンが全開になります。ピンを変えるときは、`fanPins` も直してください。
- RP2040のPWMは、1スライスを2ピンで共有します(GP2/3、GP4/5、GP6/7)。スライスは最初の1回だけ `Configure` します。`Configure` は両チャンネルのレベルを0に戻すためです。

### ディフューザー(GPIOパルス)

- ボタンの接点は、PC817で短絡します。GPIOを直接つながないでください。
- 電源は別系統にします。Picoの VBUS からは取りません。

## 動作の確認

次のように測ると、書き込んだ内容を確かめられます(PC817を外した状態)。

- 起動直後は、GP2〜GP7がすべて約3.3V(最小)になります。
- `PwmFade(value=128, duration_ms=0)` を送ると、そのピンは約2.6Vになります。`value=255` なら約0Vです。

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

`make flash` は、PicoがBOOTSELに入っても、`RPI-RP2` が自動マウントされず、
`unable to locate any volume: [RPI-RP2]` で失敗することがあります。
その場合は、手動でマウントして `firmware.uf2` をコピーしてください。

```bash
make build
udisksctl mount -b /dev/sda1  # デバイス名は lsblk で確認する
cp firmware.uf2 /run/media/$USER/RPI-RP2/
```

## シリアルコンソールの確認

`cat /dev/ttyACM0` などで読む前に、必ず以下を実行してください。

```bash
stty -F /dev/ttyACM0 raw -echo
```

これをしないとホストの端末がecho設定のままになり、受信したバイト(ファームウェアのログ出力)をそのままデバイスに送り返してしまいます。結果としてファームウェアが自分自身の出力をコマンドとして誤受信します。
通常は `mcu` のCLI(`uv run mcu --port /dev/ttyACM0`)を使えば、pyserialがraw modeで開くためこの設定は不要です。
