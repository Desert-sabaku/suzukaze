# 2026-09-22 Unityプロジェクト取り込み(#27対応)

## 経緯

PR #27(`unity-team`ブランチ、shigeshupapiさん作成)は91万行・2486ファイルの差分になっており、
リポジトリオーナーから「たぶん何かがおかしい、流石にデカすぎる」とコメントが付いていた。

調査の結果、`Library/`や`Temp/`等のビルド生成物の混入ではなく、以下が原因と判明:

- `Assets/Samples`(Shader Graph/SRP Coreのパッケージサンプル、748ファイル)
- 複数のアセットストア購入素材(`Beach - resort`, `Fantasy Skybox FREE`, `R3DWorks`,
  `FinottiGames`, `Silver_Cats`, `Tree_Packs`, `WaterWorks`等)
- Shader Graph/VFX Graphのノードグラフファイル(`.shadergraph`/`.vfx`/`.shadersubgraph`)が
  YAMLシリアライズされ、ノード数に比例して数万行規模になる

## 対応

1. `main`から`feat/add-unity-project`ブランチを新規作成し、`pr-27`の巨大な履歴を持ち込まずに
   1コミットで取り込み直した
2. モノレポ規約(`gesture_detection/`と同様)に合わせ、Unityプロジェクトを
   リポジトリ直下ではなく`suzukaze/`サブディレクトリに配置
3. `.gitignore`は[github/gitignoreの公式Unity.gitignore](https://github.com/github/gitignore/blob/main/Unity.gitignore)を採用
4. `.gitattributes`は[gitattributes/gitattributesの公式Unity.gitattributes](https://github.com/gitattributes/gitattributes/blob/master/Unity.gitattributes)
   をベースに採用。ただし`suzukaze/`がリポジトリのトップレベルではない(モノレポで
   `gesture_detection/`と同階層)ため`[attr]`マクロが使えず、全展開して記述
5. Git LFSを導入し、バイナリ資産(png/fbx/wav/pdf/otf/ttf等)と、確認の結果バイナリと
   判明した`.asset`(Terrain地形データ、LightingDataベイクデータ、数十MB規模)をLFS管理に。
   `.unity`/`.prefab`/`.mat`等diffが有効なYAMLはLFS化せず、`merge=unityyamlmerge`で
   Unity公式マージツールを使うよう設定
6. `file`コマンドと[Google Magika](https://github.com/google/magika)(`uvx magika`で実行)で
   全ファイルの実バイナリ判定を行い、gitattributesの設定ミス(バイナリなのにLFS対象外/
   逆に小さいテキストなのにLFS対象、`ProjectSettings/*.asset`がLFSに巻き込まれるバグ等)
   がないか照合した

## 結果

91万行 → 約30万行まで削減。ゴミの除去ではなく、正直なサイズ(実データ+diff優先方針)。

## 未対応・保留事項

- Unityエディタのバージョン(`6000.5.8f1`、非LTS)は提出用途なので据え置き。LTS移行は後回し
- アセットストア購入素材が実際にシーンで使われているかの精査は未実施
