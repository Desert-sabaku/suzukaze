# 0924 相対位置モデルの開栓スコア診断

2026-09-26。現ブランチで実施。相対位置モデルの保存済み分割・選択設定で再学習し、設定の再探索はしていない。特徴量、action予測、後処理、注釈、本番コードは変更していない。

## 結論

**both2幕越しの見逃しは、OPENEDが僅差で2位に落ちるケースではなかった。** 注釈138–141フレームでは3～4位で、WAIT_RELEASEだけでなくREADYにも負ける。さらに、予測の遷移はFORMINGからWAIT_RELEASEへ直接進み、READYもOPENEDも通過していない。

幕なしramuneも注釈中のOPENEDは4位。右手首の相対位置が無効で、左手首だけは使えているが、READYとのスコア差は約−0.54となる。一方、動作なし区間でもOPENEDが1位になるフレームがあり、初回準備待ちがそれを抑えていた。

したがって、**スコア閾値を一律に緩める根拠は得られなかった**。次の比較対象は、準備後のphase遷移・スコア履歴を使う開栓イベント判定とする余地がある。ただし、FORMING→WAIT_RELEASEを自動的に開栓へ置き換える仕様は今回導入しない。

今回は診断の追加であり、検出は幕越し6/7件・幕なし1/2件、再出現と単独動画の対応しない出力はいずれも0件のまま。全16動画のphase、OPENED出力、後処理状態、単独・連結評価が前回と完全一致した。

## 診断方法

- 既存の110次元の相対位置特徴を使用。前回保存したtake別の学習動画と設定を再利用し、幕なしを学習へ入れない。骨格はキャッシュ限定で読み込む。
- `fit_scores` が全phaseのridgeスコアを返し、既存の `fit_predict` は同じスコアから従来通りargmaxと骨格欠落時のNONE上書きを適用する。実験用関数の追加であり、本番APIの変更はない。
- OPENEDの順位、OPENED−READY、OPENED−WAIT_RELEASE、OPENED−他クラス最大値を記録する。同点時の順位は既存のargmaxと同じクラス順で決める。
- ridgeスコアは確率ではない。負値や1を超える値もあり、異なる外側分割のスコアを一つの分布にまとめない。以下の表も各動画の分布を別々に示す。
- 骨格未観測フレームを統計・スコア図から除外し、欠落数を別記。未学習クラスは−∞で選択対象から除外し、算出できない差や順位はNPZではNaN、JSONの統計値ではnullとする。
- 開栓注釈、直前1秒、直後1秒、RAMUNE試行全体を集計。1秒はfpsから最も近いフレーム数に丸め、前後区間に注釈自体を重複して含めない。動作なし・READY・WAIT_RELEASE・未知phaseも別々に集計する。
- 注釈外のスコア上位10フレームは診断用。許容された連続OPENEDの延長を含み得るため、それだけで誤検出とは数えない。注釈は診断の区切りにのみ使用し、推論には渡さない。

## 見逃しと成功例の比較

表の差は「OPENED−他クラス最大値」。正ならOPENEDが勝ち、負なら他phaseが勝つ。最小・中央値・最大は開栓注釈フレームだけの値であり、許容された前後延長を含む検出結果とは区別する。

