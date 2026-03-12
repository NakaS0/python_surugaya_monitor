# 駿河屋新着チェッカー

駿河屋の検索結果をチェックし、新着を Django 上で保存・表示するプロジェクトです。

## 開発背景
- 中古ECサイト「駿河屋」において、特定商品の入荷状況を確認する際の利便性向上を目的として開発しました。
- 従来、目的の商品に辿り着くには「商品名での検索」「状態の選択」「入荷カテゴリの指定」といった多段階のフィルタリング操作が必要であり、日常的なチェックにおいて大きな手間となっていました。
- また、サイト上の「新入荷」枠には数ヶ月前のデータが残る仕様のため、真に「最近入荷した商品」のみを判別することが困難であるという課題がありました。

## 解決策
- 本ツールでは、事前に設定した条件（URL）を元に自動でスクレイピングを行い、最新の入荷情報のみを抽出・集約します。
- さらに、実行ごとに前回の取得データとの差分比較を行う機能を実装し、新規に出品された商品のみを抽出して表示することで、情報の鮮度と視認性を大幅に向上させました。

## 今後追加予定
- セールがある場合は、画面上部でセール対象品目の一覧を表示
- 値段比較のため、気になった商品をGoogleで直接検索できるようにする

## 構成

- Django プロジェクト: `config/`
- Django アプリ: `monitor/`
- スクレイパー本体: `scraper.py`
- チェック対象設定: `.env`
- 対象セット切替: `ACTIVE_TARGET_SET=1..4`
- Cookie 保存先: `surugaya_cookies.json`
- SQLite DB: `db.sqlite3`

## セットアップ

```powershell
python -m venv venv
venv\Scripts\python.exe -m pip install -r requirements.txt
venv\Scripts\python.exe manage.py migrate
```

`.env` はプロジェクトルートに配置します。

## 対象セットの切替

`.env` では、4パターン分のチェック対象セットを持てます。  
使用するセットは `ACTIVE_TARGET_SET` で切り替えます。

例:

```powershell
ACTIVE_TARGET_SET=2
```

各セットは次のキーで定義します。

```powershell
SET_1_TARGET_1_NAME=チェック対象1
SET_1_TARGET_1_URL=
...
SET_4_TARGET_4_NAME=チェック対象4
SET_4_TARGET_4_URL=
```

## Cookie の取り込み

Chrome の DevTools で取得した `Cookie:` ヘッダーを、そのまま保存できます。

```powershell
venv\Scripts\python.exe manage.py import_cookies --header "name=value; other=value"
```

ファイルから取り込む場合:

```powershell
venv\Scripts\python.exe manage.py import_cookies --file path\to\cookies.txt
```

`--file` は次のどちらでも扱えます。

- `name=value; other=value` 形式のテキスト
- `[{ "name": "...", "value": "..." }]` 形式の JSON

## Django コマンド

`.env` のチェック対象を DB に同期:

```powershell
venv\Scripts\python.exe manage.py sync_monitor_targets
```

チェック実行して DB に保存:

```powershell
venv\Scripts\python.exe manage.py run_monitor
```

ページ数制限付き:

```powershell
venv\Scripts\python.exe manage.py run_monitor --max-pages 10
```

開発サーバー起動:

```powershell
venv\Scripts\python.exe manage.py runserver 127.0.0.1:8080
```

## 画面

- ダッシュボード: `http://127.0.0.1:8080/`
- Django Admin: `http://127.0.0.1:8080/admin/`
- JSON API: `http://127.0.0.1:8080/api/latest-runs/`

## 補足

- 旧 `app.py` と `dashboard.py` は削除し、Django に統一しました。
- `run_monitor.bat` は Django の `runserver` 起動用です。
- チェック対象または対象セットを変更したら `sync_monitor_targets` を再実行してください。
