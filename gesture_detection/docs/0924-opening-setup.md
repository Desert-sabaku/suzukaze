# 0924 開栓の準備待ち・見逃しの原因分析

2026-09-25。現ブランチで実施。保存済み予測を使用し、再学習・本番統合・元注釈の変更はしていない。

## 結論

**0924の残る見逃し3件は、準備待ちが原因ではない。** いずれも準備確認を終えた `ARMED` 状態で注釈時刻を迎え、phaseがその時刻までにOPENEDを出さない。準備からaction条件を外しても検出数は増えず、再準備から外すとramune3で開栓後の再出現が戻った。今回の緩和候補は採用しない。

次の分類器改善対象は、OPENEDをREADYのまま見逃す2件と、READY / WAIT_RELEASEを経て1フレーム遅れる1件。未注釈のkohara連続動画で見つかった準備不成立を、0924の見逃し原因として一般化することはできなかった。

## 比較条件と評価仕様

- 全16動画。幕越し12動画の予測はtake単位の外側評価、幕なし4動画の予測は幕越しのみで学習したモデルによる既存の保存結果を使用。新たな設定選択・再学習はしていない。
- 表示保持0.75秒、骨格が観測される非RAMUNEで解除0.6秒、準備0.3秒を固定。基準は前回の `context_fixed` で、過去の結果を見た探索条件。独立した未使用データの評価ではない。
- 初回のみ／再準備のみ／両方で、準備条件を「骨格あり、action=RAMUNE、phase=FORMINGまたはREADY」から「骨格あり、phase=FORMINGまたはREADY」に変更。解除条件は変更しない。初回とは動画内の最初の**出力イベント前**を指す。
- action未注釈はNONE。phase未知は未知のまま扱う。注釈を含む連続したOPENEDの前後への延長は許容し、1フレーム遅れて重ならない区間は見逃しとして別記する。
- 動画・注釈・予測ファイル・使用スクリプトのハッシュをJSONへ記録。基準の単独結果と全連結結果は、前回保存結果との完全一致を実行時に確認した。

## 準備条件を緩めた結果

| 準備条件 | 幕越し 検出／7 | 幕越し 再出現 | 幕越し 対応しない出力 | 幕なし 検出／2 | 幕なし 再出現／対応しない出力 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 基準：初回・再準備ともaction必須 | 5 | 0 | 1 | 1 | 0 / 0 |
| 初回だけphaseで準備 | 5 | 0 | 1 | 1 | 0 / 0 |
| 再準備だけphaseで準備 | 5 | 1 | 1 | 1 | 0 / 0 |
| 両方phaseで準備 | 5 | 1 | 1 | 1 | 0 / 0 |

再準備を緩めると、`ramune3_behind_the_screen` の基準出力168–224フレームに加え、283–305フレームに再び出力する。注釈のRAMUNE動作は129–204フレームであり、新しい試行ではない。**再準備時のaction条件はこの再出現を抑える役割を果たしていた。**

### 信号を2回連結した確認

追加欠落なし・0.5秒・2秒のすべてで、初回成功例の2回目は全条件とも幕越し5/5、幕なし1/1。再準備を緩める2条件では、幕越しの再出現は連結全体で2回となる。

対応しない出力も数えると、基準でも幕越し2区間（ramune2の1フレーム遅れが各コピーに1区間）、幕なし1区間（ramune動画の2本目冒頭）がある。初回準備を緩める条件では、さらに `contrast_without_the_screen` の2本目冒頭に1区間増え、幕なしは2区間になる。contrastでは1本目で準備済みの状態が残り、2本目冒頭の予測に反応する。

したがって「2回目が6/6で通る」だけで合格とはしない。これは保存信号の合成であり、Pose・分類器の履歴は接続をまたがず、後処理だけが連続する。特に接続点の誤出力を実際の連続撮影での誤出力率と解釈しない。

## RAMUNE全9件の原因一覧と時系列図

準備成立時間は、RAMUNE注釈開始からOPENED注釈開始の直前までに、基準の準備条件が連続成立した最長の**時刻差**。例えば30 fpsの連続10フレームは0.3秒で、10/30秒ではない。実際の状態機械は動画冒頭から動作し、注釈の境界でリセットしない。

