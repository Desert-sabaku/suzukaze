# suzukaze - 涼を出力するシステム

<img width="3300" height="1628" alt="image" src="https://github.com/user-attachments/assets/1627e86c-d667-4e9f-ba96-0c5c3e08f928" />


カメラで所作（扇ぎ・打ち水・夕涼み・礼・ラムネ開栓）を認識し、Unityの映像とファン・スピーカーで
体験を演出するプロジェクトのモノレポです。

## 構成

```text
Unity (suzukaze/) ──WebSocket(protobuf)── unity_bridge ─┬─ 子プロセス + multiprocessing.Queue ─ gesture_detection ─ カメラ
                                                        └─ ライブラリ呼び出し（予定）─ mcu ──USBシリアル(protobuf)── firmware (Pico) ─ ファン
```

| ディレクトリ | 内容 | 言語 |
| --- | --- | --- |
| [`gesture_detection/`](gesture_detection/README.md) | カメラ映像から所作を認識する | Python 3.12+ |
| [`unity_bridge/`](unity_bridge/README.md) | 認識アプリを起動し、Unityへジェスチャーを届けるWebSocketサーバー | Python 3.14+ |
| [`mcu/`](mcu/README.md) | ファームウェアと通信するシリアルクライアント（ライブラリ） | Python 3.12+ |
| [`firmware/`](firmware/README.md) | Raspberry Pi Pico のファンコン | TinyGo |
| `proto/` | protobufスキーマと buf の生成テンプレート（`buf.gen.yaml`） | protobuf |
| `suzukaze/` | Unityプロジェクト（6000.5.8f1）。`Assets/Bridge/` が `unity_bridge` との通信部分 | C# |

## セットアップ

必要なもの：[uv](https://docs.astral.sh/uv/)、[buf](https://buf.build/docs/cli/installation/)、
Unity 6000.5.8f1（Unityを使う場合）、TinyGo（ファームウェアを書き込む場合）。

1. protobufのコードを生成する。生成物はコミットしていないため、clone後とスキーマ変更後に必要です。

   ```bash
   cd proto
   buf generate
   ```

   Unityで生成物がない場合は、Consoleに同じコマンドを案内するエラーが出ます。

2. Pythonの各プロジェクトで依存関係を入れる。

> [!important]
> プロジェクトルートで実行してください！

   ```bash
   uv sync
   ```

3. Unityでは `suzukaze/` を開きます。`Google.Protobuf` はNuGetForUnityが
   `Assets/packages.config` から自動で復元します。

## 動かす

```bash
cd unity_bridge
uv run unity-bridge --gesture   # 認識アプリも起動し、ws://127.0.0.1:5000 で待ち受ける
uv run unity-gesture-probe      # Unityの代わりに受信を確認する（別ターミナル）
uv run unity-bridge --debug-gui # 認識の代わりにブラウザ（http://127.0.0.1:5080/）から所作を送る
```

> [!note]
> もしくは，`invoke`を使うことができます。仮想環境を活性化（zshなら `source .venv/bin/activate`など）をすれば，以下のように非常に短く実行できます。

プロジェクトルートで `invoke --list` を実行すると利用可能なタスクを確認できます。protobuf の生成が必要な場合は、先に
`invoke proto` を実行してください。例えば、Unity Bridge の起動とテストは次のとおりです。

```bash
invoke unity
invoke unity-tests
```

2カメラで認識する設定は [2カメラ認識ガイド](gesture_detection/docs/multicam-runtime.md)、
メッセージ仕様は [Unityへのジェスチャー通知](gesture_detection/docs/unity-delivery.md) を参照してください。
開発の約束事は [AGENTS.md](AGENTS.md) にまとめています。
