# 関数説明書（日本語）

このファイルは、主要ソースコードにある関数・処理の役割を日本語で整理したものです。
対象ファイル:

- `app.py`
- `scraper.py`
- `dashboard.py`
- `fixed_targets.py`

## app.py

### `parse_args()`
- CLI引数を定義して解析します。
- サブコマンド `init-session`, `check`, `watch`, `show-last`, `serve-ui` を受け付けます。
- 各サブコマンドのオプション（`--max-pages`, `--target`, `--ui-host` など）を設定します。

### `main()`
- `parse_args()` の結果に応じて実行ルートを分岐します。
- `init-session`: ログイン用ブラウザ起動とCookie保存を実行。
- `check`: `FIXED_TARGETS` 全件に対して1回監視を実行。
- `watch`: 全件監視後、ダッシュボード起動（必要に応じてブラウザ自動オープン）。
- `show-last`: 指定ターゲットの最新結果JSONを表示。
- `serve-ui`: ダッシュボードサーバーのみ起動。

## scraper.py

### ID/ファイル管理

#### `_safe_target_id(target_id)`
- ターゲットIDをファイルパス安全な文字に変換します。

#### `_target_dir(target_id)`
- `target_data/<target_id>` ディレクトリを作成して返します。

#### `_target_files(target_id)`
- ターゲットごとの保存ファイルパス（`saved/latest/log`）を返します。

#### `latest_report_file(target_id)`
- 指定ターゲットの最新結果ファイルパスを返します。

### スナップショット管理

#### `_load_snapshot(target_id)`
- 前回保存した商品ID集合と詳細情報を読み込みます。
- 新形式（`ids` + `details`）と旧形式（ID->詳細）両方に対応します。

#### `_save_snapshot(ids, details, target_id)`
- スナップショットを保存します。

### セッション/Cookie

#### `_build_chrome_driver(headless=True)`
- Selenium Chromeドライバを生成します。

#### `_save_cookies(driver)`
- ブラウザCookieを `surugaya_cookies.json` に保存します。

#### `bootstrap_login_session(open_url=DEFAULT_BASE_URL)`
- 手動ログイン用ブラウザを開き、設定完了後にCookieを保存します。

#### `_load_cookie_header()`
- 保存済みCookieを `Cookie` ヘッダ形式に変換して返します。

### HTML取得/解析

#### `_fetch_html(url, cookie_header, user_agent, referer="")`
- HTTPでページを取得し、文字コードを考慮してHTML文字列を返します。

#### `_strip_tags(text)`
- script/style/tagを除去してプレーンテキスト化します。

#### `_extract_value(tag, attr)`
- HTMLタグ文字列から属性値（`src`, `alt` など）を取得します。

#### `_extract_price(html_fragment, text)`
- 価格を抽出します。
- まず `text-price-detail price-buy` の要素を優先し、なければ `¥` / `円` パターンで補完します。

#### `_extract_items_from_html(html, base_url)`
- 商品リンクを解析して `id/name/url/image_url/price` を抽出します。
- 同一IDの重複情報は、より適切な値を優先して統合します。

#### `_build_page_url(base_url, page)`
- `page` クエリを付け替えてページURLを構築します。

### 監視実行

#### `_get_all_items_http(base_url, max_pages=None)`
- ページを順次取得し、商品一覧を統合します。
- 404や商品リンクなしを終端条件として扱います。

#### `get_all_items(base_url=..., max_pages=None)`
- 実取得処理のラッパーです。例外時は空データを返します。

#### `_write_report(report, target_id)`
- 最新結果（`latest`）と履歴（`log`）へ保存します。
- `default` ターゲットはルート互換ファイルも更新します。

#### `load_latest_report(target_id)`
- 最新結果JSONを読み込みます。なければ初期値を返します。

#### `load_history(target_id, limit=30)`
- 実行履歴JSONLを読み込み、最新から `limit` 件返します。

#### `check_new_items(max_pages=None, base_url=..., target_id=...)`
- 監視の本体処理です。
- 前回スナップショットと今回取得結果を比較し、増えたIDのみを `new_items` として判定します。
- 判定結果を保存し、レポートを返します。

## dashboard.py

### `HTML_PAGE`（埋め込みHTML/JS）
- ダッシュボード画面のUIテンプレートです。
- 監視対象カード、新着詳細テーブル、履歴表示を含みます。
- JavaScript側では主に以下の関数が動作します。

#### `api(url, options)`
- バックエンドAPIへのHTTPアクセス共通関数です。

#### `pick(targetId)`
- 選択中ターゲットを切り替え、カードと詳細表示を再描画します。

#### `renderTargetCards()`
- 監視対象ごとのカード（取得件数、新着件数、直近3回履歴）を描画します。

#### `renderDetailRows()`
- 選択中ターゲットの新着商品の詳細一覧を描画します。

#### `loadTargetsAndResults()`
- `/api/targets`, `/api/latest`, `/api/history` を取得し、画面を更新します。

#### `runAll()`
- `/api/run-check-all` を実行し、監視後に画面を再読込します。

#### `boot()`
- 初期化処理。初回読込と定期更新タイマーを開始します。

### `DashboardHandler(BaseHTTPRequestHandler)`

#### `do_GET()`
- `GET /` でUI配信
- `GET /api/targets` で監視対象一覧返却
- `GET /api/latest` で最新結果返却
- `GET /api/history` で履歴返却

#### `do_POST()`
- `POST /api/run-check-all` で全ターゲット監視を実行します。

#### `log_message(...)`
- HTTPアクセスログ出力を抑制します。

#### `_send_html(html)`
- HTMLレスポンス送信ヘルパーです。

#### `_send_json(payload, status=200)`
- JSONレスポンス送信ヘルパーです。

### `serve_dashboard(host="127.0.0.1", port=8080)`
- ローカルHTTPサーバーを起動し、ダッシュボードを提供します。

## fixed_targets.py

#### `_read_dotenv(path=".env")`
- `.env` ファイルを読み込み、`KEY=VALUE` を辞書に変換します。

#### `_env(key, default)`
- 優先順位 `環境変数 -> .env -> default` で設定値を返します。

#### `_required_env(key)`
- 必須設定を取得します。
- 値が空の場合は `RuntimeError` を発生させます。

#### `FIXED_TARGETS`
- 監視対象の固定配列です。
- 各ターゲットの `name` と `url` は `.env` の必須値として読み込みます。
