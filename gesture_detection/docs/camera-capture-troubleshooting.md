# WSL2でカメラ画像の下部が黒／緑になる現象

## 2026-09-27の切り分け

対象はHD Webcam C615（046d:082c）。Windows標準カメラアプリでは正常に映ることを
ユーザーが確認した。WSL2へ再アタッチ後も、以下の取得試験で欠損を再現した。

- WSLカーネル: `6.18.33.2-microsoft-standard-WSL2`
- 接続経路: USB/IP → `vhci_hcd` → `uvcvideo`
- usbipd-win: `5.3.0-54+Branch.master.Sha.aa3db8b82c4cb5071fd31bc54211606c70886912`
- 入力: YUYV、640×480、30fps（機器の対応モードであることを確認済み）

録画アプリのSキーで保存したPNGでは、下456行／全480行がBGR `(0,154,0)`。
これはゼロ埋めのYUYVをOpenCVで変換した色と一致した。PNG自体に存在するため、
プレビューの余白やQtのウィンドウ表示だけの問題ではない。

続いて、録画アプリとOpenCVを使わずに直接取得した。

```bash
# 録画アプリを終了して実行。最大15秒で終了する。
timeout 15s v4l2-ctl --device /dev/video0 \
  --set-fmt-video=width=640,height=480,pixelformat=YUYV --set-parm=30 \
  --stream-mmap=4 --stream-count=3 --stream-to=/tmp/camera0-yuyv.raw --verbose
```

正常な1枚は640×480×2 = 614,400バイト必要だが、受信バッファの`bytesused`は
主に5,120〜29,504バイトで、`(error, ts-monotonic, ts-src-soe)` が付いていた。
15秒のタイムアウトまで正常な3枚を取得できず、出力は0バイトだった。
`--stream-count=3`でもエラーフレームを数えず待ち続けるため、タイムアウトを付ける。

この結果から、少なくとも当該試験では録画アプリより手前のWSLの取得経路で
欠損が発生している。USB/IPサーバー・仮想USBホスト・Linuxドライバのどれが
根本原因かは未確定。アプリで欠損領域を切り取ったり色を置換しても映像は復元しない。
Windows標準アプリでの正常動作は確認済みだが、本録画スクリプトのWindows実機検証は未実施。

## 次の切り分け

- Windows側で同じ録画スクリプトを動かし、USB/IP経路を外して比較する。
- WSLで続ける場合は、usbipd-win／WSLのバージョン比較や低FPSでの直接取得を行う。
  更新・再起動は他のWSL作業へ影響するため、この調査では実施していない。
- Windowsでカメラを使う前はWSLからデタッチする。
  [MicrosoftのUSB接続手順](https://learn.microsoft.com/en-us/windows/wsl/connect-usb)を参照。

Qtの`saveView`拡張子エラーは別件。本アプリでは標準ツールバーを非表示にし、
該当エラーだけを録画終了の対象から除外した。静止画はCtrlなしのSキーで保存する。
