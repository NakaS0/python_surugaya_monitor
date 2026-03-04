# 関数説明書

このファイルは、
「このアプリの各ファイルが何をしているか」を説明したものです。

対象ファイル:

- `app.py`
- `scraper.py`
- `dashboard.py`
- `fixed_targets.py`

---

## まず全体の流れ

1. `app.py` がコマンド（`check` や `watch`）を受け取る
2. `scraper.py` が駿河屋ページを読み取り、新着を判定する
3. `dashboard.py` が結果をブラウザ画面に表示する
4. `fixed_targets.py` が「どのURLを監視するか」を `.env` から読み込む

---

## app.py（入口のファイル）

### `parse_args()`
- ターミナルで入力したコマンドを読み取る関数です。
- 例: `python app.py check` の `check` を判定します。
- 使えるコマンドやオプション（`--max-pages` など）をここで定義しています。

### `main()`
- このアプリの「司令塔」です。
- `parse_args()` の結果を見て、どの処理を動かすか決めます。
- たとえば:
  - `init-session`: ログイン用ブラウザを開く
  - `check`: 監視を1回実行
  - `watch`: 監視実行後にUIを起動
  - `show-last`: 最新結果を表示
  - `serve-ui`: UIだけ起動

---

## scraper.py（データ取得・判定の中心）

### ID・保存先まわり

#### `_safe_target_id(target_id)`
- 文字列を「ファイル名に使っても安全な形」に変換します。
- 例: 記号を `_` に置き換える。

#### `_target_dir(target_id)`
- 監視対象ごとの保存フォルダ（`target_data/...`）を作ります。

#### `_target_files(target_id)`
- その監視対象で使うファイルパスをまとめて返します。
- 例: `saved_items.json`, `latest_check.json`, `check_results.jsonl`

#### `latest_report_file(target_id)`
- 「最新結果ファイル」の場所だけ知りたいときに使います。

### 前回データの読み書き

#### `_load_snapshot(target_id)`
- 前回の取得結果（商品ID一覧）を読み込みます。
- 「前回と比べて増えたか」を調べるために必要です。

#### `_save_snapshot(ids, details, target_id)`
- 今回取得した結果を保存します。
- 次回実行時の比較元になります。

### ログインCookie関連

#### `_build_chrome_driver(headless=True)`
- SeleniumでChromeを起動する設定を作ります。

#### `_save_cookies(driver)`
- ログイン後のCookieをファイルに保存します。

#### `bootstrap_login_session(open_url=...)`
- 手動ログイン用の処理です。
- ブラウザを開いてログインしてもらい、Cookieを保存します。

#### `_load_cookie_header()`
- 保存済みCookieをHTTPリクエストで使える形に変換します。

### HTML取得・文字列処理

#### `_fetch_html(url, cookie_header, user_agent, referer="")`
- 指定URLからHTMLを取得します。
- CookieやUser-Agentを付けてアクセスします。

#### `_strip_tags(text)`
- HTMLタグを取り除いて、見た目の文字だけにします。

#### `_extract_value(tag, attr)`
- HTMLタグの属性値（`src`, `alt` など）を取り出します。

#### `_extract_price(html_fragment, text)`
- 価格文字列を見つけます。
- まず価格用要素（`price-buy`）を優先し、ダメなら `¥` や `円` で探します。

#### `_extract_items_from_html(html, base_url)`
- 商品ID・商品名・URL・画像URL・価格をまとめて抽出します。
- 同じ商品IDが複数回出ても、より良い情報で1つにまとめます。

#### `_build_page_url(base_url, page)`
- ページ番号を付けたURLを作ります。
- 例: 2ページ目、3ページ目のURL生成。

### 監視実行本体

#### `_get_all_items_http(base_url, max_pages=None)`
- ページを順番に巡回して商品を集める関数です。
- 404や商品が見つからない状態で終了します。

#### `get_all_items(base_url=..., max_pages=None)`
- 上の関数を呼ぶラッパーです。
- エラーが起きた場合は空データを返して落ちにくくしています。

#### `_write_report(report, target_id)`
- 今回の監視結果を
  - 最新ファイル
  - 履歴ファイル（1行ずつ追記）
  に保存します。

#### `load_latest_report(target_id)`
- 最新結果を読み込みます。
- ファイルがない場合は空の初期データを返します。

#### `load_history(target_id, limit=30)`
- 履歴ファイルを読み込み、最新から指定件数を返します。

#### `check_new_items(max_pages=None, base_url=..., target_id=...)`
- 監視の一番重要な関数です。
- 流れ:
  1. 前回データを読む
  2. 今回データを取得する
  3. 前回に無かったIDを「新着」と判定
  4. 結果を保存して返す

---

## dashboard.py（ブラウザ画面）

