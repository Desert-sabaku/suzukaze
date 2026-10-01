# 評価記録

詳細な評価記録と研究用の再現資料は、[GitHub Wiki](https://github.com/Desert-sabaku/suzukaze/wiki)
へ移しました。

## 現行実装への反映

- MediaPipeは `VIDEO` モードを既定とし、通常実行はLiteモデルを使用します。
- 検出・存在・追跡confidenceは `0.50` を維持しています。
- 相対位置モデルによるラムネ判定は、`RAMUNE_DETECTOR=learned` で選択できます。
- YOLO Poseの追跡・補間・平滑化は製品判定へ統合していません。

詳細な閾値と成立条件は [ジェスチャー仕様](gestures.md)、実行経路は
[構成と設定](architecture.md) と [2カメラ認識ガイド](multicam-runtime.md) を参照してください。

## 注意

評価結果は特定の撮影素材に対する研究記録であり、認識精度の保証ではありません。
顔が写る可能性のある画像、動画、注釈、JSON、生の推論出力はshared側で管理します。
