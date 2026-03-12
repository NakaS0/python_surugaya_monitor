# プロジェクト構成ガイド

このファイルは「どのフォルダに何が入っていて、何のために存在しているのか」を一目で把握するための説明書です。

## ルートフォルダ

- `.env`
  - チェック対象名や URL を入れる設定ファイルです。
  - `ACTIVE_TARGET_SET` で 4 パターンの対象セットを切り替えられます。
  - Git には通常含めません。

- `.env.example`
  - `.env` の見本です。
  - 何のキーを入れるべきかを確認するときに使います。

- `.gitignore`
  - Git に含めないファイルやフォルダを指定します。
  - Cookie、DB、仮想環境などを除外しています。

- `manage.py`
  - Django の入口です。
  - サーバー起動、マイグレーション、チェック実行などをここから行います。

- `requirements.txt`
  - Python 依存ライブラリの一覧です。

- `scraper.py`
  - 駿河屋のページを取得し、新着差分を判定するコア処理です。

- `fixed_targets.py`
  - `.env` を読み込んでチェック対象一覧を作る設定モジュールです。
  - 4 パターンの対象セット切替もここで処理します。

- `surugaya_cookies.json`
  - 駿河屋アクセス用の Cookie を保存するファイルです。

- `run_monitor.bat`
  - Windows でダブルクリック実行しやすい起動バッチです。
  - Django サーバー起動後にブラウザを開きます。

- `README.md`
  - 利用方法の概要説明です。

- `FILE_FUNCTIONS_JA.md`
  - 主なファイルの役割を簡潔に説明したメモです。

- `PROJECT_STRUCTURE_JA.md`
  - このファイルです。フォルダ単位の構成を説明します。

## `config/`

Django 全体の設定を持つフォルダです。

- `settings.py`
  - Django 設定本体。DB、タイムゾーン、テンプレート、アプリ一覧を管理します。

- `urls.py`
  - URL とビューの対応付けを行います。

- `wsgi.py`
  - WSGI サーバー用の起動設定です。

- `asgi.py`
  - ASGI サーバー用の起動設定です。

- `__init__.py`
  - `config` を Python パッケージとして扱うためのファイルです。

## `monitor/`

このプロジェクトの中心になる Django アプリです。

- `models.py`
  - DB テーブルに対応するモデル定義です。

- `views.py`
  - ダッシュボード画面や API の表示処理です。

- `urls.py`
  - `monitor` アプリ専用の URL 定義です。

- `services.py`
  - ビューや管理コマンドから使う業務処理です。
  - スクレイパー実行結果を DB に保存する役割を持ちます。

- `admin.py`
  - Django 管理画面の表示設定です。

- `apps.py`
  - Django にこのアプリを登録するための設定です。

- `tests.py`
  - 将来テストを追加する場所です。

- `__init__.py`
  - `monitor` を Python パッケージとして扱うためのファイルです。

## `monitor/templates/monitor/`

- `dashboard.html`
  - ブラウザで見えるメインのダッシュボード画面です。

## `monitor/management/commands/`

Django の独自管理コマンドを置くフォルダです。

- `run_monitor.py`
  - チェックを実行して DB に保存します。

- `sync_monitor_targets.py`
  - `.env` の対象を DB に同期します。

- `import_cookies.py`
  - Cookie 文字列やファイルから `surugaya_cookies.json` を作ります。

## `monitor/migrations/`

Django の DB 変更履歴を保存するフォルダです。

- `0001_initial.py`
  - 最初のテーブル作成内容です。

- `__init__.py`
  - マイグレーションパッケージであることを示します。

## `static/`

- `.gitkeep`
  - 静的ファイル用フォルダを Git に残すための空ファイルです。

## 実行時に増えるフォルダ

- `venv/`
  - Python 仮想環境です。

- `target_data/`
  - 旧スクレイパー側の保存データです。
  - 現在は Django DB を正規ルートにしていますが、互換用途で残る場合があります。

- `__pycache__/`
  - Python が自動生成するキャッシュです。

- `.chrome-debug-profile/`, `.chrome-debug-session/`
  - Cookie 周りの試行時に生成される一時フォルダです。