| 動画・開栓前後の拡大図 | 検出 | OPENED順位の内訳 | 差：最小／中央値／最大 |
| --- | --- | --- | --- |
| [both1 幕越し](0924-opening-scores/both1_behind_the_screen-anchor1.png) | 成功 | 1位×2、2位×1、5位×2 | −0.7800 / −0.0133 / +0.0374 |
| [contrast1 幕越し](0924-opening-scores/contrast1_behind_the_screen-anchor1.png) | 成功 | 1位×1、2位×1 | −0.1389 / −0.0416 / +0.0557 |
| [ramune1 幕越し](0924-opening-scores/ramune1_behind_the_screen-anchor1.png) | 成功 | 1位×2 | +0.0170 / +0.0285 / +0.0400 |
| [both2 幕越し](0924-opening-scores/both2_behind_the_screen-anchor1.png) | **見逃し** | **3位×2、4位×2** | **−0.2932 / −0.2454 / −0.2233** |
| [ramune2 幕越し](0924-opening-scores/ramune2_behind_the_screen-anchor1.png) | 成功 | 1位×1、2位×1、3位×2 | −0.0465 / −0.0241 / +0.0012 |
| [both3 幕越し](0924-opening-scores/both3_behind_the_screen-anchor1.png) | 成功 | 1位×2 | +0.0147 / +0.0193 / +0.0239 |
| [ramune3 幕越し](0924-opening-scores/ramune3_behind_the_screen-anchor1.png) | 成功 | 1位×2、2位×2、3位×2 | −0.0345 / −0.0162 / +0.0480 |
| [both 幕なし](0924-opening-scores/both_without_the_screen-anchor1.png) | 成功 | 2位×2 | −0.1164 / −0.0976 / −0.0788 |
| [ramune 幕なし](0924-opening-scores/ramune_without_the_screen-anchor1.png) | **見逃し** | **4位×2** | **−0.5404 / −0.5388 / −0.5371** |

### both2幕越し

準備待ちは124フレームでARMEDに移行している。生phaseは115–136でFORMING、137–150でWAIT_RELEASEとなり、注釈138–141にOPENEDがない。この時点で両手首の相対位置は4フレームとも有効なので、今回の特徴量の無効化や準備ロックだけで説明できない。

同じ外側分割・同じ学習モデルで成功したramune2は、147フレームでOPENEDが他クラスに約+0.0012だけ勝つ。both2では注釈中のOPENED−READYも−0.1998～−0.0412で、WAIT_RELEASEだけを候補から外してもOPENEDは勝たない。両動画の差は、単なる同点付近の順位の入れ替わりではない。

both2のRAMUNE試行全体でもOPENEDは一度も1位・2位にならない。一方、同じ動画のaction=NONE区間ではOPENED−他クラス最大値が−0.1481まで近づく。注釈内の最大−0.2233より高い値が動作なしにもあるため、スコア差だけで救済する単純な境界をこの診断から決めることはできない。後処理を含めた閾値変更の実験は実施していない。

### ramune幕なし

96フレームでARMEDに移行済みだが、注釈142–143ではREADYを選択する。両フレームとも左手首の相対位置は有効、右手首は無効で、手首間距離も無効。OPENED−READYは−0.5404～−0.5371、OPENEDは4位で、RAMUNE試行全体でも4～5位に留まる。

この結果は観測不足と整合するが、その寄与と分類器の問題を因果的に分離したものではない。スコア調整だけで不足した右手首情報が補えるとは判断しない。

### 成功例も注釈内の毎フレームでOPENEDが勝つわけではない

both幕なしは注釈284–285の両フレームでWAIT_RELEASEが勝つが、その前の277フレームに始まる連続表示が注釈を含むため成功である。注釈内のスコアや順位だけを新しい合否基準にはしない。既存の連続区間の評価を維持する。

## 動作なし区間と準備待ちの役割

生phaseでOPENEDが1位なのに、後処理で出力しなかったフレームは次の11フレーム。すべてWAIT_SETUP中で、今回の単独動画ではLOCKED中に抑制されたOPENEDは0フレームだった。

| 動画 | 準備待ちで抑えたOPENEDフレーム | action=NONE区間のスコア差最大値 |
| --- | ---: | ---: |
| contrast 幕なし | 4 | +0.3996 |
| ramune 幕なし | 2 | +0.2044 |
| yusuzumi 幕なし | 5 | +2.2913 |

確信度のように見える大きなridgeスコア差でも、正しい開栓とは限らない。初回準備条件を外す根拠にはしない。また、単独動画でLOCKEDの抑制が0だったことを、再判定防止のロックが不要という意味には解釈しない。

