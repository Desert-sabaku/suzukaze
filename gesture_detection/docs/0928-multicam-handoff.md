# 0928 2カメラ検証の引き継ぎ

## 今回mainへ渡すもの

**2カメラ方式の検証成果を、再現用コード・テスト・集計結果・判断記録として引き継ぐ。**
最終候補は `fusion_asymmetric/peak_anchor_fresh_setup`。
アプリへ組み込む前段の実験実装であり、評価スクリプトから実行する。

ラムネ・夕涼みの追加改善は、実演条件を踏まえて一旦保留する。
このデータへさらに判定を合わせ込むことより、現時点の成果と制約を共有する段階とする。

## 実演条件：phase説明UIなし

ユーザーによれば、**ラムネと夕涼みは「今どのphaseか」を示す説明UIなしで実演した。**
想定している説明UIありの運用よりも難しい条件である。
構えを取る・待つ・押し込む・静止するといったタイミングを、
認識器の内部状態に合わせて実演できる前提の素材ではない。

したがって、今回のラムネ2/3・夕涼み1/3などは、**UIなしの録画条件での診断結果**として扱う。
想定運用での最終精度や、説明UIを付けたときの改善量を示す値ではない。
説明UIの効果自体は比較測定していない。

そのほかの条件：

- camera1：左側のInsta360 Link 2C。
- camera2：右側のLogicool HD Webcam C615。
- Windows 11、`Desert-sabaku/multicam-recorder`で撮影。
- 配置・画角・元映像・注釈を固定して検証。追加撮影は行っていない。
- camera2は30fpsとして保存されているが実時間あたりの保存枚数は約10枚。
  評価時はフレーム数とセッション時間から実時間を近似し、元動画・注釈は変更していない。

## 引き継ぐ評価基準

| 所作 | 評価方針 |
| --- | --- |
| 打ち水・ラムネ | 1回のactionに対し1イベント。同じaction内の追加発火・表示再出現を問題として数える |
| 扇ぎ・夕涼み | 再検出を許容する。反応の有無に加えて表示率・他所作への誤反応を確認する |
| phase時刻 | 注釈を厳密なフレーム正解とせず、原則1秒以内のずれを許容。実装ではOPENED区間を前後1秒広げ、親action内へ制限する |

途中のレポートには、当時の厳密なphase採点や全所作の再出現を問題視した記録がある。
現行基準と最終候補の採否は、[所作別評価レポート](0928-multicam-events.md)を参照する。

## 最終候補と分かったこと

1. camera1は既存の人物選択、camera2は全画面入力を使用する。
2. ラムネは、準備中に上の手を持ち上げたら押し込みの基準位置を追従させる。
3. 打ち水は、身体に対する相対高さに加え、画像上でも手首が上昇・下降した証拠を要求する。
4. 打ち水・ラムネの発火後は、どちらかの視点で解除を観測する。
5. 解除より後に始まった新しい準備からのイベントだけを再許可し、古い動作の遅れた通知を除外する。

| 最終候補の指標 | 結果 |
| --- | ---: |
| 扇ぎ：反応した試行 | 3/3 |
| 打ち水：1イベント・表示1区間 | 3/3 |
| ラムネ：許容時刻内の1イベント・表示1区間 | 2/3 |
| 夕涼み：反応した試行 | 1/3 |
| 打ち水の未対応イベント | 前段の全画面統合22件 → 6件 |
| ラムネの未対応イベント | 0件 |
| 正解action内の打ち水・ラムネの重複／再出現 | 0件 |

検出できた打ち水3試行・ラムネ2試行の各クリップを2回連結し、
検出器をリセットせずに再生した確認では、両回を各1イベントで受け付けた。
これは再許可の回帰確認であり、別途撮影した連続実演の評価ではない。

2台目には、見逃しの補完に加え、片視点では見えない**解除姿勢の観測を補う**役割がある。
一方、打ち水の未対応イベント6件、ラムネ1試行の見逃し、夕涼みの認識不足は残る。
各所作3試行という小規模な同一素材上の探索結果であり、汎化精度として扱わない。

## コードと成果物

