# 開発ガイド

以下のコマンドは `gesture_detection/` で実行します。

## パッケージ構成


アプリケーションは `src/gesture_detection/`、テストは `tests/`、
注釈用ツールは `scripts/`、評価・研究用ツールは private な `shared/scripts/` にあります。
`uv sync` でパッケージを
editableインストールしてから実行してください。旧 `modules.*` のimportは
`gesture_detection.*` に変更しています。

モデルと `.env` は引き続きこのディレクトリ直下に置きます。wheelとして
インストールする場合はデータディレクトリを環境変数 `GESTURE_PROJECT_ROOT` で
指定してください。未指定なら作業ディレクトリを使用します。この環境変数は
`.env` の探索先も決めるため、シェル側で設定します。

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

