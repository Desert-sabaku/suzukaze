# 礼の動画評価

注釈済みの2カメラ動画を、実際の`PoseAnalyzer`（VIDEO・multicamプロファイル・
rules判定）と`MultiCameraFusion`で再生し、礼の判定を比較します。
`gesture_detection/`から実行します。

```bash
uv sync --group dev
uv run python -m scripts.evaluate_bow ../shared/annotations \
  --output shared/results/bow-baseline-20261004
```

対象は`take_001`〜`take_004`の`camera_1/timeline.json`と
`camera_2/timeline.json`です。動画は各注釈の`source.path`から読み込み、SHA-256を
照合します。両カメラは同じFPS・総フレーム数である必要があります。

## 評価条件

- `take_002`〜`004`は調整用、別の被写体の`take_001`は評価用です。
- 各動画の先頭から全フレームを処理し、時刻は`frame_id / fps`とします。
- 被写体選択は`multicam.first.select_subject`と
  `multicam.second.select_subject`に従います。設定ファイルがない場合は
  camera_1が有効、camera_2が無効です。
- 動画に含まれる同一画像の繰り返しも処理します。ライブ実行でのフレーム落ち、
  推論遅延、到着順は再現しません。録画のカメラ取得時刻は使いません。
- 統合後の正解Actionは2カメラの`BOW`区間の和集合です。Phase境界の注釈が
  食い違うフレームでは`HOLD`、`BENDING`、`RETURNING`の順に優先します。
- 注釈のない区間は、この評価では`NONE`として扱います。

## 保存する結果

- `summary.json`: 設定、モデルのハッシュ、動画情報、撮影別・カメラ別・統合後の集計。
- `take_00N/camera_1.csv`・`camera_2.csv`: フレーム単位の正解・出力、追跡状態、
  上体角度、頭の向き、保持時間、判定対象点の不備、骨格33点。
- `take_00N/fused.csv`: 統合後のフレーム単位の正解・出力。
- `take_00N/camera_1-hold.jpg`・`camera_2-hold.jpg`: `HOLD`の中央フレームに
  推定骨格を重ねた確認用画像。点0が鼻、11・12が肩、23・24が腰です。

現在の認識は保持姿勢を対象とするため、所作全体のカバー率を成功率として
解釈しないでください。各Phaseの検出フレーム数、特に`HOLD`中の検出を確認します。
`first_detection_from_hold_seconds`は、Action内の最初の検出が`HOLD`開始から
何秒後かを示し、保持前の検出なら負になります。未検出の場合は`null`です。
`detected_action`は所作内で1フレーム以上の検出があったかを示します。
未検出時のprecisionも`null`であり、100%ではありません。

生の`bow_state`と配信される`current.gesture`を分けて集計することで、
判定不成立と他所作による抑制を区別します。Phaseごとの診断件数は
独立した条件であり、重複するため足し合わせないでください。

## 被写体選択を切り分ける

調整用だけを用いて、被写体選択を無効化した診断ができます。

```bash
uv run python -m scripts.evaluate_bow ../shared/annotations \
  --output shared/results/bow-no-selection-20261004 \
  --takes take_002 take_003 take_004 --disable-subject-selection
```

これは原因の切り分け用です。両カメラの入力処理が変わるため、標準設定の評価と
区別して保存します。設定や判定を調整した後は、別の出力先を指定し、調整用の結果を
確認してから評価用`take_001`を評価します。
