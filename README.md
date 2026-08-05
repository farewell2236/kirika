# IIDX SP☆12 OPTION MANAGER

GitHub Pages用の静的サイトです。☆11は取得しません。

## 分類の取得方法

`tier` 数値から独自に分類名を推測しません。
GitHub Actionsが元のatwiki難易度表を読み、ページに表示されている
`地力A`、`個人差B+` などのセクション見出しをそのまま `data/sp12.json` に保存します。
同名のANOTHER／LEGGENDARIAを混同しないよう、楽曲Wiki URLで照合します。

## 初回公開

1. このフォルダの中身をリポジトリ直下へ配置してPushします。
2. GitHubの `Actions` から `Update SP12 data` を開き、`Run workflow` を実行します。
3. 緑のチェックが付き、`data/sp12.json` が更新されたらPagesを再読み込みします。
4. `Settings → Pages → Deploy from a branch → main / root` を選択します。

公開URL: `https://farewell2236.github.io/kirika/`

Actionsは毎日自動実行されます。取得や照合に異常がある場合は既存JSONを上書きせず、Actionをエラー終了させます。
