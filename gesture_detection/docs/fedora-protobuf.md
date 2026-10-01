# Fedora / Linux 上の Unity への protobuf 配送

## 対応範囲と確認結果

認識アプリ・unity_bridge・Unity を**同じ64-bit Linux PCのネイティブ環境**で
起動します。Windows 側とは同じプロトコルを使用し、OS に応じた時計を自動選択します。
Fedora は `clock_gettime(CLOCK_MONOTONIC)`、Windows は QPC です。
Unity の起動時刻を差し引かず、Python `time.monotonic()` と直接比較します。
別PC、WindowsとWSLの混在、異なる時計名前空間のコンテナは対象外です。

Fedora 44 x86_64 / Unity **6000.5.8f1** で確認済み:

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

Unity Hub、上記 Editor、Linuxネイティブ版 uv、Git LFS が必要です。
リポジトリ全体を取得し、各プロジェクトの依存を用意します。

```bash
git lfs pull
uv sync --locked --project gesture_detection
uv sync --locked --project unity_bridge
uv run --project unity_bridge python tools/restore_unity_protobuf.py
```

リポジトリルートから別々のターミナルで起動します。

```bash
# ターミナル1：ライブカメラの認識。動画評価では配送サーバーを起動しない
GESTURE_DELIVERY_ENABLED=true GESTURE_DELIVERY_FORMAT=protobuf \
  uv run --directory gesture_detection --locked gesture-detection
```

```bash
# ターミナル2：ブリッジ
uv run --directory unity_bridge --locked unity-bridge \
  --gesture-port 5001 --gesture-format protobuf
```

Unity Hub から `suzukaze/` を開き、確認用シーンのルートへ
`Assets/GestureDelivery/Prefabs/GestureReceiverDiagnostic.prefab` を配置して再生します。
Endpoint は `ws://127.0.0.1:5000`、時計の指定は不要です。

診断 Sink は既定で `ignored` を返します。Inspector の `acceptEvents` を有効にすると
診断目的の採用を記録します。実演出は `IGestureSink` を実装し、演出を採用した場合だけ
`TryAcceptEvent` から `true` を返してください。受信器はシーン遷移後も存続します。
Player Settings の Run In Background は有効にします。Editor Pause は解除します。

ブリッジは1受信器限定です。Unity を停止して Python プローブで切り分ける場合:

```bash
uv run --directory unity_bridge --locked unity-gesture-probe --format protobuf
```

## Unity 上での実通信テストの再現

認識モデルを使わず、実際の Outbox/TCP/ブリッジと Unity の受信コンポーネントを
接続します。リポジトリルートで以下を実行してください。

```bash
uv sync --locked --project tools/gesture-integration
export GESTURE_E2E_PYTHON="$PWD/tools/gesture-integration/.venv/bin/python"
export GESTURE_E2E_FIXTURE="$PWD/tools/gesture-integration/fixture.py"
uv pip install --python "$GESTURE_E2E_PYTHON" --no-deps \
  -e gesture_protocol -e gesture_detection -e unity_bridge
"$GESTURE_E2E_PYTHON" tools/restore_unity_protobuf.py

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
`GESTURE_E2E_*` 未指定の場合、Python を使う PlayMode テスト1件はスキップされます。
GUI の Test Runner から実行する場合も、上記環境変数を設定したターミナルから
Editor を起動すると実通信テストを有効にできます。

CI は Ubuntu/Windows で受信コアと実通信を検証します。Fedora の Editor 検証は
この手順で行い、Editor ライセンスを必要としない portable テストとは区別します。

詳細なイベントの期限・重複排除・ACK仕様は [配送仕様](unity-delivery.md)、
Sink API は [Unity 受信器 README](../../suzukaze/Assets/GestureDelivery/README.md) を参照してください。
