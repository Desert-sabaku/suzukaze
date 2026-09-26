# 相対位置モデルのアプリ組み込み

2026-09-26。現ブランチへ研究成果を段階別にコミットし、ラムネ判定を選択式で追加した。
mainへのマージ・リモートへのpushは実施していない。

## 反映した成果

- 0924の相対位置特徴を使うphase分類器と、準備・解除判定用のaction分類器。
- 初回・再準備の連続確認0.3秒、開栓表示保持0.75秒、観測された非RAMUNEによる解除0.6秒。
- 学習条件と同じ、画面横方向35～75%を残す常時中央マスク。元の表示画像は変更しない。

速度特徴と、actionを要求しない準備条件は悪化が確認されたため採用しない。学習済みactionの
RELAXINGをアプリの表示に直接使わず、扇ぎ・打ち水・涼む動作の判定器は従来のものを使う。
ただし骨格入力の条件は中央マスクへ変わるので、他動作の実環境での精度維持を証明したものではない。

## 利用方法と互換性

`.env` に `RAMUNE_DETECTOR=learned` と `POSE_RUNNING_MODE=VIDEO` を設定して通常通り起動する。
既定は `rules` のままで、切り戻しも設定変更と再起動で行う。カメラ入力・動画入力の両方で使用できる。

学習済みモードでは人物選択を無効にし、モデル内の中央マスク範囲を使用する。
`POSE_SELECT_SUBJECT` と `SUBJECT_AREA` による追跡条件はこのモードに適用しない。
IMAGEモードとの併用、モデルの欠落・非対応形式・不正な重みは明示的なエラーにする。
読み込みに失敗したときに従来判定へ黙って切り替えることはしない。

`RAMUNE_LEARNED_MODEL_PATH` を空にすると同梱モデルを使う。独自モデルの相対パスは従来通り
プロジェクトルート基準。NPZはpickleを許可せず読み込む。学習データ、研究スクリプト、追加依存は
アプリの実行に不要で、wheelにもモデルと来歴JSONを含める。

公開する `current`、`occurrences`、frame ID、timestampの形式は変更しない。開栓通知は
連続表示の開始時に1回だけ出す。学習済みモードでは骨格欠落時もロック状態を保持する。
欠落中の画面状態は従来通りNONE・tracking=Falseであり、欠落を「手を離した」と数えない。

## フレーム処理

動画・カメラから取得したfpsをworkerへ渡す。取得不能時は既存のFPS設定を使う。
履歴は学習時と同じ `round(history_seconds × source_fps)` 標本で、最大履歴長に制限したdequeを使う。
表示用の平滑化前の骨格から、元の96次元特徴と相対位置14次元を生成する。

カメラworkerでフレームが飛んだ場合は、その標本を欠落として扱い、準備・解除の継続時間を切る。
0.5秒超の処理間隔では特徴量履歴を消去し、準備済み状態は再確認を要求する。
開栓済みロックを欠落だけで解除せず、保持期限を過ぎた表示も欠落後に新しい開栓として再通知しない。
逆順の時刻・frame IDはエラーにし、新しい入力ストリームは新しいAnalyzerで開始する。

この欠落処理は実時間入力向けの保守的な追加仕様。全フレームを順番に処理する0924の再生では
研究時の特徴量・判定を再現するが、実カメラでの処理落ちを含む検出率はまだ測定していない。

## モデルと評価の区別

同梱 `ramune_0924.npz` は幕越し12動画すべてで学習した配布用モデル。
actionは既存96次元、phaseは相対位置込み110次元を使い、各設定は以前の幕なし評価用に
幕越し側だけで選んだ値を固定した。学習対象・注釈・元動画・研究レポートのハッシュを来歴JSONに残した。
幕なし4動画を学習には入れていない。

研究の7/9件という値は、幕越しの外側take評価6/7と幕なし1/2の合計。
同梱モデルが学習済みの12動画に対して7/9件の未知データ性能を持つ、という意味ではない。

### 実施した検証

