# IIDX SP☆12 OPTION MANAGER

GitHub Pages用の静的サイトです。

## データ仕様

- 曲一覧の母集団：`sp12.iidx.app` の有効なSP☆12譜面全件
- ノマゲ／ハード分類：atwikiの各地力表から取得
- 地力表に掲載されていない譜面：`未分類`
- 地力表で「未定」の譜面：`未分類`
- 表記差などで照合できなかった譜面：`未分類`

## 更新

GitHubの **Actions → Update SP12 data → Run workflow** を実行してください。
成功すると `data/sp12.json` と `data/update-report.json` が更新されます。

公開URL：`https://farewell2236.github.io/kirika/`
