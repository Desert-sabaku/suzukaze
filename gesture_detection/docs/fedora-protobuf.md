# Fedora / Linux 上の Unity への protobuf 配送

## 対応範囲と確認結果

認識アプリ・unity_bridge・Unity を**同じ64-bit Linux PCのネイティブ環境**で
起動します。Windows 側とは同じプロトコルを使用し、OS に応じた時計を自動選択します。
Fedora は `clock_gettime(CLOCK_MONOTONIC)`、Windows は QPC です。
Unity の起動時刻を差し引かず、Python `time.monotonic()` と直接比較します。
別PC、WindowsとWSLの混在、異なる時計名前空間のコンテナは対象外です。

Fedora 44 x86_64 / Unity **6000.5.8f1** で確認済み（認識側から TCP で中継していた旧構成での結果。
C# の portable / 結合テストは `tools/` の廃止に伴い削除済み）:

| 検証 | 結果 |
|---|---|
| C# portable テスト | 30 passed |
| C# 8 / .NET Standard 2.1 | ビルド成功 |
| Python ↔ 本番 C# 受信コア | 3 passed、Linux時計の同一原点も検証 |
| Unity Editor EditMode | 27 passed |
| Unity Editor PlayMode | 4 passed（実 Python からの受信・Update・採用・ACK・再送停止を含む） |

Editor テストは batchmode/nographics で実行しています。実カメラのジェスチャーと
演出の目視確認、Linux standalone の描画・Mono/IL2CPP ビルドは別途確認してください。

## 通常の起動

Unity Hub、上記 Editor、Linuxネイティブ版 uv、buf が必要です。
リポジトリ全体を取得し、生成物と依存を用意します。

```bash
(cd proto && buf generate)
uv sync --locked --project unity_bridge
```

リポジトリルートから起動します。認識画面も開きます（動画評価では送信しません）。

```bash
uv run --directory unity_bridge --locked unity-bridge --gesture
```

Unity Hub から `suzukaze/` を開き、確認用シーンのルートへ
`Assets/Bridge/Gesture/Prefabs/GestureReceiverDiagnostic.prefab` を配置して再生します。
Endpoint は `ws://127.0.0.1:5000`、時計の指定は不要です。
`Google.Protobuf` は NuGetForUnity が復元します。

診断 Sink は既定で `ignored` を返します。Inspector の `acceptEvents` を有効にすると
診断目的の採用を記録します。実演出は `IGestureSink` を実装し、演出を採用した場合だけ
`TryAcceptEvent` から `true` を返してください。受信器はシーン遷移後も存続します。
Player Settings の Run In Background は有効にします。Editor Pause は解除します。

ブリッジは1受信器限定です。Unity を停止して Python プローブで切り分ける場合:

```bash
uv run --directory unity_bridge --locked unity-gesture-probe
```

2カメラで認識する場合は [2カメラ認識ガイド](multicam-runtime.md) の設定を
`gesture_detection/.env` に書きます。Linux ではカメラ1台につき `/dev/video*` が2つ作られることが多く、
`MULTICAM_CAMERA_INDICES=0,2` のようになる場合があります。

## Unity Editor テストの batchmode 実行

リポジトリルートで以下を実行してください。

```bash
export UNITY_EDITOR="$HOME/Unity/Hub/Editor/6000.5.8f1/Editor/Unity"
"$UNITY_EDITOR" -batchmode -nographics -projectPath "$PWD/suzukaze" \
  -runTests -testPlatform EditMode -testFilter Suzukaze.Gesture \
  -testResults /tmp/suzukaze-editmode.xml -logFile /tmp/suzukaze-editmode.log
"$UNITY_EDITOR" -batchmode -nographics -projectPath "$PWD/suzukaze" \
  -runTests -testPlatform PlayMode -testFilter Suzukaze.Gesture \
  -testResults /tmp/suzukaze-playmode.xml -logFile /tmp/suzukaze-playmode.log
```

テスト対象プロジェクトを別の Editor で開いている場合は閉じるか、別 worktree を使います。
初回のアセットインポートには時間がかかります。成功判定は終了コードだけでなく、
結果 XML の `result="Passed"`、`failed="0"` を確認してください。
`NativeClockTests` は実際の `LinuxMonotonicClock` を使います。
Python ↔ Unity の実通信は `unity-gesture-probe` の代わりに Unity を接続して手動で確認します。

詳細なイベントの期限・重複排除・ACK仕様は [配送仕様](unity-delivery.md)、
Sink API は [Unity 受信器 README](../../suzukaze/Assets/Bridge/Gesture/README.md) を参照してください。
