import json
import os
import re
import shutil
import socket
import subprocess
import time
from datetime import datetime
from html import unescape
from typing import Any, Optional
from urllib.error import HTTPError
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit
from urllib.request import Request, urlopen

from selenium import webdriver
from selenium.common.exceptions import NoSuchWindowException
from selenium.webdriver.chrome.options import Options

# Suruga-yaチェックの中核ロジック:
# - HTTPでページを巡回して商品を収集
# - 前回との差分から新着を判定
# - 結果をJSONとして保存
DEFAULT_BASE_URL = (
    "https://www.suruga-ya.jp/search"
    "?category=50108020209"
    "&search_word="
    "&adult_s=1"
    "&hendou=%E6%96%B0%E5%85%A5%E8%8D%B7"
    "&rankBy=modificationTime:descending"
)

DEFAULT_TARGET_ID = "default"
COOKIE_FILE = "surugaya_cookies.json"
TARGET_DATA_DIR = "target_data"
MATOME_CAMPAIGN_URL = "https://www.suruga-ya.jp/feature/campaign/index.html#matome"
SALE_DATA_DIR = os.path.join(TARGET_DATA_DIR, "sales")

HTTP_TIMEOUT_SECONDS = 8
HTTP_RETRIES = 8
PAGE_INTERVAL_SECONDS = 0.12
USER_AGENTS = [
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) "
        "Gecko/20100101 Firefox/123.0"
    ),
    (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_5) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) "
        "Version/17.0 Safari/605.1.15"
    ),
]


def _read_dotenv_value(key: str, path: str = ".env", default: str = "") -> str:
    """`.env` から単一キーを読み取る。環境変数があればそれを優先する。"""
    value = os.environ.get(key, "").strip()
    if value:
        return value

    if not os.path.exists(path):
        return default

    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            for raw_line in f:
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                current_key, current_value = line.split("=", 1)
                if current_key.strip() != key:
                    continue
                current_value = current_value.strip()
                if (
                    current_value.startswith('"')
                    and current_value.endswith('"')
                    or current_value.startswith("'")
                    and current_value.endswith("'")
                ):
                    current_value = current_value[1:-1]
                return current_value
    except OSError:
        return default

    return default


def _default_chrome_user_data_dir() -> str:
    """Windows の既定 Chrome ユーザーデータディレクトリを返す。"""
    local_app_data = os.environ.get("LOCALAPPDATA", "").strip()
    if not local_app_data:
        return ""
    return os.path.join(local_app_data, "Google", "Chrome", "User Data")


def _default_chrome_executable() -> str:
    """Windows の既定 Chrome 実行ファイル候補を返す。"""
    candidates = [
        os.path.join(
            os.environ.get("PROGRAMFILES", "").strip(),
            "Google",
            "Chrome",
            "Application",
            "chrome.exe",
        ),
        os.path.join(
            os.environ.get("PROGRAMFILES(X86)", "").strip(),
            "Google",
            "Chrome",
            "Application",
            "chrome.exe",
        ),
        os.path.join(
            os.environ.get("LOCALAPPDATA", "").strip(),
            "Google",
            "Chrome",
            "Application",
            "chrome.exe",
        ),
    ]
    for path in candidates:
        if path and os.path.exists(path):
            return path
    return "chrome"


def _wait_for_debug_port(host: str, port: int, timeout_seconds: float = 10.0) -> None:
    """Chrome のリモートデバッグポートが開くまで待つ。"""
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.5):
                return
        except OSError:
            time.sleep(0.2)
    raise RuntimeError(f"Chrome remote debugging port did not open: {host}:{port}")


def _prepare_debug_profile(user_data_dir: str, profile_directory: str) -> str:
    """既存 Chrome プロファイルのコピーをローカル作業用に作成する。"""
    temp_root = os.path.join(os.getcwd(), ".chrome-debug-profile")
    if os.path.isdir(temp_root):
        shutil.rmtree(temp_root)
    os.makedirs(temp_root, exist_ok=True)

    local_state_src = os.path.join(user_data_dir, "Local State")
    local_state_dst = os.path.join(temp_root, "Local State")
    if os.path.exists(local_state_src):
        shutil.copy2(local_state_src, local_state_dst)

    profile_src = os.path.join(user_data_dir, profile_directory)
    profile_dst = os.path.join(temp_root, profile_directory)
    if not os.path.isdir(profile_src):
        raise RuntimeError(f"Chrome profile directory not found: {profile_src}")
    shutil.copytree(profile_src, profile_dst)
    return temp_root


