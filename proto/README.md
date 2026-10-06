# 通信スキーマ

`gesture/v1/gesture.proto`はジェスチャー認識とUnity間、`comms/v1`は
マイコンとの通信に使用します。生成コードはコミットせず、変更後はこのディレクトリで
`buf generate`を実行します。

## 動作の正確性

`State.action_accuracy`と`Event.action_accuracy`は、**所作の基準に対して、
実際に行われた動作がどれだけ一致しているか**を表す省略可能な`double`です。

| 値 | 意味 |
| --- | --- |
| フィールドなし | 未評価、または評価に必要な観測が不足している |
| `0.0` | 評価済みで、所作の基準への一致度が最低 |
| `0.0`〜`1.0`の間 | 部分的に基準を満たしている |
| `1.0` | 評価対象の所作の基準を完全に満たしている |

- 値は有限の数値かつ`0.0 <= action_accuracy <= 1.0`とします。NaN、無限大、
  範囲外の値を送信しません。これはプロトコル上の制約であり、protobufの数値型自体は
  範囲を検証しません。
- ジェスチャー分類の確信度・確率、映像認識の評価指標であるaccuracy、
  配送の成功率とは別の値です。認識されたことだけを理由に`1.0`を設定しません。
- 角度・軌跡・保持時間などの採点基準と集計方法は所作ごとに定義します。
  異なる所作の点数を同じ基準の測定値とみなすことはできません。
- `State`では、その観測時点の代表所作についての評価です。所作が`NONE`、
  追跡がない場合、または評価できない場合は省略します。
- `Event`では、その成立イベントを生んだ動作についての評価です。同じイベントの
  再送では、当初の値と有無を保持します。
- 省略と明示的な`0.0`は区別します。

既存のフィールド番号を変更せず、Stateに10、Eventに7を追加しています。
追加フィールドを送らない既存のメッセージは未評価として扱えます。
採点項目・計算式は
[`gesture_detection/docs/gestures.md`](../gesture_detection/docs/gestures.md#所作の正確性action_accuracy)
を参照してください。認識結果からIPC・WebSocket配信を通してUnityへ引き継ぎます。

## Unityでの取得

`GestureEvents.CurrentState.ActionAccuracy` は `double?` です。未評価・期限切れは
`null`、評価済みのゼロ点は `0.0` です。点数だけが変化した場合も `StateChanged` を通知します。

```csharp
gestures.StateChanged += state => {
    if (state.ActionAccuracy is double score)
        UnityEngine.Debug.Log($"{state.Gesture}: {score:F2}");
};
gestures.Occurred += (sessionId, occurrence) => {
    if (occurrence.HasActionAccuracy)
        UnityEngine.Debug.Log($"{occurrence.Gesture}: {occurrence.ActionAccuracy:F2}");
    return false; // 点数の参照だけでは所作を採用したACKにはしない
};
```

Pythonの配信辞書では、未評価の `action_accuracy` キーは省略します。
Python・Unity双方で非有限値・範囲外の点数、および有効な追跡所作を伴わないStateの点数を拒否します。
