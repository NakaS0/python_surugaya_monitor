# 駿河屋 新着監視ツール

このアプリは、指定した駿河屋の検索URLを監視し、前回実行時点から増えた商品（新着）を検出して表示します。

- 監視対象URL・表示名は `.env` から読み込みます
- 成人向け表示を含めるため、ログイン済みCookieを利用します
- 結果はローカルファイルに保存し、ダッシュボードで確認できます

## 必要環境

1. Python 3.10 以上
2. Google Chrome
3. 依存ライブラリ

```bash
pip install selenium
```

## 設定（.env）

1. `.env.example` を `.env` にコピー
2. 必要に応じて監視対象名・URLを編集

使用する主なキー:

- `TARGET_1_NAME`, `TARGET_1_URL`
- `TARGET_2_NAME`, `TARGET_2_URL`
- `TARGET_3_NAME`, `TARGET_3_URL`
- `TARGET_4_NAME`, `TARGET_4_URL`

`.env` は Git 管理しない前提です（`.gitignore` 対象）。
`TARGET_1` 〜 `TARGET_4` の `NAME` / `URL` が未設定の場合、アプリ起動時にエラーになります。

## 使い方

### 1. 初期セッション作成（ログイン + 成人向け表示設定）

```bash
python app.py init-session
```

Chrome が開いたら:

1. 駿河屋へログイン
2. 成人向け表示を有効化
3. 対象ページで表示を確認
4. ターミナルに戻って Enter

Cookieは `surugaya_cookies.json` に保存されます。

### 2. 監視を1回実行

```bash
python app.py check
```

### 3. 監視実行後にUI表示（最終ページ到達で終了）

```bash
python app.py watch
```

### 4. UIのみ起動

```bash
python app.py serve-ui --host 127.0.0.1 --port 8080
```

ブラウザで以下を開きます。

- http://127.0.0.1:8080

### Windows向け1行実行

```bash
run_monitor.bat
```

### ページ数を制限したい場合

```bash
python app.py check --max-pages 10
python app.py watch --max-pages 10
```

## 保存ファイル

- `surugaya_cookies.json`: ログインCookie
- `target_data/<target_id>/saved_items.json`: 監視用スナップショット
- `target_data/<target_id>/latest_check.json`: 最新結果
- `target_data/<target_id>/check_results.jsonl`: 実行履歴（追記）

上記の実行生成物は `.gitignore` でGit対象外にしています。

## 最新結果をCLIで確認

```bash
python app.py show-last --target default
```

## 備考

- サイトHTML構造が変わると抽出ロジックの修正が必要です
- Cookieの有効期限が切れたら `init-session` を再実行してください
- 利用規約および法令に従って利用してください
