# 実験データ

撮影・注釈・評価で使うデータをまとめるディレクトリです。

```text
shared/
  videos/        元動画
  annotations/   動画ごとの注釈セッション（PNG、CSV、source.json）
  results/       評価結果や推論出力
```

新しい動画を `videos/` に配置し、`gesture_detection/` から実行します。

```bash
uv run python -m scripts.annotate_landmarks shared/videos/打ち水btn.mp4
uv run python -m scripts.annotate_landmarks --resume shared/annotations/打ち水btn
```

注釈ツールは入力動画の場所にかかわらず `shared/annotations/<動画名>/` に保存します。
同名の動画は `--output shared/annotations/<一意のセッション名>` で区別してください。
操作は [注釈の手順](../docs/landmark-annotation.md) を参照してください。

評価スクリプトには入力先と結果の保存先を明示できます。例：

```bash
uv run python -m scripts.evaluate_curtain --sample-dir shared/videos --output shared/results/curtain-comparison.json
```

既存の `sample_movies/`、`output/` と過去の評価レポートは自動移動しません。
以前の注釈は従来のパスを `--resume` に渡せば再開できます。
注釈を移す場合はPNG・CSV・source.jsonを含むセッションディレクトリ全体を移してください。
source.json内の元動画の絶対パスは撮影資料の参照情報として残り、移動先には自動更新されません。
再開に元動画は不要です。

データ本体はGit管理対象外です。ここでいうsharedは配置の共通化であり、他のPCへの
自動同期ではありません。共有・バックアップにはこのディレクトリを別途コピーしてください。
コードとともに残す評価レポートは従来どおり `docs/` に置けます。
