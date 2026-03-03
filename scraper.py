import json
import os
import re
import time
from datetime import datetime
from html import unescape
from typing import Any, Optional
from urllib.error import HTTPError
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit
from urllib.request import Request, urlopen

from selenium import webdriver
from selenium.webdriver.chrome.options import Options

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


def _safe_target_id(target_id: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_-]", "_", target_id).strip("_")
    return cleaned or DEFAULT_TARGET_ID


def _target_dir(target_id: str) -> str:
    path = os.path.join(TARGET_DATA_DIR, _safe_target_id(target_id))
    os.makedirs(path, exist_ok=True)
    return path


def _target_files(target_id: str) -> dict[str, str]:
    root = _target_dir(target_id)
    return {
        "saved": os.path.join(root, "saved_items.json"),
        "latest": os.path.join(root, "latest_check.json"),
        "log": os.path.join(root, "check_results.jsonl"),
    }


def latest_report_file(target_id: str = DEFAULT_TARGET_ID) -> str:
    return _target_files(target_id)["latest"]


def _load_snapshot(target_id: str = DEFAULT_TARGET_ID) -> tuple[set[str], dict[str, dict[str, str]]]:
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
    payload = {
        "ids": sorted(ids),
        "details": details,
    }
    files = _target_files(target_id)
    with open(files["saved"], "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

def _build_chrome_driver(headless: bool = True) -> webdriver.Chrome:
    options = Options()
    options.page_load_strategy = "eager"
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    return webdriver.Chrome(options=options)


def _save_cookies(driver: webdriver.Chrome) -> None:
    cookies = driver.get_cookies()
    with open(COOKIE_FILE, "w", encoding="utf-8") as f:
        json.dump(cookies, f, ensure_ascii=False, indent=2)
    print(f"Saved {len(cookies)} cookies to {COOKIE_FILE}")


def bootstrap_login_session(open_url: str = DEFAULT_BASE_URL) -> None:
    driver = _build_chrome_driver(headless=False)
    try:
        print("Browser opened.")
        print("1) Login to suruga-ya in the opened browser.")
        print("2) Enable adult-content visibility.")
        print("3) Open your target page and confirm adult items are visible.")
        print("4) Return here and press Enter.")
        driver.get(open_url)
        input("Press Enter after setup is complete...")
        _save_cookies(driver)
    finally:
        driver.quit()


def _load_cookie_header() -> str:
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


def _fetch_html(url: str, cookie_header: str, user_agent: str, referer: str = "") -> str:
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
    no_script = re.sub(r"<script.*?</script>", "", text, flags=re.I | re.S)
    no_style = re.sub(r"<style.*?</style>", "", no_script, flags=re.I | re.S)
    no_tags = re.sub(r"<[^>]+>", " ", no_style)
    return re.sub(r"\s+", " ", unescape(no_tags)).strip()


def _extract_value(tag: str, attr: str) -> str:
    m = re.search(rf'{attr}\s*=\s*"([^"]+)"', tag, flags=re.I)
    if m:
        return m.group(1).strip()
    m = re.search(rf"{attr}\s*=\s*'([^']+)'", tag, flags=re.I)
    if m:
        return m.group(1).strip()
    return ""


def _extract_price(html_fragment: str, text: str) -> str:
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
    parts = urlsplit(base_url)
    query_items = parse_qsl(parts.query, keep_blank_values=True)
    query_items = [(k, v) for (k, v) in query_items if k.lower() != "page"]
    if page > 1:
        query_items.append(("page", str(page)))
    new_query = urlencode(query_items, doseq=True)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, new_query, parts.fragment))


def _get_all_items_http(base_url: str, max_pages: Optional[int] = None) -> dict[str, dict[str, str]]:
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
    try:
        return _get_all_items_http(base_url=base_url, max_pages=max_pages)
    except Exception as exc:
        print(f"HTTP mode failed: {exc}")
        return {}


def _write_report(report: dict[str, Any], target_id: str = DEFAULT_TARGET_ID) -> None:
    files = _target_files(target_id)
    with open(files["latest"], "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    with open(files["log"], "a", encoding="utf-8") as f:
        f.write(json.dumps(report, ensure_ascii=False) + "\n")

def load_latest_report(target_id: str = DEFAULT_TARGET_ID) -> dict[str, Any]:
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


def check_new_items(
    max_pages: Optional[int] = None,
    base_url: str = DEFAULT_BASE_URL,
    target_id: str = DEFAULT_TARGET_ID,
) -> dict[str, Any]:
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



