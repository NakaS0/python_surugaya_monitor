import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from fixed_targets import FIXED_TARGETS
from scraper import check_new_items, load_history, load_latest_report


HTML_PAGE = """<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>駿河屋新着速報</title>
  <style>
    :root {
      --bg:#f6f8fb;
      --card:#ffffff;
      --line:#d9e2ec;
      --ink:#102a43;
      --muted:#627d98;
      --accent:#0f766e;
      --link:#175cd3;
      --soft:#ecfeff;
      --soft-border:#67e8f9;
    }
    * { box-sizing:border-box; }
    body {
      margin:0;
      background:var(--bg);
      color:var(--ink);
      font-family:"Yu Gothic UI","Meiryo",sans-serif;
    }
    .wrap { max-width:1300px; margin:18px auto; padding:0 12px 20px; }
    .head {
      display:flex;
      justify-content:space-between;
      align-items:flex-end;
      gap:10px;
      margin-bottom:10px;
    }
    .title { font-size:24px; font-weight:800; }
    .muted { color:var(--muted); font-size:12px; }
    .card {
      background:var(--card);
      border:1px solid var(--line);
      border-radius:12px;
      padding:12px;
      margin-bottom:12px;
    }
    .row { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:10px; }
    .target-title { font-size:15px; font-weight:700; margin-bottom:8px; }
    .kpi-grid { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:8px; margin-bottom:10px; }
    .kpi {
      border:1px solid var(--line);
      border-radius:10px;
      padding:10px;
      user-select:none;
    }
    .kpi.new {
      border-color:var(--soft-border);
      background:var(--soft);
      cursor:pointer;
    }
    .kpi.new.selected { outline:2px solid var(--accent); }
    .k { font-size:11px; color:var(--muted); }
    .v { font-size:20px; font-weight:800; margin-top:4px; }
    .accent { color:var(--accent); }
    .badge {
      display:inline-block;
      margin-left:6px;
      padding:2px 7px;
      border-radius:999px;
      font-size:10px;
      font-weight:700;
      vertical-align:middle;
      background:#06b6d4;
      color:#fff;
    }
    button {
      border:1px solid var(--line);
      background:#fff;
      border-radius:8px;
      padding:6px 10px;
      cursor:pointer;
      font-size:12px;
    }
    button.primary {
      background:var(--accent);
      color:#fff;
      border-color:var(--accent);
    }
    .history-title {
      font-size:12px;
      color:var(--muted);
      margin-bottom:6px;
      font-weight:700;
    }
    .history-list {
      margin:0;
      padding-left:18px;
      font-size:12px;
      color:#334e68;
    }
    .history-list li { margin:2px 0; }
    table { width:100%; border-collapse:collapse; font-size:13px; }
    th,td { border-bottom:1px solid var(--line); padding:8px 6px; text-align:left; vertical-align:top; }
    th { color:var(--muted); background:#f8fbff; }
    .thumb {
      width:72px;
      height:54px;
      object-fit:cover;
      border:1px solid var(--line);
      border-radius:6px;
      background:#edf2f7;
    }
    a { color:var(--link); text-decoration:none; }
    a:hover { text-decoration:underline; }
    @media (max-width:1200px) { .row { grid-template-columns:repeat(2,minmax(0,1fr)); } }
    @media (max-width:760px) { .row { grid-template-columns:1fr; } }
  </style>
</head>
<body>
  <div class="wrap">
    <div class="head">
      <div>
        <div class="title">監視URL ダッシュボード</div>
        <div class="muted">新着件数をクリックすると、下に新着商品の詳細を表示します。</div>
      </div>
      <div class="muted" id="updatedAt">読み込み中...</div>
    </div>

    <div class="card">
      <button class="primary" onclick="runAll()">全URLを監視実行</button>
      <span class="muted" id="runStatus"></span>
    </div>

    <div id="targetCards" class="row"></div>

    <div class="card">
      <div class="muted" id="detailSource"></div>
      <table>
        <thead><tr><th>画像</th><th id="detailHeader">新着商品の詳細</th></tr></thead>
        <tbody id="detailRows"></tbody>
      </table>
    </div>
  </div>

  <script>
    const PLACEHOLDER = "data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='600' height='450'><rect width='100%25' height='100%25' fill='%23edf2f7'/><text x='50%25' y='50%25' dominant-baseline='middle' text-anchor='middle' font-size='24' fill='%2361798a'>NO IMAGE</text></svg>";
    const TAB_CLOSE_SIGNAL_KEY = "monitor_dashboard_close_signal_v1";
    const THIS_TAB_ID = (window.crypto && crypto.randomUUID) ? crypto.randomUUID() : String(Date.now()) + Math.random().toString(16).slice(2);

    let targetMeta = [];
    let latestByTarget = {};
    let historyByTarget = {};
    let selectedTargetId = "default";

    function closeThisTabOrBlank() {
      window.close();
      setTimeout(() => { if (!window.closed) location.replace("about:blank"); }, 120);
    }
    function broadcastCloseOtherTabs() {
      localStorage.setItem(TAB_CLOSE_SIGNAL_KEY, JSON.stringify({ from: THIS_TAB_ID, ts: Date.now() }));
    }
    window.addEventListener("storage", (ev) => {
      if (ev.key !== TAB_CLOSE_SIGNAL_KEY || !ev.newValue) return;
      try {
        const msg = JSON.parse(ev.newValue);
        if (msg.from && msg.from !== THIS_TAB_ID) closeThisTabOrBlank();
      } catch {}
    });

    async function api(url, options = {}) {
      const res = await fetch(url, options);
      if (!res.ok) throw new Error(await res.text());
      return await res.json();
    }

    function e(s) {
      return (s ?? "").replace(/[&<>"']/g, (c) => ({ "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;" }[c]));
    }

    function pick(targetId) {
      selectedTargetId = targetId;
      renderTargetCards();
      renderDetailRows();
    }

    function formatHistoryRow(h) {
      const checkedAt = e(h.checked_at || "-");
      const total = Number(h.total_items || 0);
      const news = Number(h.new_items_count || 0);
      return `${checkedAt} / 取得:${total} / 新着:${news}`;
    }

    function renderTargetCards() {
      const cards = [];
      for (const t of targetMeta) {
        const latest = latestByTarget[t.id] || {};
        const hist = historyByTarget[t.id] || [];
        const newCount = Number(latest.new_items_count || 0);
        const total = Number(latest.total_items || 0);
        const isSelected = selectedTargetId === t.id;
        const newBadge = newCount > 0 ? "<span class='badge'>変化あり</span>" : "";
        const historyRows = hist.length
          ? hist.map((h) => `<li>${formatHistoryRow(h)}</li>`).join("")
          : "<li>履歴なし</li>";

        cards.push(`
          <section class="card">
            <div class="target-title">${e(t.name)}</div>
            <div class="kpi-grid">
              <div class="kpi">
                <div class="k">取得商品数</div>
                <div class="v">${total}</div>
              </div>
              <div class="kpi new ${isSelected ? "selected" : ""}" onclick="pick('${t.id}')" title="新着詳細を表示">
                <div class="k">新着件数${newBadge}</div>
                <div class="v accent">${newCount}</div>
              </div>
            </div>
            <div class="history-title">直近3回の実行履歴</div>
            <ul class="history-list">${historyRows}</ul>
          </section>
        `);
      }
      document.getElementById("targetCards").innerHTML = cards.join("");
    }

    function renderDetailRows() {
      const latest = latestByTarget[selectedTargetId] || {};
      const target = targetMeta.find((t) => t.id === selectedTargetId);
      const typeLabel = "新着商品の詳細";
      document.getElementById("detailHeader").textContent = typeLabel;
      document.getElementById("detailSource").textContent = target ? `表示元: ${target.name}` : typeLabel;

      const rows = document.getElementById("detailRows");
      const items = latest.new_items || [];
      if (items.length === 0) {
        rows.innerHTML = "<tr><td colspan='2'>この対象では新着商品がありません。</td></tr>";
        return;
      }

      rows.innerHTML = items.map((item) => {
        const img = item.image_url && item.image_url.trim() ? item.image_url : PLACEHOLDER;
        const name = e(item.name || "(商品名なし)");
        const url = e(item.url || "");
        const price = e(item.price || "価格未取得");
        return `
          <tr>
            <td><img class="thumb" src="${img}" alt="${name}" loading="lazy" referrerpolicy="no-referrer" /></td>
            <td>
              <div><strong>${name}</strong></div>
              <div>価格: ${price}</div>
              <a href="${url}" target="_blank" rel="noopener">${url}</a>
            </td>
          </tr>
        `;
      }).join("");
    }

    async function loadTargetsAndResults() {
      targetMeta = await api("/api/targets");
      latestByTarget = {};
      historyByTarget = {};
      for (const t of targetMeta) {
        latestByTarget[t.id] = await api(`/api/latest?target=${encodeURIComponent(t.id)}`);
        historyByTarget[t.id] = await api(`/api/history?target=${encodeURIComponent(t.id)}&limit=3`);
      }
      if (!targetMeta.find((t) => t.id === selectedTargetId) && targetMeta.length > 0) {
        selectedTargetId = targetMeta[0].id;
      }
      renderTargetCards();
      renderDetailRows();
      document.getElementById("updatedAt").textContent = "UI更新: " + new Date().toLocaleString("ja-JP");
    }

    async function runAll() {
      document.getElementById("runStatus").textContent = "全URL監視を実行中...";
      await api("/api/run-check-all", { method: "POST" });
      document.getElementById("runStatus").textContent = "実行完了";
      await loadTargetsAndResults();
    }

    async function boot() {
      broadcastCloseOtherTabs();
      const q = new URLSearchParams(location.search);
      const targetFromQuery = q.get("target");
      if (targetFromQuery) selectedTargetId = targetFromQuery;
      await loadTargetsAndResults();
      setInterval(loadTargetsAndResults, 7000);
    }
    boot();
  </script>
</body>
</html>
"""


class DashboardHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)

        if parsed.path == "/":
            self._send_html(HTML_PAGE)
            return

        if parsed.path == "/api/targets":
            self._send_json(FIXED_TARGETS)
            return

        if parsed.path == "/api/latest":
            target_id = query.get("target", ["default"])[0]
            self._send_json(load_latest_report(target_id=target_id))
            return

        if parsed.path == "/api/history":
            target_id = query.get("target", ["default"])[0]
            try:
                limit = int(query.get("limit", ["3"])[0])
            except ValueError:
                limit = 3
            self._send_json(load_history(target_id=target_id, limit=max(1, limit)))
            return

        self.send_response(404)
        self.end_headers()

    def do_POST(self) -> None:
        parsed = urlparse(self.path)

        if parsed.path == "/api/run-check-all":
            reports = []
            for target in FIXED_TARGETS:
                reports.append(
                    check_new_items(base_url=target["url"], target_id=target["id"], max_pages=None)
                )
            self._send_json({"ok": True, "reports": reports})
            return

        self.send_response(404)
        self.end_headers()

    def log_message(self, format: str, *args) -> None:
        return

    def _send_html(self, html: str) -> None:
        payload = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _send_json(self, payload: dict | list, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def serve_dashboard(host: str = "127.0.0.1", port: int = 8080) -> None:
    server = ThreadingHTTPServer((host, port), DashboardHandler)
    print(f"Dashboard running: http://{host}:{port}")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
