# ファイル構成メモ

このプロジェクトは Django ベースで動きます。主な役割は以下です。

## Django の入口

- `manage.py`
  - Django 管理コマンドの入口です。
  - `runserver`, `migrate`, `run_monitor`, `sync_monitor_targets`, `import_cookies` をここから実行します。

## Django 設定

- `config/settings.py`
  - Django の設定です。
  - DB、タイムゾーン、インストール済みアプリ、テンプレート設定を持ちます。

- `config/urls.py`
  - URL ルーティングです。
  - `/admin/` と `monitor.urls` を接続しています。

## チェックアプリ

- `monitor/models.py`
  - `MonitorTarget`: チェック対象
  - `CheckRun`: チェック実行結果
  - `NewItem`: 新着商品

- `monitor/views.py`
  - ダッシュボード画面と JSON API を返します。

- `monitor/templates/monitor/dashboard.html`
  - Django ダッシュボードの HTML テンプレートです。

- `monitor/services.py`
  - `.env` から対象を同期し、スクレイパーを実行して DB に保存します。

- `monitor/management/commands/run_monitor.py`
  - チェックを実行して結果を DB に保存する Django 管理コマンドです。

- `monitor/management/commands/sync_monitor_targets.py`
  - `.env` のチェック対象を DB に同期する Django 管理コマンドです。

- `monitor/management/commands/import_cookies.py`
  - Cookie ヘッダー文字列やファイルから `surugaya_cookies.json` を作る Django 管理コマンドです。

## スクレイパー

- `scraper.py`
  - 駿河屋の検索結果を HTTP で巡回します。
  - Cookie を読み込み、商品一覧を取得し、新着差分を判定します。

- `fixed_targets.py`
  - `.env` を読んでチェック対象一覧を作ります。
  - `ACTIVE_TARGET_SET=1..4` に応じて、使う対象セットを切り替えます。

## 実行に使うファイル

- `.env`
  - チェック対象名と検索 URL を定義します。
  - 4セット分の対象を持たせて切り替えられます。

- `surugaya_cookies.json`
  - ログイン済み Cookie を保存します。

- `run_monitor.bat`
  - Django 開発サーバーを `127.0.0.1:8080` で起動します。