| 動画・時系列図 | 注釈フレーム | 最長準備成立 秒 | 注釈開始時の状態 | 結果・観測 |
| --- | ---: | ---: | --- | --- |
| [both1 幕越し](0924-opening-setup/both1_behind_the_screen.png) | 307–311 | 0.492 | OPENED | 検出 |
| [both2 幕越し](0924-opening-setup/both2_behind_the_screen.png) | 138–141 | 0.741 | ARMED | 見逃し。注釈4フレームともREADY |
| [both3 幕越し](0924-opening-setup/both3_behind_the_screen.png) | 181–182 | 0.308 | OPENED | 検出。準備時間は閾値付近 |
| [both 幕なし](0924-opening-setup/both_without_the_screen.png) | 284–285 | 0.701 | OPENED | 検出 |
| [contrast1 幕越し](0924-opening-setup/contrast1_behind_the_screen.png) | 349–350 | 0.868 | OPENED | 検出 |
| [ramune1 幕越し](0924-opening-setup/ramune1_behind_the_screen.png) | 161–162 | 0.558 | OPENED | 検出。連続出力113–196は仕様上許容 |
| [ramune2 幕越し](0924-opening-setup/ramune2_behind_the_screen.png) | 145–148 | 1.027 | ARMED | READY→WAIT_RELEASE。OPENEDは149から、1フレーム遅れ |
| [ramune3 幕越し](0924-opening-setup/ramune3_behind_the_screen.png) | 180–185 | 1.280 | OPENED | 保持で検出。注釈内の生phaseはREADY |
| [ramune 幕なし](0924-opening-setup/ramune_without_the_screen.png) | 142–143 | 1.808 | ARMED | 見逃し。注釈2フレームともREADY |

各図にはaction・phaseの正解と予測、両手首のvisibility、準備条件の成立区間、基準の状態遷移、4条件のOPENED出力を同じ時間軸で描いた。黄色はOPENED注釈。UNKNOWNはphase未注釈を表す。

9件とも準備区間で「全骨格が未観測」のフレームは0。actionとphaseの不整合は一部にあるが、全件で0.3秒以上の同時成立を確保している。一方、幕なしramuneは準備60フレームと開栓注釈2フレームのすべてで、両手首が同時にvisibility>0.5になっていない。現在の特徴量は低visibilityの関節座標を0にするため、開栓を区別する入力が弱い可能性がある。**手首の入力品質の問題と、分類器自体の問題の寄与は今回だけでは分離できない。**

## 正解への置き換えによる切り分け

以下は推論精度ではなく、入力の一部を正解に置き換えた診断。骨格と後処理は固定し、未知phaseは予測を残す。元の注釈は変更しない。

| 置き換え | 幕越し 検出／7 | 幕なし 検出／2 | 解釈 |
| --- | ---: | ---: | --- |
| なし | 5 | 1 | 比較基準 |
| actionのみ正解 | 5 | 1 | 見逃し3件は改善しない |
| 既知phaseのみ正解 | 6 | 2 | 見逃し3件を回復する一方、ramune1が見逃しへ変化 |
| actionと既知phaseを正解 | 6 | 2 | phaseのみと同じ |

ramune1では未知phaseの118フレームに予測OPENEDが残る。周辺を注釈のREADYへ置き換えると、基準で113–196まで続いていた表示が118–139へ短くなり、140フレームでLOCKEDとなる。161–162の正解OPENEDはロック中で抑制される。

これは**部分的な正解置き換えが到達精度の上限ではない**ことを示す。未知をNONEへ埋めたり、許容された長いOPENEDを誤検出扱いしたりしてはいけない。次の学習実験でも、短い注釈区間だけに出力を押し込めることを目的にしない。

## 次に改善する箇所

1. 準備条件と解除条件は基準を維持し、READY / OPENED / WAIT_RELEASEの識別と開栓タイミングを分類器側の検討対象にする。both2、ramune2、幕なしramuneを失敗例として追跡する。
2. 幕なしramuneについては手首の可視性・特徴量の欠落を併記し、識別方式の変更だけで解決したと判断しない。
3. 成功した長いOPENEDを維持できるか、再出現を増やさないかを同時に測る。今回の3候補は検出数の増加がなく、次段階の候補条件を満たさない。
4. 連続実動画での再準備・別撮影条件の検証は引き続き未達。本番には組み込まない。

## 再現と検証

gesture_detectionディレクトリで、既存の依存環境を使用する。

```bash
MPLCONFIGDIR=/tmp/suzukaze-mpl OPENBLAS_NUM_THREADS=1 \
  uv run python -m scripts.evaluate_opening_setup --plot
uv run pytest tests/test_evaluate_opening_setup.py \
  tests/test_evaluate_opening_temporal.py tests/test_evaluate_opening_repetition.py \
  tests/test_evaluate_opening_rearm.py tests/test_evaluate_timeline.py --no-cov -q
uv run ruff check scripts/evaluate_opening_setup.py \
  scripts/evaluate_opening_temporal.py tests/test_evaluate_opening_setup.py
uv run python -m compileall -q src scripts tests
```

対象44テスト、変更したスクリプト・テストのruff、src・scripts・testsの構文検査が通過。未知phaseの維持、初回と再準備の分離、未来・注釈への非依存、骨格欠落を解除とみなさないこと、1フレーム遅れ、正解部分置換によるロックの副作用を確認した。基準結果の回帰確認は16動画の実験にも組み込み、保存済み結果と一致した。アプリのカメラ動作は変更しておらず、実カメラ検証は今回の対象外。

生データ：[比較結果・原因一覧JSON](0924-opening-setup-results.json)。全条件のフレーム出力と状態列は `shared/results/0924-cache/0924-opening-setup-results-predictions.npz` に保存する。JSONにはその相対パス、状態IDの対応、入力・実装のハッシュを含む。
