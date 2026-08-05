# IIDX SP☆12 OPTION MANAGER

GitHub Pages用です。`sp12.iidx.app` がGitHub Actionsの通常HTTP通信を403で拒否するため、更新処理は次の順で取得を試します。

1. requests
2. curl_cffiによるChrome偽装
3. Playwright Chromiumでページを実際に開き、内部JSONを取得

曲一覧はSP☆12全件を母集団にし、地力表に掲載されていない譜面・未定・照合不能は「未分類」にまとめます。

## 初回更新

Actions → Update SP12 data → Run workflow

Chromiumのインストールがあるため、初回は数分かかることがあります。