def _should_copy_profile_for_debug() -> bool:
    """デバッグ起動時に既存プロファイルをコピーするかを返す。"""
    raw = _read_dotenv_value("CHROME_COPY_PROFILE_FOR_DEBUG", default="0").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _launch_chrome_for_debugging(open_url: str) -> tuple[subprocess.Popen, str, str]:
    """通常の Chrome をリモートデバッグ付きで起動する。"""
    chrome_path = _read_dotenv_value("CHROME_PATH", default=_default_chrome_executable()).strip()
    user_data_dir = _read_dotenv_value("CHROME_USER_DATA_DIR", default="").strip()
    profile_directory = _read_dotenv_value("CHROME_PROFILE_DIRECTORY", default="").strip()
    debug_host = _read_dotenv_value("CHROME_REMOTE_DEBUGGING_HOST", default="127.0.0.1").strip()
    debug_port_raw = _read_dotenv_value("CHROME_REMOTE_DEBUGGING_PORT", default="9222").strip()
    debug_port = int(debug_port_raw) if debug_port_raw.isdigit() else 9222
    debug_user_data_dir = ""
    if user_data_dir and profile_directory and _should_copy_profile_for_debug():
        debug_user_data_dir = _prepare_debug_profile(user_data_dir, profile_directory)
    elif not user_data_dir:
        debug_user_data_dir = os.path.join(os.getcwd(), ".chrome-debug-session")
        if os.path.isdir(debug_user_data_dir):
            shutil.rmtree(debug_user_data_dir, ignore_errors=True)
        os.makedirs(debug_user_data_dir, exist_ok=True)

    command = [
        chrome_path,
        f"--remote-debugging-port={debug_port}",
    ]
    if debug_user_data_dir:
        command.append(f"--user-data-dir={debug_user_data_dir}")
    if profile_directory:
        command.append(f"--profile-directory={profile_directory}")
    command.append(open_url)

    process = subprocess.Popen(command)
    _wait_for_debug_port(debug_host, debug_port)
    return process, f"{debug_host}:{debug_port}", debug_user_data_dir


def _safe_target_id(target_id: str) -> str:
    """ファイル名/フォルダ名に使える安全なID文字列へ変換する。"""
    cleaned = re.sub(r"[^a-zA-Z0-9_-]", "_", target_id).strip("_")
    return cleaned or DEFAULT_TARGET_ID


def _target_dir(target_id: str) -> str:
    """ターゲット専用ディレクトリを返す。存在しなければ作成する。"""
    path = os.path.join(TARGET_DATA_DIR, _safe_target_id(target_id))
    os.makedirs(path, exist_ok=True)
    return path


def _target_files(target_id: str) -> dict[str, str]:
    """ターゲット別の保存先ファイルパス群を返す。"""
    root = _target_dir(target_id)
    return {
        "saved": os.path.join(root, "saved_items.json"),
        "latest": os.path.join(root, "latest_check.json"),
        "log": os.path.join(root, "check_results.jsonl"),
    }


def _sale_cache_files(sale_id: str = "") -> dict[str, str]:
    """セール情報キャッシュの保存先を返す。"""
    os.makedirs(SALE_DATA_DIR, exist_ok=True)
    files = {
        "campaigns": os.path.join(SALE_DATA_DIR, "matome_campaigns.json"),
    }
    if sale_id:
        files["items"] = os.path.join(SALE_DATA_DIR, f"{_safe_target_id(sale_id)}_items.json")
    return files


def latest_report_file(target_id: str = DEFAULT_TARGET_ID) -> str:
    """最新レポートJSONのパスを返す。"""
    return _target_files(target_id)["latest"]


