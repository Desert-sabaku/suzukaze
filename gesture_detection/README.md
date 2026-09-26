# ジェスチャー認識

カメラまたは動画を MediaPipe Pose で解析し、「扇ぎ」「打ち水」「夕涼み」
「ラムネ開栓」の4動作を判定するアプリケーションです。物体や小道具は判定に使わず、
通常の実行では YOLO を起動しません。

## 実行

Python 3.12 以上と `uv` を使用します。

```bash
uv sync
cp .env.example .env
uv run gesture-detection
```

`uv run python -m gesture_detection` でも起動できます。終了するには表示ウィンドウで
`Esc` を押します。入力元や出力先は `.env` で設定します。

## パッケージ構成

アプリケーションは `src/gesture_detection/`、テストは `tests/`、
評価用スクリプトは `scripts/` にあります。`uv sync` でパッケージを
editableインストールしてから実行してください。旧 `modules.*` のimportは
`gesture_detection.*` に変更しています。

モデルと `.env` は引き続きこのディレクトリ直下に置きます。wheelとして
インストールする場合はデータディレクトリを環境変数 `GESTURE_PROJECT_ROOT` で
指定してください。未指定なら作業ディレクトリを使用します。この環境変数は
`.env` の探索先も決めるため、シェル側で設定します。

## ドキュメント

- [ジェスチャー仕様](docs/gestures.md) — 現在の判定仕様の正本
- [アーキテクチャ](docs/architecture.md) — 入出力、時刻、並行処理、設定
- [Unityへの通知](docs/unity-delivery.md) — 状態・成立イベント・ACKと接続手順
- [手動テスト](docs/manual-testing.md) — カメラ・動画で確認する項目
- [過去の評価](docs/evaluations.md) — 検証結果、生データ、現在の採否
- [関節位置の手動ラベル付け](docs/landmark-annotation.md) — 評価用の正解データ作成

補助的な情報はWikiの
[トラブルシュートと運用メモ](https://github.com/Desert-sabaku/suzukaze/wiki/%E3%83%88%E3%83%A9%E3%83%96%E3%83%AB%E3%82%B7%E3%83%A5%E3%83%BC%E3%83%88%E3%81%A8%E9%81%8B%E7%94%A8%E3%83%A1%E3%83%A2)
を参照してください。

## 品質確認

```bash
uv sync --group dev
uv run ruff format --check src tests scripts main.py
uv run ruff check src tests scripts main.py
uv run pyright
uv run python -m pytest
```

構文だけを確認する場合は `uv run python -m compileall src` を実行します。
Pull Request では Ruff、Pyright、Pytest とカバレッジ計測を実行します。

幕越しの明るい環境・白い服での評価と、骨格表示の平滑化については
[追加評価](docs/bright-curtain.md)を参照してください。
VIDEOモードでは骨格表示を平滑化します。`POSE_DISPLAY_SMOOTHING=false`で無効化できます。
所作判定には元の推定座標を使用します。

VIDEOモードでは[背景人物を避けた実演者追跡](docs/subject-selection.md)が標準で有効です。
取得時だけ背景を隠し、取得後は全画面で追跡します。枠に胴体中心を置いてください。
`.env` の `SUBJECT_AREA` と人物サイズ下限で設置環境に合わせられます。
`POSE_SELECT_SUBJECT=false` で従来方式へ戻せます。

### 0924 の action / phase 注釈による予備学習

動画単位で学習・評価を分離した比較結果と再現コマンドは、
[0924 action・phase 評価](docs/0924-timeline.md)を参照してください。
学習器は実験用で、本番の判定には組み込んでいません。

ラムネの連続表示と再出現を分けた追加実験は、
[OPENEDの表示保持・再発火抑制](docs/0924-opening-temporal.md)にまとめています。

[再許可・連続試行の追試](docs/0924-opening-rearm.md)では、
前回候補が2回目を抑制する問題と、解除条件の代案を記録しています。

[準備待ち・見逃しの原因分析](docs/0924-opening-setup.md)では、
0924の見逃し3件は準備後のphase判定に残ることを確認しました。
準備条件の緩和は改善せず、再出現も増えるため採用していません。

[相対位置・動きの特徴量比較](docs/0924-opening-features.md)では、
相対位置の追加で幕越しの開栓検出が5/7件から6/7件へ改善しました。
再出現0件を維持した探索候補で、本番未統合です。

最新の[開栓スコア診断](docs/0924-opening-scores.md)では、
残る2件の見逃しはOPENEDが3～4位であることを確認しました。
判定を変えずに全phaseのスコアと状態遷移を記録しています。
