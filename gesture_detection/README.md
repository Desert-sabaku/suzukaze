# ジェスチャー認識・カメラ録画

カメラや動画から「扇ぎ」「打ち水」「夕涼み」「礼」「ラムネ開栓」を判定します。
認識を行わず、複数のカメラを同時録画するツールも使えます。

## 準備

Python 3.12以上、[uv](https://docs.astral.sh/uv/)、使用するカメラを用意してください。
以下のコマンドはすべて `gesture_detection/` 内で実行します。

```bash
uv sync
```

## ジェスチャーを認識する

初回のみ `.env.example` を `.env` にコピーして、入力元を設定します。

```bash
cp .env.example .env
uv run gesture-detection
```

既定ではカメラ0を使用します。表示された枠に胴体の中心を合わせてください。
終了は `Esc` です。姿勢推定モデルがない場合は初回起動時に自動取得します。
単体で起動した場合はUnityへ送信しません。Unityへ送るときは `unity_bridge/` で
`uv run unity-bridge --gesture` を実行すると、この認識アプリも起動します（[Unity連携](docs/integration.md)）。

主な設定は `.env` で変更します。

| 設定           | 用途                                   |
| -------------- | -------------------------------------- |
| `CAMERA_INDEX` | 使用するカメラのID（既定 `0`）         |
| `VIDEO_SOURCE` | 動画ファイルのパス。空欄ならカメラ入力 |
| `OUTPUT_DIR`   | `VIDEO_SOURCE` の注釈付き解析結果の保存先（既定 `output/`） |

その他の設定は [.env.example](.env.example) を参照してください。
[学習済みラムネ判定](docs/learned-ramune.md)は設定で切り替えられます。

### 2カメラで認識する

`.env`で`MULTICAM_ENABLED=true`と`MULTICAM_CAMERA_INDICES=1,2`を指定します。
先頭のカメラで人物選択、2台目で全画面解析を行い、結果を統合します。
実カメラと録画セッションの設定は[Unity連携・OS別セットアップ・2カメラ](docs/integration.md)を参照してください。

## カメラ映像を録画する

通常の `gesture-detection` はライブカメラを録画しません。`OUTPUT_DIR` と
`VIDEO_OUTPUT_PATH` は既存動画の解析結果用です。カメラ録画には次の専用コマンドを使います。

使うカメラのIDを指定します。1台から利用でき、設定はコマンド引数で渡します。

```bash
uv run record-cameras --cameras 0
# 複数台の例
uv run record-cameras --cameras 0 2
```

**起動直後はプレビューのみです。`R` または `Space` を押すと、3秒後に録画が始まります。**

| キー            | 操作                                             |
| --------------- | ------------------------------------------------ |
| `R` / `Space`   | 全台の録画開始・停止。停止後に再開すると別テイク |
| `S`（Ctrlなし） | 全台の静止画をPNGで保存                          |
| `M`             | 録画中の目印を記録                               |
| `Q` / `Esc`     | 保存して終了                                     |

保存先はプロジェクト内の **`shared/videos/日時_識別子/take_001/`** です。
カメラごとの `camera_0.mp4` などと、時刻・撮影情報を保存します。
保存先を変更する場合は `--output PATH` を指定してください。
音声は収録しません。カメラ間の厳密な同期は保証しません。

解像度・FPSは `--width 640 --height 480 --fps 30` のように指定できます。
詳しいオプション、入力形式、映像が黒／緑になる場合の切り分けは
[カメラ入力・録画・トラブルシュート](docs/camera.md)を参照してください。

## 詳しい情報

- ドキュメントの入口は [docs/README.md](docs/README.md) です。
- [ジェスチャーの仕様](docs/gestures.md)・[Unity連携](docs/integration.md)
- [構成・設定・開発](docs/architecture.md)・[動画と関節位置の注釈](docs/annotation.md)

検証動画、注釈、ランドマーク、結果ファイル、顔が写る可能性のある画像は
`gesture_detection/shared` サブモジュールで管理します。本体リポジトリには、通常利用に
必要な手順と、検証結果の要約だけを置きます。
