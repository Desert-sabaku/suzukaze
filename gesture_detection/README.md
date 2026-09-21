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

`uv run python -m modules.app` でも起動できます。終了するには表示ウィンドウで
`Esc` を押します。入力元や出力先は `.env` で設定します。

## ドキュメント

- [ジェスチャー仕様](docs/gestures.md) — 現在の判定仕様の正本
- [アーキテクチャ](docs/architecture.md) — 入出力、時刻、並行処理、設定
- [手動テスト](docs/manual-testing.md) — カメラ・動画で確認する項目
- [過去の評価](docs/evaluations.md) — 検証結果、生データ、現在の採否
- [関節位置の手動ラベル付け](docs/landmark-annotation.md) — 評価用の正解データ作成

補助的な情報はWikiの
[トラブルシュートと運用メモ](https://github.com/Desert-sabaku/suzukaze/wiki/%E3%83%88%E3%83%A9%E3%83%96%E3%83%AB%E3%82%B7%E3%83%A5%E3%83%BC%E3%83%88%E3%81%A8%E9%81%8B%E7%94%A8%E3%83%A1%E3%83%A2)
を参照してください。

## 品質確認

```bash
uv sync --group dev
uv run ruff format --check $(git ls-files '*.py')
uv run ruff check $(git ls-files '*.py')
uv run pyright
uv run python -m pytest
```

構文だけを確認する場合は `uv run python -m compileall modules` を実行します。
Pull Request では Ruff、Pyright、Pytest とカバレッジ計測を実行します。
