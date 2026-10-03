# ドキュメント

対象読者ごとに入口を分けています。

## まず動かす

- [ジェスチャー仕様](gestures.md): 認識する4種類の所作と成立条件
- [カメラ入力・録画・トラブルシュート](camera.md): 録画、入力形式、カメラ障害
- [設定ファイル](configuration.md): TOML設定と旧 `.env` からの移行
- [実演者の選択](subject-selection.md): 複数人が映る場合の対象選択
- [実機での確認項目](manual-testing.md): 起動後の確認項目

## 連携・複数カメラ

- [Unity連携・OS別セットアップ・2カメラ](integration.md): 通信仕様、Windows/Linux、2カメラ

## 開発者向け

- [構成・設定・開発](architecture.md): 責任範囲、時刻・入力、品質確認
- [学習済みラムネ判定](learned-ramune.md): 任意の学習済み判定器
- [動画・関節位置の注釈](annotation.md)

## 評価記録

- [評価記録](evaluations.md): 現行実装へ反映した結論
- [詳細な評価記録](https://github.com/Desert-sabaku/suzukaze/wiki): GitHub Wikiで管理

日付付きの評価レポート、結果JSON、比較画像、動画、注釈、ランドマーク、顔が写る
可能性のある素材は、通常の利用者向け資料ではありません。検証データは
`gesture_detection/shared` サブモジュールで管理し、公開ドキュメントには必要な結論と
再現手順へのリンクだけを残します。
