"""Local dashboard server for multi-target monitor status and results."""

from __future__ import annotations

import json
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

from fixed_targets import FIXED_TARGETS
from scraper import check_new_items, load_history, load_latest_report


class MonitorRunManager:
    """Manage background monitoring runs and expose per-target live status."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._run_seq = 0
        self._state: dict[str, Any] = {
            "running": False,
            "run_started_at": None,
            "run_finished_at": None,
            "current_target_id": None,
            "current_target_name": None,
            "total_targets": len(FIXED_TARGETS),
            "completed_targets": 0,
            "targets": self._build_idle_targets(),
        }

    def _build_idle_targets(self) -> dict[str, dict[str, Any]]:
        targets: dict[str, dict[str, Any]] = {}
        for idx, target in enumerate(FIXED_TARGETS, start=1):
            targets[target["id"]] = {
                "id": target["id"],
                "name": target["name"],
                "url": target["url"],
                "order": idx,
                "status": "idle",
                "message": "待機中",
                "started_at": None,
                "finished_at": None,
                "elapsed_seconds": 0,
                "new_items_count": None,
                "last_checked_at": None,
            }
        return targets

    def start_run(self, max_pages: int | None = None) -> tuple[bool, dict[str, Any]]:
        with self._lock:
            if self._state["running"]:
                return False, self._snapshot_locked()

            self._run_seq += 1
            run_started_at = datetime.now().isoformat(timespec="seconds")
            self._state = {
                "running": True,
                "run_started_at": run_started_at,
                "run_started_monotonic": time.monotonic(),
                "run_finished_at": None,
                "current_target_id": None,
                "current_target_name": None,
                "total_targets": len(FIXED_TARGETS),
                "completed_targets": 0,
                "targets": self._build_idle_targets(),
            }
            for target in self._state["targets"].values():
                target["status"] = "queued"
                target["message"] = "開始待ち"

            run_id = self._run_seq
            self._thread = threading.Thread(
                target=self._worker,
                name=f"monitor-run-{run_id}",
                args=(run_id, max_pages),
                daemon=True,
            )
            self._thread.start()
            return True, self._snapshot_locked()

    def _worker(self, run_id: int, max_pages: int | None) -> None:
        for idx, target in enumerate(FIXED_TARGETS, start=1):
            start_monotonic = time.monotonic()
            start_iso = datetime.now().isoformat(timespec="seconds")

            with self._lock:
                if not self._state["running"] or run_id != self._run_seq:
                    return
                row = self._state["targets"][target["id"]]
                row["status"] = "running"
                row["message"] = "監視中"
                row["started_at"] = start_iso
                row["finished_at"] = None
                row["elapsed_seconds"] = 0
                row["new_items_count"] = None
                self._state["current_target_id"] = target["id"]
                self._state["current_target_name"] = target["name"]

            try:
                report = check_new_items(base_url=target["url"], target_id=target["id"], max_pages=max_pages)
                status = "done"
                message = "完了"
                if report.get("warning"):
                    message = str(report["warning"])
                new_items_count = int(report.get("new_items_count") or 0)
                last_checked_at = report.get("checked_at")
            except Exception as exc:  # pragma: no cover
                status = "error"
                message = str(exc)
                new_items_count = None
                last_checked_at = datetime.now().isoformat(timespec="seconds")

            elapsed = int(max(0, round(time.monotonic() - start_monotonic)))
            finish_iso = datetime.now().isoformat(timespec="seconds")

            with self._lock:
                if run_id != self._run_seq:
                    return
                row = self._state["targets"][target["id"]]
                row["status"] = status
                row["message"] = message
                row["finished_at"] = finish_iso
                row["elapsed_seconds"] = elapsed
                row["new_items_count"] = new_items_count
                row["last_checked_at"] = last_checked_at
                if self._state["completed_targets"] < idx:
                    self._state["completed_targets"] = idx
                self._state["current_target_id"] = None
                self._state["current_target_name"] = None

        with self._lock:
            if run_id != self._run_seq:
                return
            self._state["running"] = False
            self._state["run_finished_at"] = datetime.now().isoformat(timespec="seconds")

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return self._snapshot_locked()

    def _snapshot_locked(self) -> dict[str, Any]:
        now_mono = time.monotonic()
        running = bool(self._state.get("running"))

        run_elapsed = 0
        started_mono = self._state.get("run_started_monotonic")
        if isinstance(started_mono, (int, float)):
            run_elapsed = int(max(0, round(now_mono - started_mono)))

        targets: list[dict[str, Any]] = []
        raw_targets = self._state.get("targets", {})
        for target in sorted(raw_targets.values(), key=lambda x: x.get("order", 0)):
            row = dict(target)
            if row.get("status") == "running" and row.get("started_at"):
                started = datetime.fromisoformat(row["started_at"])
                row["elapsed_seconds"] = int(
                    max(0, round((datetime.now() - started).total_seconds()))
                )
            targets.append(row)

        return {
            "running": running,
            "run_started_at": self._state.get("run_started_at"),
            "run_finished_at": self._state.get("run_finished_at"),
            "elapsed_seconds": run_elapsed,
            "current_target_id": self._state.get("current_target_id"),
            "current_target_name": self._state.get("current_target_name"),
            "total_targets": int(self._state.get("total_targets") or 0),
            "completed_targets": int(self._state.get("completed_targets") or 0),
            "targets": targets,
        }


MONITOR_MANAGER = MonitorRunManager()


HTML_PAGE = """<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>監視ダッシュボード</title>
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
      --ok:#0f766e;
      --run:#175cd3;
      --wait:#64748b;
      --err:#b42318;
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
    .monitor-box {
      border:1px solid var(--line);
      border-radius:10px;
      background:#fbfdff;
      padding:8px;
      margin-bottom:10px;
      font-size:12px;
    }
    .monitor-row {
      display:flex;
      justify-content:space-between;
      gap:8px;
      margin:3px 0;
    }
    .monitor-key { color:var(--muted); }
    .monitor-pill {
      font-size:11px;
      padding:1px 8px;
      border-radius:999px;
      font-weight:700;
      color:#fff;
      white-space:nowrap;
    }
    .status-idle { background:var(--wait); }
    .status-queued { background:#94a3b8; }
    .status-running { background:var(--run); }
    .status-done { background:var(--ok); }
    .status-error { background:var(--err); }
    .monitor-note {
      max-width:65%;
      text-align:right;
      color:#334e68;
      overflow-wrap:anywhere;
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
    @media (max-width:760px) {
      .row { grid-template-columns:1fr; }
      .monitor-note { max-width:55%; }
    }
  </style>
</head>
<body>
  <div class="wrap">
    <div class="head">
      <div>
        <div class="title">監視ダッシュボード</div>
        <div class="muted">各URLの監視状態と経過時間をリアルタイム表示します。</div>
      </div>
      <div class="muted" id="updatedAt">読み込み中...</div>
    </div>

    <div class="card">
      <button class="primary" onclick="runAll()">全URLを監視開始</button>
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
    const STICKY_NEW_ITEMS_KEY = "monitor_dashboard_sticky_new_items_v1";
    const THIS_TAB_ID = (window.crypto && crypto.randomUUID) ? crypto.randomUUID() : String(Date.now()) + Math.random().toString(16).slice(2);

    let targetMeta = [];
    let latestByTarget = {};
    let historyByTarget = {};
    let targetStatusById = {};
    let stickyNewItemsByTarget = {};
    let selectedTargetId = "default";
    let monitorRunning = false;

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

    function loadStickyNewItems() {
      try {
        const raw = localStorage.getItem(STICKY_NEW_ITEMS_KEY);
        if (!raw) return {};
        const parsed = JSON.parse(raw);
        return parsed && typeof parsed === "object" ? parsed : {};
      } catch {
        return {};
      }
    }

    function saveStickyNewItems() {
      try {
        localStorage.setItem(STICKY_NEW_ITEMS_KEY, JSON.stringify(stickyNewItemsByTarget));
      } catch {}
    }

    function fmtSeconds(sec) {
      const n = Math.max(0, Number(sec || 0));
      const m = Math.floor(n / 60);
      const s = n % 60;
      return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
    }

    function statusLabel(code) {
      return {
        idle: "待機中",
        queued: "開始待ち",
        running: "監視中",
        done: "完了",
        error: "エラー",
      }[code] || "不明";
    }

    function pick(targetId) {
      selectedTargetId = targetId;
      renderTargetCards();
      renderDetailRowsV2();
    }

    function formatHistoryRow(h) {
      const checkedAt = e(h.checked_at || "-");
      const total = Number(h.total_items || 0);
      const news = Number(h.new_items_count || 0);
      return `${checkedAt} / 合計:${total} / 新着:${news}`;
    }

    function getStatus(targetId) {
      return targetStatusById[targetId] || {
        status: "idle",
        elapsed_seconds: 0,
        message: "待機中",
        new_items_count: null,
      };
    }

    function renderTargetCards() {
      const cards = [];
      for (const t of targetMeta) {
        const latest = latestByTarget[t.id] || {};
        const hist = historyByTarget[t.id] || [];
        const stat = getStatus(t.id);

        const newCount = Number(latest.new_items_count || 0);
        const total = Number(latest.total_items || 0);
        const isSelected = selectedTargetId === t.id;
        const newBadge = newCount > 0 ? "<span class='badge'>新着あり</span>" : "";
        const historyRows = hist.length
          ? hist.map((h) => `<li>${formatHistoryRow(h)}</li>`).join("")
          : "<li>履歴なし</li>";
        const statusText = statusLabel(stat.status);
        const statusClass = `status-${stat.status || "idle"}`;
        const elapsed = fmtSeconds(stat.elapsed_seconds || 0);

        cards.push(`
          <section class="card">
            <div class="target-title">${e(t.name)}</div>
            <div class="kpi-grid">
              <div class="kpi">
                <div class="k">合計商品数</div>
                <div class="v">${total}</div>
              </div>
              <div class="kpi new ${isSelected ? "selected" : ""}" onclick="pick('${t.id}')" title="新着詳細を表示">
                <div class="k">新着件数${newBadge}</div>
                <div class="v accent">${newCount}</div>
              </div>
            </div>
            <div class="monitor-box">
              <div class="monitor-row">
                <span class="monitor-key">監視状態</span>
                <span class="monitor-pill ${statusClass}">${statusText}</span>
              </div>
              <div class="monitor-row">
                <span class="monitor-key">経過時間</span>
                <span>${elapsed}</span>
              </div>
            </div>
            <div class="history-title">直近3回の監視履歴</div>
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
      document.getElementById("detailSource").textContent = target ? `表示中: ${target.name}` : typeLabel;

      const rows = document.getElementById("detailRows");
      const latestItems = Array.isArray(latest.new_items) ? latest.new_items : [];
      let items = latestItems;
      let usingPreviousNewItems = false;

      if (items.length === 0) {
        const historyRows = historyByTarget[selectedTargetId] || [];
        const previousWithNewItems = historyRows.find((h, idx) => {
          if (idx === 0) return false;
          const histItems = Array.isArray(h.new_items) ? h.new_items : [];
          return Number(h.new_items_count || 0) > 0 && histItems.length > 0;
        });
        if (previousWithNewItems) {
          items = previousWithNewItems.new_items;
          usingPreviousNewItems = true;
        }
      }

      if (usingPreviousNewItems && target) {
        document.getElementById("detailSource").textContent = `表示中: ${target.name} (今回0件のため前回新着を表示)`;
      }

      if (items.length === 0) {
        rows.innerHTML = "<tr><td colspan='2'>この監視では新着商品がありません。</td></tr>";
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

    function renderDetailRowsV2() {
      const latest = latestByTarget[selectedTargetId] || {};
      const target = targetMeta.find((t) => t.id === selectedTargetId);
      const typeLabel = "新着商品の詳細";
      document.getElementById("detailHeader").textContent = typeLabel;
      document.getElementById("detailSource").textContent = target ? `表示中: ${target.name}` : typeLabel;

      const rows = document.getElementById("detailRows");
      const latestItems = Array.isArray(latest.new_items) ? latest.new_items : [];
      let items = latestItems;
      let sourceHint = "";

      if (latestItems.length > 0) {
        stickyNewItemsByTarget[selectedTargetId] = latestItems;
        saveStickyNewItems();
      }

      if (items.length === 0) {
        const historyRows = historyByTarget[selectedTargetId] || [];
        const previousWithNewItems = historyRows.find((h, idx) => {
          if (idx === 0) return false;
          const histItems = Array.isArray(h.new_items) ? h.new_items : [];
          return Number(h.new_items_count || 0) > 0 && histItems.length > 0;
        });
        if (previousWithNewItems) {
          items = previousWithNewItems.new_items;
          sourceHint = " (今回0件のため前回新着を表示)";
          stickyNewItemsByTarget[selectedTargetId] = items;
          saveStickyNewItems();
        }
      }

      if (items.length === 0) {
        const stickyItems = Array.isArray(stickyNewItemsByTarget[selectedTargetId])
          ? stickyNewItemsByTarget[selectedTargetId]
          : [];
        if (stickyItems.length > 0) {
          items = stickyItems;
          sourceHint = " (今回0件のため保持中の新着を表示)";
        }
      }

      if (target && sourceHint) {
        document.getElementById("detailSource").textContent = `表示中: ${target.name}${sourceHint}`;
      }

      if (items.length === 0) {
        rows.innerHTML = "<tr><td colspan='2'>この監視では新着商品がありません。</td></tr>";
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
        const latestItems = Array.isArray(latestByTarget[t.id].new_items) ? latestByTarget[t.id].new_items : [];
        if (latestItems.length > 0) {
          stickyNewItemsByTarget[t.id] = latestItems;
        } else {
          const previousWithNewItems = (historyByTarget[t.id] || []).find((h, idx) => {
            if (idx === 0) return false;
            const histItems = Array.isArray(h.new_items) ? h.new_items : [];
            return Number(h.new_items_count || 0) > 0 && histItems.length > 0;
          });
          if (previousWithNewItems) {
            stickyNewItemsByTarget[t.id] = previousWithNewItems.new_items;
          }
        }
      }
      saveStickyNewItems();
      if (!targetMeta.find((t) => t.id === selectedTargetId) && targetMeta.length > 0) {
        selectedTargetId = targetMeta[0].id;
      }
      renderTargetCards();
      renderDetailRowsV2();
      document.getElementById("updatedAt").textContent = "UI更新: " + new Date().toLocaleString("ja-JP");
    }

    async function refreshMonitorStatus() {
      const monitor = await api("/api/monitor-status");
      targetStatusById = {};
      for (const row of (monitor.targets || [])) {
        targetStatusById[row.id] = row;
      }

      const total = Number(monitor.total_targets || 0);
      const completed = Number(monitor.completed_targets || 0);
      const elapsed = fmtSeconds(monitor.elapsed_seconds || 0);
      const prevRunning = monitorRunning;
      monitorRunning = !!monitor.running;

      if (monitorRunning) {
        document.getElementById("runStatus").textContent = `監視中 ${completed}/${total} 経過 ${elapsed}`;
      } else {
        document.getElementById("runStatus").textContent = monitor.run_finished_at
          ? `待機中 (前回完了: ${monitor.run_finished_at})`
          : "待機中";
      }

      renderTargetCards();

      if (prevRunning && !monitorRunning) {
        await loadTargetsAndResults();
      }
    }

    async function runAll() {
      document.getElementById("runStatus").textContent = "監視開始中...";
      const result = await api("/api/run-check-all", { method: "POST" });
      if (!result.started) {
        document.getElementById("runStatus").textContent = "既に監視中です";
      }
      await refreshMonitorStatus();
    }

    async function boot() {
      broadcastCloseOtherTabs();
      stickyNewItemsByTarget = loadStickyNewItems();
      const q = new URLSearchParams(location.search);
      const targetFromQuery = q.get("target");
      if (targetFromQuery) selectedTargetId = targetFromQuery;

      await loadTargetsAndResults();
      await refreshMonitorStatus();

      setInterval(async () => {
        try {
          await refreshMonitorStatus();
        } catch (err) {
          console.error(err);
        }
      }, 1000);

      setInterval(async () => {
        if (monitorRunning) {
          return;
        }
        try {
          await loadTargetsAndResults();
        } catch (err) {
          console.error(err);
        }
      }, 7000);
    }

    boot();
  </script>
</body>
</html>
"""


class DashboardHandler(BaseHTTPRequestHandler):
    """HTTP handler for dashboard page and APIs."""

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

        if parsed.path == "/api/monitor-status":
            self._send_json(MONITOR_MANAGER.snapshot())
            return

        self.send_response(404)
        self.end_headers()

    def do_POST(self) -> None:
        parsed = urlparse(self.path)

        if parsed.path == "/api/run-check-all":
            started, snapshot = MONITOR_MANAGER.start_run(max_pages=None)
            self._send_json({"ok": True, "started": started, "monitor": snapshot})
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