外側評価ごとのモデルを同じ分割で書き出し、16動画の保存骨格をアプリ用の逐次推論へ入力した。
全フレームのaction・phase・OPENED表示・後処理状態が研究結果と一致した。
同梱モデルでも、学習に使っていない幕なし4動画の予測一致を確認した。

さらに元動画をMediaPipeから処理し、骨格とアプリの `current`・通知・ラムネ状態を
保存骨格からのアプリ再生と照合した。

| 元動画 | フレーム数 | ラムネ通知 |
| --- | ---: | --- |
| both_without_the_screen | 389 | 277フレームで1回 |
| contrast_without_the_screen | 458 | 0回 |

アプリが実際に使う動画PTS（`FrameClock`）でも同じ2本を再生し、通知は同じ277フレームで1回／0回だった。
研究の等間隔時刻による骨格一致検証と、実動画の時刻による実行確認を別々に記録した。

テストは全体実行で367件通過し、サンドボックスのソケット制限で失敗したTCPテスト1件は制限外で通過。
その後追加した扇ぎ・打ち水の互換性テスト2件も通過し、計370件を確認した。
ruff、変更した実行時モジュールのpyright、構文検査が通過。wheelをビルドし、展開先から
学習モデルを読み込めることも確認した。

これは既存動画での実装一致の検証で、追加の独立データによる精度評価ではない。
カメラ実機・新しい連続試行・人物交代、学習に正例がない扇ぎと打ち水の実動画評価は未実施。

数値記録：[等間隔時刻での実装一致JSON](0924-runtime-validation.json)、
[アプリの動画時刻での検証JSON](0924-runtime-source-clock.json)。

## 再現

gesture_detectionディレクトリで、モデルを使うだけなら通常の `uv sync` とアプリ起動でよい。
研究用のデータサブモジュールと保存骨格がある場合は、次のコマンドで再出力・検証できる。

```bash
MPLCONFIGDIR=/tmp/suzukaze-mpl OPENBLAS_NUM_THREADS=1 \
  uv run python -m scripts.export_ramune_model
MPLCONFIGDIR=/tmp/suzukaze-mpl OPENBLAS_NUM_THREADS=1 \
  uv run python -m scripts.validate_learned_ramune \
  --videos both_without_the_screen contrast_without_the_screen
MPLCONFIGDIR=/tmp/suzukaze-mpl OPENBLAS_NUM_THREADS=1 \
  uv run python -m scripts.validate_learned_ramune --app-clock \
  --videos both_without_the_screen contrast_without_the_screen \
  --output docs/0924-runtime-source-clock.json
uv run pytest --no-cov -q
uv run python -m compileall -q src scripts tests
```

保存骨格 `shared/results/0924-cache/runtime-source.npz` はローカルの研究キャッシュで、Gitに含めない。
新しいチェックアウトで必要な場合は、動画・注釈を用意して別パスへ作成する。

```bash
RAMUNE_DETECTOR=rules MPLCONFIGDIR=/tmp/suzukaze-mpl OPENBLAS_NUM_THREADS=1 \
  uv run python -m scripts.export_ramune_model --prepare-snapshot \
  --snapshot shared/results/0924-cache/runtime-source-new.npz \
  --output /tmp/ramune-rebuilt.npz
```

再抽出時はMediaPipe・モデル・実行環境の一致が必要。新しく作った骨格が研究結果を再現するかは
`validate_learned_ramune --snapshot ...` で確認する。元の研究キャッシュは上書きしない。

## 成果別コミット

| コミット | 内容 |
| --- | --- |
| `3406e8c` | 注釈評価・因果的な学習基準 |
| `159b48d` | 開栓表示保持・再出現抑制 |
| `ea3956c` | 再許可・2回目・連続動画の追試 |
| `ccb7f41` | 準備待ちの原因切り分け |
| `57099a0` | 相対位置・速度特徴の比較 |
| `2d3f2b1` | 分類スコア診断と研究索引 |

上記6件を現ブランチに確定した後、アプリ組み込みを別コミットにまとめる。
