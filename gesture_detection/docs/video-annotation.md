# 動画の時系列注釈

動画を再生しながら、任意のフレームへ動作区間、構えや節目、関節点を記録します。
既存の代表フレーム用 `annotate-landmarks` とは独立したツールです。

```bash
uv run annotate-video shared/videos/bright-behind-the-screen/aogi1_3-8.mp4
```

既定では次の場所へ保存し、同じコマンドを再実行すると自動的に再開します。

```text
shared/annotations/bright-behind-the-screen/aogi1_3-8/timeline.json
```

保存先は `--output`、ラベル定義は `--labels` で変更できます。作成済みの
`annotations.csv` が同じディレクトリにあれば、初回だけ関節点を自動で取り込みます。
別の旧セッションは `--import-landmarks` で指定できます。

```bash
uv run annotate-video VIDEO --import-landmarks OLD_SESSION_DIRECTORY
```

## 操作

- 右側のラベルを選び、`SET START` と `SET END` で区間を記録します。異なるトラックの区間は重ねられます。
- イベント名をクリックすると、現在フレームへ節目を記録します。
- 関節名を選んで画像をクリックすると、元画像ピクセル座標を記録します。
- タイムラインをクリックするとシークし、その位置の区間またはイベントを選択します。選択後は端点移動や削除ができます。
- すべての編集は `timeline.json` へ原子的に自動保存されます。

| キー | 操作 |
| --- | --- |
| Space | 再生・一時停止 |
| A / D | 1フレーム戻る／進む |
| J / L | 10フレーム戻る／進む |
| S / E | 区間の開始／終了を設定 |
| U / X | 選択関節を不明／現在フレームを被写体不在にする |
| Z / Y | Undo / Redo |
| `[` / `]` | 再生速度を下げる／上げる |
| Backspace / Delete | 選択した区間またはイベントを削除 |
| Q / Esc | 保存して終了 |

`timeline.json` ではフレームIDを正本とし、FPSから計算した時刻も併記します。動画の
SHA-256、総フレーム数、解像度が一致しない場合は、誤った動画への再開を拒否します。
