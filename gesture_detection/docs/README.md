# ドキュメント

対象読者ごとに入口を分けています。

## まず動かす

- [ジェスチャー仕様](gestures.md): 認識する4種類の所作と成立条件
- [カメラ録画](camera-recording.md): 検証用のカメラ録画
- [カメラ取得のトラブルシュート](camera-capture-troubleshooting.md): 映像が黒い・緑になる場合
- [実演者の選択](subject-selection.md): 複数人が映る場合の対象選択
- [実機での確認項目](manual-testing.md): 起動後の確認項目

## 連携・複数カメラ

- [Unityへのジェスチャー通知](unity-delivery.md): `unity_bridge` と Unity の接続仕様
- [Windows protobuf 運用ガイド](windows-protobuf.md)
- [Fedora/Linux protobuf 運用ガイド](fedora-protobuf.md)
- [2カメラ認識ガイド](multicam-runtime.md)

## 開発者向け

- [構成と設定](architecture.md): モジュールの責任範囲と時刻・入力の扱い
- [開発ガイド](development.md): formatter、lint、型検査、テスト
- [学習済みラムネ判定](learned-ramune.md): 任意の学習済み判定器
- [動画の注釈](video-annotation.md)
- [関節位置の手動ラベル付け](landmark-annotation.md)

## 評価記録

- [過去の評価](evaluations.md): 現行実装に反映した結論の索引
- [0928 2カメラ検証の引き継ぎ](0928-multicam-handoff.md): 採用事項と制約
- [幕越し評価のプロトコル](curtain-validation-protocol.md)

日付付きの評価レポート、結果JSON、比較画像、動画、注釈、ランドマーク、顔が写る
可能性のある素材は、通常の利用者向け資料ではありません。検証データは
`gesture_detection/shared` サブモジュールで管理し、公開ドキュメントには必要な結論と
再現手順へのリンクだけを残します。

評価記録を追加するときは、個人を識別できる画像をこのディレクトリへ追加しないでください。
説明用画像が必要な場合も、匿名化済みの素材または個人を識別できない図を使用します。