def _load_snapshot(target_id: str = DEFAULT_TARGET_ID) -> tuple[set[str], dict[str, dict[str, str]]]:
    """前回スナップショットを読み込む。

    返り値:
    - 既知ID集合
    - 変更商品の詳細辞書（必要なものだけ保持）
    """
    files = _target_files(target_id)
    source = files["saved"]
    if not os.path.exists(source):
        return set(), {}

    with open(source, "r", encoding="utf-8") as f:
        raw = json.load(f)

    # New compact format
    if isinstance(raw, dict) and "ids" in raw:
        ids = set(str(x) for x in raw.get("ids", []))
        details = raw.get("details", {})
        if not isinstance(details, dict):
            details = {}
        return ids, details

    # Legacy map format: {id: detail}
    if isinstance(raw, dict):
        ids = set(raw.keys())
        details = {k: v for k, v in raw.items() if isinstance(v, dict)}
        return ids, details

    return set(), {}


def _save_snapshot(
    ids: set[str],
    details: dict[str, dict[str, str]],
    target_id: str = DEFAULT_TARGET_ID,
) -> None:
    """現在のID集合と必要詳細をコンパクト形式で保存する。"""
    payload = {
        "ids": sorted(ids),
        "details": details,
    }
    files = _target_files(target_id)
    with open(files["saved"], "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

def _build_chrome_driver(
    headless: bool = True,
    debugger_address: str = "",
) -> webdriver.Chrome:
    """Cookie取得用のChromeドライバーを生成する。"""
    options = Options()
    options.page_load_strategy = "eager"
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    if debugger_address:
        options.debugger_address = debugger_address
    else:
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)
    return webdriver.Chrome(options=options)


def _save_cookies(driver: webdriver.Chrome) -> None:
    """ブラウザのCookieをJSONへ保存する。"""
    try:
        cookies = driver.get_cookies() or []
        if not cookies:
            payload = driver.execute_cdp_cmd("Network.getAllCookies", {})
            cookies = payload.get("cookies", []) if isinstance(payload, dict) else []
    except NoSuchWindowException as exc:
        raise RuntimeError(
            "The Chrome window was closed before cookies could be saved."
        ) from exc
    with open(COOKIE_FILE, "w", encoding="utf-8") as f:
        json.dump(cookies, f, ensure_ascii=False, indent=2)
    print(f"Saved {len(cookies)} cookies to {COOKIE_FILE}")


def bootstrap_login_session(open_url: str = DEFAULT_BASE_URL) -> None:
    """手動ログインセッションを開始し、最終的にCookieを保存する。"""
    print("Launching Chrome with remote debugging enabled...")
    chrome_process, debugger_address, debug_user_data_dir = _launch_chrome_for_debugging(open_url)
    driver = _build_chrome_driver(headless=False, debugger_address=debugger_address)
    try:
        print("Browser opened.")
        print("A temporary copy of your Chrome profile is being used for this session.")
        print("1) Login to suruga-ya in the opened browser.")
        print("2) Adjust the site display settings you need.")
        print("3) Open your target page and confirm the page is displayed as expected.")
        print("4) Return here and press Enter.")
        input("Press Enter after setup is complete...")
        _save_cookies(driver)
    finally:
        try:
            driver.quit()
        finally:
            if chrome_process.poll() is None:
                chrome_process.terminate()
            if os.path.isdir(debug_user_data_dir):
                shutil.rmtree(debug_user_data_dir, ignore_errors=True)


def _load_cookie_header() -> str:
    """保存済みCookie JSONをHTTPヘッダー文字列へ変換する。"""
    if not os.path.exists(COOKIE_FILE):
        return ""
    try:
        with open(COOKIE_FILE, "r", encoding="utf-8") as f:
            cookies = json.load(f)
    except Exception:
        return ""

    pairs = []
    for cookie in cookies:
        name = cookie.get("name")
        value = cookie.get("value")
        if name and value:
            pairs.append(f"{name}={value}")
    return "; ".join(pairs)


def _cookie_list_from_header(header: str) -> list[dict[str, str]]:
    """`name=value; ...` 形式のCookie文字列をJSON保存形式へ変換する。"""
    rows: list[dict[str, str]] = []
    for part in header.split(";"):
        item = part.strip()
        if not item or "=" not in item:
            continue
        name, value = item.split("=", 1)
        name = name.strip()
        value = value.strip()
        if not name:
            continue
        rows.append({"name": name, "value": value})
    return rows


