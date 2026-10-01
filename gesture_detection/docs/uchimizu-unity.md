# 所作解析の打ち水を Unity の水パーティクルへ接続する

## 実行するコードを揃える

この機能を含むブランチ／マージ後のリビジョンの Unity プロジェクトを開いてください。
別 worktree の古いプロジェクトを開いている場合、その Editor には変更が反映されません。

clone 後は `proto/` で生成し、Unity Editor の NuGetForUnity による依存復元を完了させます。

```bash
buf generate
```

## ライブ認識から演出する

1. `unity_bridge/` で起動します。

   ```bash
   uv sync --group dev
   uv run unity-bridge --gesture
   ```

   これが認識プロセスも起動します。現在の仕様は、認識結果の `GestureSample` を
   キューでブリッジへ渡し、ブリッジが protobuf のイベント・再送・ACK を管理する構成です。
   `uv run gesture-detection` 単独では Unity に通知しません。

2. 同じ PC・同じ OS 上の Unity 6000.5.8f1 で、例えば `Assets/MyScenes/Forest.unity`
   を開いて Play します。

3. プレイヤーの `ParticleOnEnter` で `receiveGestures` が有効であることを確認します。
   既存シーンでは `particlePrefab` / `neck` / `heightOffset` が設定済みです。

4. カメラで打ち水の成立が認識されると、従来 Enter キーで生成していた `Water_split`
   がプレイヤーの首位置とシーン設定の高さ・向きで生成されます。

Enter / テンキー Enter による手動確認も同じ処理を通ります。Enter では水が出るのに
所作で出ない場合は、認識画面での打ち水成立、ブリッジの起動、Unity の受信器の
`LastError` と Endpoint を確認してください。

## 接続と ACK

`ParticleOnEnter` が有効になると、専用の永続ルート `GestureReceiver` を自動作成するか、
既存の受信器を再利用します。診断 Prefab の追加は不要です。Python プローブは Unity と
同時に接続しないでください。ブリッジの受信クライアントは1つです。

水を生成できた場合に限り `accepted` を返します。ラムネイベント、演出が無効、Prefab/首位置が
未設定の場合は `ignored` です。期限切れ・再送の重複判定は既存受信器が担当し、同じ成立で
水を繰り返し生成しません。演出の完了を待って ACK する仕様ではありません。

シーン切替で旧 `ParticleOnEnter` を解除し、新しいものを登録します。受信器は同じものを
使用するため、カメラ・ブリッジの再起動は不要です。打ち水コンポーネントがないシーンの間は
イベントを見送り、後で戻っても過去のイベントを再生しません。

自動対応する既存シーン:

- `Forest`
- `river`
- `sea`
- `Sea2`
- `☆1湖`
- `滝`

`Scene_ch`、`river(中流)` には元の `ParticleOnEnter` がありません。新しいシーンに追加する場合は、
同コンポーネントに水 Prefab とプレイヤーの首 Transform を設定します。

## 検証

Fedora 44 / Unity 6000.5.8f1 の Test Runner で確認しています。

- EditMode: 33 passed（既存6シーンのスクリプト・Prefab・首位置・高さの読み込みを含む）
- PlayMode: 12 passed（実パーティクル生成、採用 ACK、重複、失効、ラムネ見送り、
  無効な参照、手動生成、受信器再利用、シーン受信先の切替を含む）

テストはカメラ依存を避け、認識成立に相当するイベントを受信ポリシーへ渡しています。
実カメラでの認識精度と、実際の投影映像の目視確認はライブ環境で実施してください。
