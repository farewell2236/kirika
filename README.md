# IIDX SP☆12 OPTION MANAGER

公開URL: https://farewell2236.github.io/naide/

## この版の変更点

- 既存の `songs.json` は使用しません。
- 楽曲データは `data/sp12.json` から読み込みます。
- そのため、以前の `songs.json` が残っていても競合・誤読込しません。
- GitHub Actionsには通信タイムアウトがあります。
- 更新失敗時も既存の `data/sp12.json` は消しません。

## 導入

このフォルダの中身を `farewell2236/naide` のルートへコピーし、GitHub Desktopでコミット・プッシュしてください。
古い `songs.json` は削除しても残しても動作に影響しません。

GitHub Pagesは `Settings → Pages → Deploy from a branch → main → /(root)` に設定します。

## 手動更新

`Actions → Update SP12 data → Run workflow` を実行します。
