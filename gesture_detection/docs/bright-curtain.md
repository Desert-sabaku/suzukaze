# 明るい環境・白い服での幕越し評価（2026-09-23）

## 条件と結論

`shared/videos/bright-behind-the-screen` の12本（4動作×3本）、対応する
`shared/annotations/bright-behind-the-screen` の96フレーム・385点を評価した。
モデルはMediaPipe Pose Lite 0.10.35、confidence 0.5、前処理なし。
打ち水の `uchimziu` / `utchimizu` の表記も評価対象に含めた。

明るさ・服装を変更した今回の撮影では、扇ぎと打ち水の検出が改善した。
ただし両方の条件とテイクが変わっているため、明るさ単独の効果とは断定できない。
ラムネ・夕涼みは現行判定では各0/3であり、4動作すべてが解決したわけではない。

## 静止画と時系列を分けた位置評価

| 条件 | 人物ありで姿勢取得 | 人物なしで姿勢検出 | PCK@0.2 |
| --- | ---: | ---: | ---: |
| 前回・暗い環境 IMAGE（既存報告） | 11.3% | 5.9% | 0.0% |
| 今回 IMAGE | 34/67 = 50.7% | 0/29 = 0.0% | 68/385 = 17.7% |
| 今回 VIDEO・全フレーム追跡 | 57/67 = 85.1% | 1/29 = 3.4% | 283/385 = 73.5% |
| 今回 VIDEO・表示平滑化後 | 同上 | 同上 | 278/385 = 72.2% |

PCKは手動肩幅（使用不可なら腰幅）の20%以内を正解とし、姿勢未取得も失敗に含める。
VIDEOは各動画の先頭から全4,002フレームを処理し、注釈フレーム番号で照合した。
推論時刻はフレーム番号/動画平均FPS。IMAGEは各注釈画像を独立に推論する。
両モードの差が大きく、静止画のみの結果でカメラ追跡性能を判断してはいけない。

## 動作区間

ファイル名の開始秒〜終了秒を正解区間として、動画のソース時刻を保ち30 FPSの固定時間格子で評価。
従来のサンプリングは採用したフレームの時刻から次の時刻を計算しており、
30 FPS付近の動画で余計な間引きが発生したため修正した。
過去の動作区間集計とは処理頻度が異なることに注意する。

| 動作 | 区間内で検出した動画 | 区間内の姿勢取得率 | 区間内の当該動作フレーム率 | 区間外の何らかの動作出力率 |
| --- | ---: | ---: | ---: | ---: |
| 扇ぎ | 3/3 | 100% | 67.3% | 24.8% |
| ラムネ | 0/3 | 60.0% | 0% | 6.4% |
| 夕涼み | 0/3 | 100% | 0% | 13.1% |
| 打ち水 | 3/3 | 100% | 26.7% | 16.1% |

区間外出力には準備・終了動作や判定保持も含む。動画単位の3/3だけでは誤発火の少なさを保証しない。

ラムネ1本目はREADYへ進んだが、押下量最大0.082肩幅で現行の0.25に届かなかった。
2、3本目は正解区間中に必要関節が揃わずIDLEのまま。平滑化だけで開栓完了を復元することはできない。
夕涼みは姿勢を取得しても現行の静止条件を満たしていない。

## 表示の揺れへの変更

VIDEOモードの骨格表示に、時定数60 msの指数平滑化を追加した。
推論結果の時刻差で係数を計算し、カメラの処理頻度が変わっても同じ時間尺度で動く。
未検出・低visibility・0.25秒超の間隔・時刻逆行で履歴を切り、再取得時に古い位置を引きずらない。
visibilityは平滑化せず、そのフレームの値で描画を決める。

動作判定・Unity向け判定・評価用の `landmarks` は元座標を使い、
ローカル骨格表示だけ `display_landmarks` を使用する。
`POSE_DISPLAY_SMOOTHING=false` で従来表示へ戻せる。IMAGEモードは平滑化しない。

同じ可視関節ペアで比較すると、連続フレーム間移動量のp95は測定可能な11本で18〜52%減少。
残り1本は連続した姿勢が得られず比較不能。移動量には実際の所作も含み、純粋なノイズ量ではない。
PCKは全体で1.3ポイント低下した。これは表示の安定性と追従遅れのトレードオフであり、
誤った骨格の補正や所作精度の改善を示すものではない。

比較動画: `shared/results/bright-ramune-smoothing.mp4`（左: 元座標、右: 表示平滑化）。
録画を再処理し比較フレームを確認済み。実機カメラでの操作確認は未実施。

## 次の撮影

今回のデータだけで改善傾向と表示平滑化は検証できた。
幕なし相当かの比較、およびラムネの動作と推定器の問題を切り分けるには、
同じ白い服・照明・カメラ位置で幕なしも各動作3本、特にラムネの準備〜押下〜解除を撮影してほしい。
明るさ単独を比較するなら服装も固定する。
静止中の揺れを測るため、入場後に2〜3秒静止する区間もあるとよい。

## 再現

```bash
uv sync
uv run python -m scripts.evaluate_landmark_annotations \
  --annotations shared/annotations/bright-behind-the-screen \
  --output docs/bright-landmarks.json
POSE_SELECT_SUBJECT=false uv run python -m scripts.evaluate_action_intervals \
  --environment bright --sample-fps 30 --output docs/bright-actions.json
POSE_SELECT_SUBJECT=false uv run python -m scripts.evaluate_bright_tracking \
  --annotations shared/annotations/bright-behind-the-screen \
  --videos shared/videos/bright-behind-the-screen \
  --output docs/bright-tracking.json \
  --preview shared/results/bright-ramune-smoothing.mp4
```

生データ: [静止画](bright-landmarks.json)、[動作区間](bright-actions.json)、[時系列](bright-tracking.json)。

## 幕なし追加撮影の結果

同条件に近づけた各1本の追加診断は[幕なし対照](bright-without-controls.md)を参照。
背景人物への追跡固定が見つかったため、姿勢取得率だけでは実演者の入力品質を判断できない。
