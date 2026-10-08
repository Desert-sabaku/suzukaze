# ジェスチャー認識・カメラ録画

カメラや動画から「扇ぎ」「打ち水」「夕涼み」「礼」「ラムネ開栓」を判定します。
認識をせずに複数のカメラを同時録画するツールもあります。

## 準備

Python 3.12以上、[uv](https://docs.astral.sh/uv/)、使用するカメラを用意してください。
以下のコマンドはすべて `gesture_detection/` 内で実行します。

```bash
uv sync
```

## ジェスチャーを認識する

初回のみ `config.example.toml` を `config.toml` にコピーして、入力元を設定します。

```bash
cp config.example.toml config.toml
uv run gesture-detection
```

ライブ入力では起動時に候補カメラの映像を表示します。数字キーで使用するカメラを選びます。
表示された枠に胴体の中心を合わせてください。
`Esc` で終了します。姿勢推定モデルがない場合は初回起動時に自動取得します。
単体で起動した場合、認識結果はUnityへ送信しません。Unityへ送るときは `unity_bridge/` で
`uv run unity-bridge --gesture` を実行します。このコマンドで認識アプリも起動します（[Unity連携](docs/integration.md)）。

主な設定は `config.toml` で変更します。ファイルがなければ既定値を使います。

| 設定 | 用途 |
| ---- | ---- |
| `camera.indices` | カメラ番号の配列。空なら起動時に映像から選択 |
| `video.source` | 動画ファイルのパス。空欄ならカメラ入力 |
| `output.directory` | 認識結果の保存先（既定 `output/`） |
| `output.record_live` | `true` なら認識中の表示映像を保存 |

その他の設定は [config.example.toml](config.example.toml) を参照してください。
従来の `.env` は読み込みません。[移行対応表](docs/configuration.md)に従って値を移してください。
ファイルの場所は `GESTURE_CONFIG_PATH`（相対指定はプロジェクトルート基準）で変更できます。
[学習済みラムネ判定](docs/learned-ramune.md)は設定で切り替えられます。

### 2カメラで認識する

`config.toml` の `[multicam]` で `enabled = true` を指定します。起動時に2台を役割順に選ぶか、
画面なしでは `[camera]` に `indices = [1, 2]` のように指定します。
先頭のカメラで人物を選択し、2台目では全画面を解析します。両方の結果を統合します。
実カメラと録画セッションの設定は[Unity連携・OS別セットアップ・2カメラ](docs/integration.md)を参照してください。

## カメラ映像を録画する

通常の `gesture-detection` はライブカメラを録画しません。`OUTPUT_DIR` と
`VIDEO_OUTPUT_PATH` は既存動画の解析結果用です。カメラの録画には次の専用コマンドを使います。

使用するカメラのIDを指定します。1台から利用でき、設定はコマンド引数で渡します。

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

- [ジェスチャー仕様](docs/gestures.md): 5種類の所作と成立条件
- [カメラ入力・録画・トラブルシュート](docs/camera.md): 録画、入力形式、カメラの障害
- [設定ファイル](docs/configuration.md): TOML設定と旧 `.env` からの移行
- [実演者の選択](docs/subject-selection.md): 複数人が映る場合の対象選択
- [実機での確認項目](docs/manual-testing.md): 起動後の確認項目
- [Unity連携・OS別セットアップ・2カメラ](docs/integration.md): 通信仕様、Windows/Linux、2カメラ認識
- [打ち水のUnity演出](docs/uchimizu-unity.md): 水パーティクルへの接続
- [構成・設定・開発](docs/architecture.md): 責任範囲、時刻・入力、品質確認
- [学習済みラムネ判定](docs/learned-ramune.md): 任意の学習済み判定器
- [動画・関節位置の注釈](docs/annotation.md): 注釈ツールと記録基準
- [評価記録・再現手順](docs/evaluations.md): 現行実装へ反映した結論、全所作と部分的な関節注釈の評価
- [礼の動画評価](docs/bow-evaluation.md): 注釈済みの2カメラ動画による判定比較
- [詳細な評価記録](https://github.com/Desert-sabaku/suzukaze/wiki): GitHub Wikiで管理

日付付きの評価レポート、JSONなどの結果ファイル、比較画像、検証動画、注釈、ランドマーク、顔が写る
可能性のある素材は通常の利用者向け資料ではありません。検証データは
`gesture_detection/shared` サブモジュールで管理します。本体リポジトリの公開ドキュメントには、
通常の利用に必要な手順、検証結果の要約と再現手順へのリンクだけを置きます。