### `HTML_PAGE`
- 画面のHTML/CSS/JavaScriptを1つの文字列で持っています。
- 表示内容:
  - 監視対象ごとのカード
  - 新着件数
  - 新着商品の詳細
  - 直近履歴

### JavaScript側の主な関数（`HTML_PAGE` 内）

#### `api(url, options)`
- バックエンドAPIへアクセスする共通関数です。

#### `pick(targetId)`
- どの監視対象を画面で選ぶか切り替えます。

#### `renderTargetCards()`
- 監視対象カード（取得件数・新着件数・履歴）を描画します。

#### `renderDetailRows()`
- 選択中ターゲットの新着詳細一覧を描画します。

#### `loadTargetsAndResults()`
- APIから最新データを取り直して画面更新します。

#### `runAll()`
- 「全URL監視実行」ボタンの処理です。
- 監視実行後、画面を更新します。

#### `boot()`
- 画面起動時に最初に呼ばれる初期化処理です。

### Python側のクラス

#### `DashboardHandler`
- HTTPリクエストを受け取って、
  - HTMLページ
  - API JSON
  を返すクラスです。

主なメソッド:

- `do_GET()`:
  - `/` → 画面HTML
  - `/api/targets` → 監視対象一覧
  - `/api/latest` → 最新結果
  - `/api/history` → 履歴
- `do_POST()`:
  - `/api/run-check-all` → 全監視実行
- `_send_html()` / `_send_json()`:
  - レスポンス送信の共通処理

#### `serve_dashboard(host, port)`
- ダッシュボード用のローカルサーバーを起動します。

---

## fixed_targets.py（監視対象設定）

#### `_read_dotenv(path=".env")`
- `.env` ファイルを読み取り、設定値を辞書にします。

#### `_env(key, default="")`
- 設定値を取得します。
- 優先順位は「環境変数 → `.env` → default」です。

#### `_build_targets()`
- `TARGET_1` ～ `TARGET_4` を読み取り、実際に使う監視対象一覧を作ります。
- URLが空の対象は自動で除外します。
- 1件も有効なURLがない場合はエラーにします。

#### `FIXED_TARGETS`
- `_build_targets()` の結果（最終的な監視対象リスト）です。
- 他ファイルはこのリストを使って監視を回します。

---

## 補足（初心者向け）

- `def 関数名(...):` は「処理のまとまりを作る」書き方です。
- `return` は「結果を呼び出し元へ返す」意味です。
- `dict` は「キーと値のセット」（例: `{ "name": "イラストカード" }`）です。
- `list` は「値の並び」（例: `[1, 2, 3]`）です。

この説明書と実コードを並べて読むと、流れを追いやすくなります。

---

## 図解っぽい処理フロー

### 1. アプリ全体の流れ

```text
[ユーザーがコマンド実行]
          |
          v
      app.py (main)
          |
          +--> init-session ----> scraper.py: ログイン用ブラウザ起動 + Cookie保存
          |
          +--> check / watch ---> scraper.py: 商品取得 + 新着判定 + 保存
          |                              |
          |                              v
          |                        target_data に保存
          |
          +--> serve-ui / watch --> dashboard.py: 画面表示サーバー起動
                                         |
                                         v
                                   ブラウザで確認
```

### 2. 監視（`check_new_items`）の中身

```text
1) 前回データを読む (_load_snapshot)
          |
          v
2) 今回のページを取得 (get_all_items)
          |
          v
3) IDを比較して「新着ID」を作る
   new_ids = current_ids - old_ids
          |
          v
4) 新着詳細(new_items)を作る
          |
          v
5) スナップショット保存 (_save_snapshot)
   レポート保存 (_write_report)
          |
          v
6) 結果を返す（画面表示・履歴表示に使う）
```

### 3. UI表示の流れ（`dashboard.py`）

```text
ブラウザで http://127.0.0.1:8080 を開く
          |
          v
DashboardHandler.do_GET("/")
          |
          v
HTML_PAGE を返す
          |
          v
JavaScript boot() 実行
          |
          v
loadTargetsAndResults()
   |- /api/targets で監視対象取得
   |- /api/latest   で最新結果取得
   |- /api/history  で履歴取得
          |
          v
renderTargetCards() / renderDetailRows() で画面描画
```

### 4. 「全URL監視実行」ボタンの流れ

```text
[ボタンクリック]
      |
      v
runAll() (JavaScript)
      |
      v
POST /api/run-check-all
      |
      v
DashboardHandler.do_POST()
      |
      v
FIXED_TARGETS をループして check_new_items() 実行
      |
      v
保存完了後、ブラウザ側で再読み込みして最新表示
```

### 5. どこに何が保存されるか

```text
target_data/<target_id>/
   |- saved_items.json      : 次回比較用のスナップショット
   |- latest_check.json     : 最新1回分の結果
   |- check_results.jsonl   : 履歴（1行1実行）

surugaya_cookies.json       : ログインCookie
```