2回連結の結果も前回と一致し、初回成功例の2回目は幕越し6/6・幕なし1/1。幕なしramuneの2本目冒頭に対応しない出力1区間が残る。連結は保存信号の合成であり、連続実動画での確認ではない。

## 全16動画の比較図

各図は全phaseのスコア、OPENEDとの差、OPENED順位、正解と予測phase、後処理の状態を同じ時間軸で示す。黄色は開栓注釈。

| 条件 | both | contrast | ramune | yusuzumi |
| --- | --- | --- | --- | --- |
| 幕越し take1 | [図](0924-opening-scores/both1_behind_the_screen.png) | [図](0924-opening-scores/contrast1_behind_the_screen.png) | [図](0924-opening-scores/ramune1_behind_the_screen.png) | [図](0924-opening-scores/yusuzumi1_behind_the_screen.png) |
| 幕越し take2 | [図](0924-opening-scores/both2_behind_the_screen.png) | [図](0924-opening-scores/contrast2_behind_the_screen.png) | [図](0924-opening-scores/ramune2_behind_the_screen.png) | [図](0924-opening-scores/yusuzumi2_behind_the_screen.png) |
| 幕越し take3 | [図](0924-opening-scores/both3_behind_the_screen.png) | [図](0924-opening-scores/contrast3_behind_the_screen.png) | [図](0924-opening-scores/ramune3_behind_the_screen.png) | [図](0924-opening-scores/yusuzumi3_behind_the_screen.png) |
| 幕なし | [図](0924-opening-scores/both_without_the_screen.png) | [図](0924-opening-scores/contrast_without_the_screen.png) | [図](0924-opening-scores/ramune_without_the_screen.png) | [図](0924-opening-scores/yusuzumi_without_the_screen.png) |

## 次に検証する分類方法

both2は「準備後にphaseが変化しているのに、瞬間ごとの5クラス競合ではOPENEDが低順位」という例。次の比較候補として、現在の相対位置特徴と過去のphaseスコアの変化から、準備後の開栓イベントを別に判定する方法を検討する。phase macro F1と開栓区間の検出が一致しないため、イベント指標による設定選択も比較対象になる。

これは今回の診断からの提案であり、有効性は未検証。単純な状態遷移の置換、スコア閾値の変更、追加モデルの本番統合は行っていない。新しい比較でもtake分割を維持し、既存7件の検出・再出現0件・次の試行の受付を同時に評価する必要がある。

## 再現と検証

gesture_detectionディレクトリで：

```bash
MPLCONFIGDIR=/tmp/suzukaze-mpl OPENBLAS_NUM_THREADS=1 \
  uv run python -m scripts.evaluate_opening_scores --plot
uv run pytest tests/test_evaluate_opening_scores.py tests/test_evaluate_opening_features.py \
  tests/test_evaluate_opening_setup.py tests/test_evaluate_opening_temporal.py \
  tests/test_evaluate_opening_repetition.py tests/test_evaluate_opening_rearm.py \
  tests/test_evaluate_timeline.py --no-cov -q
uv run ruff check scripts/evaluate_opening_scores.py scripts/evaluate_timeline.py \
  tests/test_evaluate_opening_scores.py
uv run python -m compileall -q src scripts tests
```

対象62テスト、変更したスクリプト・テストのruff、src・scripts・testsの構文検査が通過。スコア取得前後の判定一致、未知phaseの学習除外、評価ラベル・未来フレームへの非依存、未学習クラス、骨格未観測、同点順位、前後区間が空の場合を確認した。全16動画の保存済み予測との一致は診断スクリプトでも検証し、成果物・入力のハッシュと25図へのリンクも確認した。実カメラの検証は今回の対象外。

生データ：[スコア集計・遷移JSON](0924-opening-scores-results.json)。全phaseのスコア、観測有効性、順位・差、固定action、phase予測、OPENED出力、後処理状態は `shared/results/0924-cache/0924-opening-scores-results-predictions.npz` に保存。入力・実装・出力のハッシュをJSONに記録した。
