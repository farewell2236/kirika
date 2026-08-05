# Kirika — IIDX SP☆12 OPTION MANAGER

`sp12.iidx.app` の公開ページをChromiumで開き、ページが実際に読み込む楽曲データから以下を直接保存します。

- 全SP☆12譜面
- ノマゲ分類：`n_clear_string`
- ハード分類：`hard_string`

atwikiとの照合やtier数値の独自変換は行いません。元サイト側で空欄・未定になっているものだけ「未分類」にまとめます。

## 反映手順

1. ZIPの中身を `farewell2236/kirika` のルートへ上書き
2. GitHub Desktopで Commit → Push
3. GitHubの Actions → **Update SP12 data** → **Run workflow**
4. 成功後、公開ページを `Ctrl + F5` で再読み込み

公開URL：`https://farewell2236.github.io/kirika/`

## 更新結果の確認

- `data/sp12.json`：表示用データ
- `data/update-report.json`：取得件数、分類済み件数、未分類一覧