| ファイル | 役割 |
| --- | --- |
| `shared/scripts/evaluate_multicam.py` | 26動画の監査・実時間近似補正・3条件の骨格推定と一次評価 |
| `shared/scripts/analyze_multicam.py` | 姿勢取得率、判定状態、注釈時計差の集計 |
| `shared/scripts/evaluate_multicam_followup.py` | カメラ別領域、保存骨格の再生整合性、判定診断 |
| `shared/scripts/analyze_multicam_followup.py` | 表示持続時間と静止判定の平滑化比較 |
| `shared/scripts/multicam_temporal_metrics.py` | phase許容幅、イベント対応、表示区間の計測 |
| `shared/scripts/evaluate_multicam_temporal.py` | ラムネ準備追従と短期保持の比較 |
| `shared/scripts/evaluate_multicam_fusion.py` | 時刻順の2カメラ統合・固定優先順位と短期重複除去 |
| `shared/scripts/multicam_event_policy.py` | 所作別採点、打ち水の追加証拠、解除・新準備による再許可 |
| `shared/scripts/evaluate_multicam_events.py` | 最終候補を含む比較、2回連結したクリップの回帰確認 |

レポートのJSONは集計・追跡用。`shared/results/0928-multicam*/` のフレーム別出力、
骨格キャッシュ、比較画像は下記コマンドで再生成する。
画像の見方は各段階のレポートに記載している。

## データと再現順序

素材と注釈は`shared`データセットの次のリビジョンを使用する。

```text
suzukaze-dataset: a34e1212dd6adc55f8d2ddd8c17f79fb6baee65c
videos/0928/<take>/camera_01.mp4, camera_02.mp4, session.json
annotations/<take>/camera_01/timeline.json, camera_02/timeline.json
```

リポジトリのルートで`git submodule update --init --recursive`を実行する。
以降は `gesture_detection/` 内で、次の順番に実行する。
各段階が前段のキャッシュ・集計結果を使用するため、順番を保つ。

```bash
uv sync --group dev
uv run python -m shared.scripts.evaluate_multicam
uv run python -m shared.scripts.analyze_multicam
uv run python -m shared.scripts.evaluate_multicam_followup
uv run python -m shared.scripts.analyze_multicam_followup
uv run python -m shared.scripts.evaluate_multicam_temporal
uv run python -m shared.scripts.evaluate_multicam_fusion
uv run python -m shared.scripts.evaluate_multicam_events
```

前段で作った動画・注釈・実行コードのハッシュと再生結果を照合する。
初期評価は `.env` を含むプロジェクト設定の影響を受けるので、
記録済みの`0928-multicam-diagnostics.json`の`configuration`も確認する。
再現順序の最後に生成される`0928-multicam-events-results.json`の
`fusion_summary["fusion_asymmetric/peak_anchor_fresh_setup/reference1"]`と
`reference2`が最終候補の集計である。

## テストと引き継ぎ時のチェック

```bash
uv run ruff format --check src tests scripts main.py
uv run ruff check src tests scripts main.py
uv run pyright
uv run python -m pytest
uv run python -m compileall src scripts
```

通常のテストは録画データや実カメラを必要としない。
今回追加した30テストケースは、採点、phase許容、時間換算、準備追従、
再発火抑制、他視点での解除、正当な次の準備、所作別の再検出方針を確認する。

引き継ぎ時に全469テスト、Ruffの整形・静的検査、Pyright、構文確認が成功した。
上記7段階のデータ再現も完了し、整形後のコードに対応する結果・記録ハッシュを再生成した。
最終候補の件数と、検出済み5試行の2回目を受け付ける結果が再現された。

## 保留事項

- ラムネ・夕涼みへの追加の条件調整・学習は、説明UIなしの難しい条件だったことを踏まえ保留。
- アプリへの2カメラ経路、運用設定、実時間取得・同期の導入は次の実装作業として扱う。
- 再開時は説明UIを含む想定運用条件を揃えて評価する。今回の低い数値だけを理由に、
  同じ録画へさらに過度な条件調整を行わない。

検証の履歴：
[一次評価](0928-multicam.md) → [入力・判定の診断](0928-multicam-followup.md)
→ [phase許容と統合](0928-multicam-temporal.md) → [所作別評価・再許可](0928-multicam-events.md)。
