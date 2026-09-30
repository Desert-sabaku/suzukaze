# firmware

Raspberry Pi Pico向けファームウェア(TinyGo)。ファンコン(PWMフェード制御)を実装しています。

## 構成

- `main.go`: USBシリアル経由で改行区切りのJSON `Message` を受信し、ピンごとにPWMフェードを行う
- `heartbeat.go`: オンボードLEDを点滅させ、生存確認ログを送信する

## ビルド

```bash
tinygo build -target=pico -o fan_controller.uf2 .  # ファームウェアイメージをビルド
```

BOOTSELボタンを押しながらPicoを接続し、生成された`.uf2`をマウントされたドライブにコピーして書き込みます。

## シリアルコンソールの確認

`cat /dev/ttyACM0` などで読む前に、必ず以下を実行してください。

```bash
stty -F /dev/ttyACM0 raw -echo
```

これをしないとホストの端末がecho設定のままになり、受信したバイト(ファームウェアのログ出力)をそのままデバイスに送り返してしまいます。結果としてファームウェアが自分自身のログをコマンドとして誤受信し、JSONパースエラーが発生します。