def save_cookie_header(header: str) -> int:
    """Cookieヘッダー文字列を `surugaya_cookies.json` として保存する。"""
    cookies = _cookie_list_from_header(header)
    with open(COOKIE_FILE, "w", encoding="utf-8") as f:
        json.dump(cookies, f, ensure_ascii=False, indent=2)
    return len(cookies)


def import_cookies_from_file(path: str) -> int:
    """JSON もしくは `name=value; ...` 形式のファイルから Cookie を保存する。"""
    with open(path, "r", encoding="utf-8-sig") as f:
        raw = f.read().strip()

    cookies: list[dict[str, Any]]
    if not raw:
        cookies = []
    elif raw.startswith("["):
        parsed = json.loads(raw)
        if not isinstance(parsed, list):
            raise RuntimeError("Cookie JSON must be a list.")
        cookies = [row for row in parsed if isinstance(row, dict)]
    else:
        cookies = _cookie_list_from_header(raw)

    with open(COOKIE_FILE, "w", encoding="utf-8") as f:
        json.dump(cookies, f, ensure_ascii=False, indent=2)
    return len(cookies)


def _fetch_html(url: str, cookie_header: str, user_agent: str, referer: str = "") -> str:
    """1ページ分のHTMLをHTTP取得して文字列で返す。"""
    headers = {
        "User-Agent": user_agent,
        "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    if referer:
        headers["Referer"] = referer
    if cookie_header:
        headers["Cookie"] = cookie_header

    req = Request(url, headers=headers)
    with urlopen(req, timeout=HTTP_TIMEOUT_SECONDS) as res:
        raw = res.read()
        charset = res.headers.get_content_charset() or "utf-8"
    return raw.decode(charset, errors="ignore")


def _strip_tags(text: str) -> str:
    """HTML断片からタグを除去して可読テキストへ変換する。"""
    no_script = re.sub(r"<script.*?</script>", "", text, flags=re.I | re.S)
    no_style = re.sub(r"<style.*?</style>", "", no_script, flags=re.I | re.S)
    no_tags = re.sub(r"<[^>]+>", " ", no_style)
    return re.sub(r"\s+", " ", unescape(no_tags)).strip()


def _extract_value(tag: str, attr: str) -> str:
    """HTMLタグ文字列から属性値を取り出す。"""
    m = re.search(rf'{attr}\s*=\s*"([^"]+)"', tag, flags=re.I)
    if m:
        return m.group(1).strip()
    m = re.search(rf"{attr}\s*=\s*'([^']+)'", tag, flags=re.I)
    if m:
        return m.group(1).strip()
    return ""


def _extract_price(html_fragment: str, text: str) -> str:
    """HTML断片とテキストから価格表記を抽出する。"""
    # Sold-out text should be prioritized over any numeric fallback parsing.
    sold_out_markers = [
        "申し訳ございません。品切れ中です。",
        "申し訳ございません。品切れ中です",
        "品切れ中です",
        "売り切れ",
    ]
    for marker in sold_out_markers:
        if marker in html_fragment or marker in text:
            return "売り切れ"

    # Prefer explicit price element:
    # <span class="text-price-detail price-buy">580円 (税込)</span>
    span_patterns = [
        r'<span\b[^>]*class\s*=\s*"(?=[^"]*\btext-price-detail\b)(?=[^"]*\bprice-buy\b)[^"]*"[^>]*>(.*?)</span>',
        r"<span\b[^>]*class\s*=\s*'(?=[^']*\btext-price-detail\b)(?=[^']*\bprice-buy\b)[^']*'[^>]*>(.*?)</span>",
    ]
    for pat in span_patterns:
        m = re.search(pat, html_fragment, flags=re.I | re.S)
        if not m:
            continue
        value = _strip_tags(m.group(1))
        if re.search(r"\d", value):
            return value

    fallback_patterns = [
        r"[¥￥]\s*([0-9][0-9,]*)",
        r"([0-9][0-9,]*)\s*円",
    ]
    for pat in fallback_patterns:
        m = re.search(pat, text)
        if not m:
            continue
        num = m.group(1).replace(",", "")
        if num.isdigit():
            return f"{int(num):,}円"
    return ""


def _extract_items_from_html(html: str, base_url: str) -> dict[str, dict[str, str]]:
    """検索結果HTMLから商品ID単位の情報を抽出する。"""
    items: dict[str, dict[str, str]] = {}
    price_by_id: dict[str, str] = {}

    for m in re.finditer(r"/product/[^/]+/([^/?#&\"']+)", html):
        pid = m.group(1)
        if pid in price_by_id:
            continue
        snippet = html[m.start() : m.start() + 2000]
        found_price = _extract_price(snippet, _strip_tags(snippet))
        if found_price:
            price_by_id[pid] = found_price

    anchor_pattern = re.compile(
        r'<a\b[^>]*href\s*=\s*"([^"]*?/product/[^"]+)"[^>]*>(.*?)</a>',
        flags=re.I | re.S,
    )

    def is_stock_name(name: str) -> bool:
        return bool(re.match(r"^\(\d+点の中古品\)$", name.strip()))

    def prefer_url(cur: str, nxt: str) -> str:
        if not cur:
            return nxt
        if "/detail/" in cur and "/detail/" not in nxt:
            return cur
        if "/detail/" in nxt and "/detail/" not in cur:
            return nxt
        return cur

    def prefer_name(cur: str, nxt: str) -> str:
        if not cur:
            return nxt
        if is_stock_name(cur) and not is_stock_name(nxt):
            return nxt
        return cur

    for href_raw, inner_html in anchor_pattern.findall(html):
        href = urljoin(base_url, unescape(href_raw).strip())
        m = re.search(r"/product/[^/]+/([^/?#&]+)", href)
        if not m:
            continue
        pid = m.group(1)

        image_url = ""
        img_match = re.search(r"<img\b[^>]*>", inner_html, flags=re.I | re.S)
        if img_match:
            img_tag = img_match.group(0)
            for key in ["data-original", "data-src", "data-lazy", "srcset", "src"]:
                value = _extract_value(img_tag, key)
                if not value:
                    continue
                if key == "srcset":
                    value = value.split(",")[0].strip().split(" ")[0]
                if value.startswith("//"):
                    value = "https:" + value
                image_url = urljoin(base_url, value)
                break

        name = _extract_value(img_match.group(0), "alt") if img_match else ""
        text = _strip_tags(inner_html)
        if not name:
            name = text
        price = price_by_id.get(pid, "") or _extract_price(inner_html, text)

        existing = items.get(pid, {"name": "", "url": "", "image_url": "", "price": ""})
        items[pid] = {
            "name": prefer_name(existing.get("name", ""), name),
            "url": prefer_url(existing.get("url", ""), href),
            "image_url": existing.get("image_url", "") or image_url,
            "price": existing.get("price", "") or price,
        }

    return {pid: d for pid, d in items.items() if d.get("name")}


def _build_page_url(base_url: str, page: int) -> str:
    """指定ページ番号のURLを生成する。

    既存クエリの `page` は一度除去してから付け直す。
    """
    parts = urlsplit(base_url)
    query_items = parse_qsl(parts.query, keep_blank_values=True)
    query_items = [(k, v) for (k, v) in query_items if k.lower() != "page"]
    if page > 1:
        query_items.append(("page", str(page)))
    new_query = urlencode(query_items, doseq=True)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, new_query, parts.fragment))


