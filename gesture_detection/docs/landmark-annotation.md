# 関節位置の手動ラベル付け

`gesture_detection/` から実行します。

```bash
uv run python -m scripts.annotate_landmarks sample_movies/打ち水btn.mp4
```

先頭と末尾を含めて均等に8フレームを抽出し、既定では
`output/annotations/<動画名>/` に保存します。`--count`、`--frames`、`--output`で変更できます。

```bash
uv run python -m scripts.annotate_landmarks --resume output/annotations/打ち水btn
```

| 操作 | 内容 |
| --- | --- |
| 左クリック | 現在の点を指定して次へ進む |
| U | 点を判別困難として記録 |
| A | フレームの全6点を被写体不在 (`absent`) にする |
| R | フレームの全6点を未入力へ戻す |
| 1〜6 | 同じフレーム内の点を選択 |
| C / Z | 選択点を消す／ひとつ前へ戻る |
| N / P | 次／前のフレームへ移動 |
| Q / Esc | 終了 |

各編集はCSVへ自動保存されます。被写体はいるが幕などで点が見えない場合は `U`、
被写体自体がいない場合だけ `A` を使用します。状態は `marked`、`uncertain`、
`pending`、`absent` の4種類で、`marked` 以外の座標は空欄です。