def _get_all_items_http(base_url: str, max_pages: Optional[int] = None) -> dict[str, dict[str, str]]:
    """HTTP巡回で複数ページの商品を最後のページまで収集する。"""
    all_items: dict[str, dict[str, str]] = {}
    page = 1
    cookie_header = _load_cookie_header()
    last_url = "https://www.suruga-ya.jp/"

    if cookie_header:
        print("Loaded cookies for HTTP mode.")
    else:
        print("Cookie file not found for HTTP mode.")

    while True:
        if max_pages is not None and page > max_pages:
            print(f"Reached max page limit: {max_pages}")
            break

        url = _build_page_url(base_url, page)
        print(f"[HTTP] Scanning page {page}: {url}")
        html = ""
        last_error: Any = None

        for attempt in range(1, HTTP_RETRIES + 1):
            try:
                user_agent = USER_AGENTS[(attempt - 1) % len(USER_AGENTS)]
                html = _fetch_html(url, cookie_header, user_agent, referer=last_url)
                last_url = url
                break
            except HTTPError as exc:
                last_error = exc
                if exc.code == 404:
                    if page == 1:
                        raise RuntimeError("first page returned 404")
                    print("[HTTP] Reached end page (404). Stop scanning.")
                    return all_items
                if attempt < HTTP_RETRIES:
                    time.sleep(1.2 * attempt if exc.code in (429, 503) else 0.3 * attempt)
            except Exception as exc:
                last_error = exc
                if attempt < HTTP_RETRIES:
                    time.sleep(0.5 * attempt)

        if not html:
            if page == 1:
                raise RuntimeError(f"failed to fetch page {page}: {last_error}")
            print(f"[HTTP] Failed to fetch page {page}: {last_error}. Stop scanning.")
            break

        page_items = _extract_items_from_html(html, base_url=url)
        if not page_items:
            if page == 1:
                raise RuntimeError("first page returned zero items")
            print("[HTTP] No product links found. Stop scanning.")
            break

        all_items.update(page_items)
        print(f"[HTTP] Found {len(page_items)} products on page {page}.")
        time.sleep(PAGE_INTERVAL_SECONDS)
        page += 1

    return all_items


def get_all_items(base_url: str = DEFAULT_BASE_URL, max_pages: Optional[int] = None) -> dict[str, dict[str, str]]:
    """商品収集の公開関数。失敗時は空辞書を返す。"""
    try:
        return _get_all_items_http(base_url=base_url, max_pages=max_pages)
    except Exception as exc:
        print(f"HTTP mode failed: {exc}")
        return {}


def _write_report(report: dict[str, Any], target_id: str = DEFAULT_TARGET_ID) -> None:
    """最新レポートと履歴ログ(JSONL)の両方を書き込む。"""
    files = _target_files(target_id)
    with open(files["latest"], "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    with open(files["log"], "a", encoding="utf-8") as f:
        f.write(json.dumps(report, ensure_ascii=False) + "\n")

def load_latest_report(target_id: str = DEFAULT_TARGET_ID) -> dict[str, Any]:
    """保存済みの最新レポートを読み込む。なければ初期値を返す。"""
    files = _target_files(target_id)
    if os.path.exists(files["latest"]):
        with open(files["latest"], "r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "checked_at": None,
        "total_items": 0,
        "new_items_count": 0,
        "new_items": [],
    }


def load_history(target_id: str = DEFAULT_TARGET_ID, limit: int = 30) -> list[dict[str, Any]]:
    """履歴ログの末尾 `limit` 件を新しい順で返す。"""
    files = _target_files(target_id)
    log_file = files["log"]
    if not os.path.exists(log_file):
        return []

    rows: list[dict[str, Any]] = []
    with open(log_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows[-limit:][::-1]


def _parse_matome_campaigns(html: str) -> list[dict[str, Any]]:
    """キャンペーンページの まとめうり セクションから一覧を抽出する。"""
    start = html.find('<div id="matome"')
    if start < 0:
        return []
    end = html.find("<!-- まとめうり おわり -->", start)
    section = html[start:] if end < 0 else html[start:end]
    blocks = re.findall(r'<div class="campaign_box_ss[^"]*">(.+?)</div><!--campaign_box_ss-->', section, flags=re.S)

    campaigns: list[dict[str, Any]] = []
    for index, block in enumerate(blocks, start=1):
        title_match = re.search(r"<h4>(.*?)</h4>", block, flags=re.S | re.I)
        link_match = re.search(r'<p class="link">.*?<a href="([^"]+)".*?>(.*?)</a>', block, flags=re.S | re.I)
        if not title_match or not link_match:
            continue

        description = ""
        period = ""
        paragraphs = re.findall(r"<p(?:\s+[^>]*)?>(.*?)</p>", block, flags=re.S | re.I)
        for paragraph_html in paragraphs:
            text = _strip_tags(paragraph_html)
            if not text:
                continue
            if text.startswith("期間："):
                period = text
                continue
            if "OFF" in text or "対象商品" in text or "対象ジャンル" in text:
                description = text if not description else f"{description} {text}"

        conditions: list[dict[str, str]] = []
        for minimum_html, discount_html in re.findall(r"<tr><td>(.*?)</td><td>(.*?)</td></tr>", block, flags=re.S | re.I):
            conditions.append(
                {
                    "minimum": _strip_tags(minimum_html),
                    "discount": _strip_tags(discount_html),
                }
            )

        campaigns.append(
            {
                "id": f"matome_{index}",
                "title": _strip_tags(title_match.group(1)),
                "description": description,
                "period": period,
                "link_url": urljoin(MATOME_CAMPAIGN_URL, unescape(link_match.group(1).strip())),
                "link_label": _strip_tags(link_match.group(2)),
                "conditions": conditions,
            }
        )
    return campaigns


def fetch_matome_campaigns() -> list[dict[str, Any]]:
    """まとめうりキャンペーン一覧を取得する。"""
    html = _fetch_html(MATOME_CAMPAIGN_URL, _load_cookie_header(), USER_AGENTS[0], referer="https://www.suruga-ya.jp/")
    return _parse_matome_campaigns(html)


def fetch_sale_items(sale_url: str) -> list[dict[str, str]]:
    """セールリンク先から取得できる商品一覧を返す。"""
    if "/search" in sale_url or "search?" in sale_url:
        items = get_all_items(base_url=sale_url)
    else:
        html = _fetch_html(sale_url, _load_cookie_header(), USER_AGENTS[0], referer=MATOME_CAMPAIGN_URL)
        items = _extract_items_from_html(html, base_url=sale_url)

    return [
        {
            "id": product_id,
            "name": data.get("name", ""),
            "url": data.get("url", ""),
            "image_url": data.get("image_url", ""),
            "price": data.get("price", ""),
        }
        for product_id, data in sorted(items.items(), key=lambda item: item[1].get("name", ""))
    ]


def reset_runtime_data(include_cookies: bool = False) -> list[str]:
    """チェックの実行生成物を削除して差分状態を初期化する。"""
    removed: list[str] = []

    if os.path.isdir(TARGET_DATA_DIR):
        shutil.rmtree(TARGET_DATA_DIR)
        removed.append(TARGET_DATA_DIR)

    if include_cookies and os.path.exists(COOKIE_FILE):
        os.remove(COOKIE_FILE)
        removed.append(COOKIE_FILE)

    return removed


def check_new_items(
    max_pages: Optional[int] = None,
    base_url: str = DEFAULT_BASE_URL,
    target_id: str = DEFAULT_TARGET_ID,
) -> dict[str, Any]:
    """1回分のチェックを実行し、新着差分を判定して保存する。"""
    old_ids, _ = _load_snapshot(target_id=target_id)
    current_items = get_all_items(base_url=base_url, max_pages=max_pages)

    print("\n=== Update Check ===")
    checked_at = datetime.now().isoformat(timespec="seconds")
    print(f"Checked at: {checked_at}")

    if not current_items:
        print("Fetch returned 0 items. Skip saving to protect previous data.")
        return {
            "checked_at": checked_at,
            "total_items": len(old_ids),
            "new_items_count": 0,
            "new_items": [],
            "warning": "fetch returned zero items; previous snapshot retained",
        }

    current_ids = set(current_items.keys())
    new_ids = current_ids - old_ids

    new_items: list[dict[str, str]] = []
    for pid in sorted(new_ids):
        data = current_items[pid]
        new_items.append(
            {
                "id": pid,
                "name": data.get("name", ""),
                "url": data.get("url", ""),
                "image_url": data.get("image_url", ""),
                "price": data.get("price", ""),
            }
        )

    # Keep compact snapshot: all current IDs + only changed(new) item details.
    details_to_store: dict[str, dict[str, str]] = {}
    for pid in new_ids:
        details_to_store[pid] = current_items[pid]
    _save_snapshot(ids=current_ids, details=details_to_store, target_id=target_id)

    report = {
        "checked_at": checked_at,
        "target_id": target_id,
        "target_url": base_url,
        "total_items": len(current_ids),
        "new_items_count": len(new_items),
        "new_items": new_items,
    }
    _write_report(report, target_id=target_id)

    print(f"New items: {len(new_items)}")
    print(f"Total items now: {len(current_ids)}")
    return report



