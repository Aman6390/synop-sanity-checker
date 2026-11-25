"""
IMD SYNOP Monitor & SLA Sanity Checker - Windows 10/11 Desktop Floating Widget
Apple Design System styled, frameless, translucent, always-on-top desktop mini-widget.
"""

from __future__ import annotations

import os
import sys
import json
import socket
import logging
import threading
import subprocess
import webbrowser
import ctypes
from ctypes import windll
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any, Optional

import webview

# Ensure backend directory is in path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.join(BASE_DIR, "backend")
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from fetcher import AMSSFetcher
from gts_parser import GTSParser
from sla_engine import (
    SLAEngine,
    get_synoptic_window_status,
    SYNOPTIC_HOURS,
    HOUR_LABELS,
)

CONFIG_PATH = os.path.join(BACKEND_DIR, "stations_config.json")
DUMP_PATH = os.path.join(BASE_DIR, "sendata_dump.txt")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("SYNOPWidget")


def is_port_active(port: int, host: str = "127.0.0.1") -> bool:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)
            return s.connect_ex((host, port)) == 0
    except Exception:
        return False


class WidgetBackend:
    """Manages cached data fetching, parsing, and SLA engine analysis for the widget."""

    def __init__(self):
        self.cached_data: Optional[Dict[str, Any]] = None
        self.last_fetch_time: Optional[datetime] = None
        self.last_source: str = "Uninitialized"
        self.fetcher = AMSSFetcher()

    def load_stations_config(self) -> List[Dict[str, Any]]:
        if os.path.exists(CONFIG_PATH):
            try:
                with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                    return json.load(f).get("stations", [])
            except Exception as e:
                logger.error(f"Error loading stations config: {e}")
        return []

    def fetch_and_evaluate(self) -> Dict[str, Any]:
        raw_text = None
        source = "AMSS Delhi Live"
        try:
            raw_text = self.fetcher.fetch_live_data()
        except Exception as e:
            logger.warning(f"Live fetch failed ({e}), falling back to local dump...")
            if os.path.exists(DUMP_PATH):
                with open(DUMP_PATH, "r", encoding="utf-8", errors="ignore") as f:
                    raw_text = f.read()
                source = "Local GTS Dump (Backup)"
            else:
                source = "Offline (No Data)"

        if raw_text:
            parsed = GTSParser.parse_bulletin_stream(raw_text)
            now_utc = datetime.now(timezone.utc)
            window_status = get_synoptic_window_status(now_utc)
            stations = self.load_stations_config()

            evaluated_stations = []
            total_on_time = 0
            total_late = 0
            total_missing = 0
            total_early = 0

            for st_cfg in stations:
                st_id = st_cfg["id"]
                st_synops = parsed["synops_by_station"].get(st_id, [])
                eval_res = SLAEngine.evaluate_station_timeliness(st_cfg, st_synops, now_utc)

                # Format slots for widget display
                slots_data = []
                for h in SYNOPTIC_HOURS:
                    slot = eval_res["slots"].get(h, {})
                    slots_data.append({
                        "hour": h,
                        "label": f"{h[:2]}Z",
                        "status": slot.get("status", "NOT_SCHEDULED"),
                        "severity": slot.get("severity", "muted"),
                        "badge_text": slot.get("badge_text", "-"),
                        "received": slot.get("received", False),
                        "transmission_count": slot.get("transmission_count", 0),
                        "duplicate_type": slot.get("duplicate_type", "NONE"),
                        "raw_synop": slot.get("authoritative_synop", {}).get("raw_text", "")
                    })

                counts = eval_res.get("counts", {})
                total_on_time += counts.get("on_time", 0)
                total_late += counts.get("late", 0)
                total_missing += counts.get("missing", 0)
                total_early += counts.get("early", 0)

                evaluated_stations.append({
                    "id": st_id,
                    "name": st_cfg.get("name", st_id),
                    "state": st_cfg.get("state", ""),
                    "required_count": len(st_cfg.get("required_hours", SYNOPTIC_HOURS)),
                    "overall_status": eval_res.get("overall_status", "ALL_NORMAL"),
                    "counts": counts,
                    "slots": slots_data,
                })

            self.last_fetch_time = now_utc
            self.last_source = source

            self.cached_data = {
                "success": True,
                "source": source,
                "total_bulletins": parsed.get("total_bulletins", 0),
                "last_fetch_iso": now_utc.isoformat(),
                "window_status": window_status,
                "metrics": {
                    "total_stations": len(stations),
                    "on_time_slots": total_on_time,
                    "late_slots": total_late,
                    "missing_slots": total_missing,
                    "early_slots": total_early,
                },
                "stations": evaluated_stations,
            }
            return self.cached_data

        return {
            "success": False,
            "source": source,
            "error": "No bulletin data available.",
            "window_status": get_synoptic_window_status(),
            "metrics": {"total_stations": 0, "on_time_slots": 0, "late_slots": 0, "missing_slots": 0, "early_slots": 0},
            "stations": [],
        }


backend_instance = WidgetBackend()


# Win32 Window Positioning Constants
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
SWP_ASYNCWINDOWPOS = 0x4000
HWND_TOPMOST = -1
HWND_NOTOPMOST = -2
SW_MINIMIZE = 6
WM_CLOSE = 0x0010

# Global reference to widget window (kept outside WidgetAPI to avoid circular COM/WinForms introspection)
_widget_window: Optional[webview.Window] = None


def get_widget_hwnd() -> int:
    """Retrieve Win32 HWND safely for asynchronous window operations."""
    global _widget_window
    if _widget_window:
        try:
            import webview.platforms.winforms as wf
            inst = wf.BrowserView.instances.get(_widget_window.uid)
            if inst:
                return int(inst.Handle.ToInt64())
        except Exception:
            pass
    try:
        import ctypes
        hwnd = ctypes.windll.user32.FindWindowW(None, "IMD SYNOP SLA Widget")
        if hwnd:
            return hwnd
    except Exception:
        pass
    return 0


class WidgetAPI:
    """JS API exposed to the frontend inside pywebview."""

    def __init__(self):
        self.is_pinned: bool = True
        self.is_compact: bool = False
        self.full_height: int = 420
        self.compact_height: int = 85
        self.width: int = 370

    def get_data(self) -> str:
        """Called by Javascript on initialization and periodic refresh."""
        try:
            data = backend_instance.fetch_and_evaluate()
            return json.dumps(data)
        except Exception as e:
            logger.error(f"Error in get_data: {e}")
            return json.dumps({"success": False, "error": str(e)})

    def refresh_now(self) -> str:
        """Trigger an instant scrape and evaluation."""
        return self.get_data()

    def toggle_pin(self) -> bool:
        """Toggles always-on-top behavior asynchronously without blocking the UI thread."""
        self.is_pinned = not self.is_pinned
        hwnd = get_widget_hwnd()
        if hwnd:
            try:
                import ctypes
                target = HWND_TOPMOST if self.is_pinned else HWND_NOTOPMOST
                flags = SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_ASYNCWINDOWPOS
                threading.Thread(
                    target=ctypes.windll.user32.SetWindowPos,
                    args=(hwnd, target, 0, 0, 0, 0, flags),
                    daemon=True,
                ).start()
            except Exception as e:
                logger.warning(f"Win32 SetWindowPos error: {e}")
        return self.is_pinned

    def toggle_compact(self) -> bool:
        """Toggles between full station view and compact single-bar glance view."""
        self.is_compact = not self.is_compact
        target_height = self.compact_height if self.is_compact else self.full_height
        hwnd = get_widget_hwnd()
        if hwnd:
            try:
                import ctypes
                flags = SWP_NOMOVE | SWP_NOZORDER | SWP_NOACTIVATE | SWP_ASYNCWINDOWPOS
                threading.Thread(
                    target=ctypes.windll.user32.SetWindowPos,
                    args=(hwnd, 0, 0, 0, self.width, target_height, flags),
                    daemon=True,
                ).start()
            except Exception as e:
                logger.warning(f"Win32 resize error: {e}")
        elif _widget_window:
            try:
                _widget_window.resize(self.width, target_height)
            except Exception:
                pass
        return self.is_compact

    def open_dashboard(self) -> str:
        """Opens the full Streamlit web dashboard in the user's default browser."""
        streamlit_port = 8501
        url = f"http://localhost:{streamlit_port}"

        if not is_port_active(streamlit_port):
            logger.info("Streamlit server not detected on port 8501. Launching in background...")
            cmd = [sys.executable, "-m", "streamlit", "run", "streamlit_app.py", "--server.port", str(streamlit_port), "--server.headless", "true"]
            subprocess.Popen(cmd, cwd=BASE_DIR, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)

        webbrowser.open(url)
        return "opened"

    def minimize(self) -> None:
        hwnd = get_widget_hwnd()
        if hwnd:
            try:
                import ctypes
                threading.Thread(
                    target=ctypes.windll.user32.ShowWindow,
                    args=(hwnd, SW_MINIMIZE),
                    daemon=True,
                ).start()
            except Exception:
                if _widget_window:
                    _widget_window.minimize()
        elif _widget_window:
            _widget_window.minimize()

    def close(self) -> None:
        global _widget_window
        if _widget_window:
            threading.Timer(0.1, _widget_window.destroy).start()


# -----------------------------------------------------------------------------
# Embedded HTML, Apple Design System CSS, and Reactive UI Script
# -----------------------------------------------------------------------------
WIDGET_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>IMD SYNOP SLA Widget</title>
<style>
  :root {
    --bg-glass: rgba(15, 23, 42, 0.88);
    --border-glass: rgba(255, 255, 255, 0.12);
    --text-primary: #F8FAFC;
    --text-secondary: #94A3B8;
    --text-muted: #64748B;
    --accent-emerald: #10B981;
    --accent-amber: #F59E0B;
    --accent-rose: #EF4444;
    --accent-sky: #38BDF8;
    --spring-easing: cubic-bezier(0.16, 1, 0.3, 1);
  }

  * {
    box-sizing: border-box;
    margin: 0;
    padding: 0;
    user-select: none;
    -webkit-user-select: none;
  }

  body {
    background: transparent;
    color: var(--text-primary);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    overflow: hidden;
    height: 100vh;
    padding: 8px;
  }

  .widget-card {
    background: var(--bg-glass);
    border: 1px solid var(--border-glass);
    backdrop-filter: blur(28px) saturate(190%);
    -webkit-backdrop-filter: blur(28px) saturate(190%);
    border-radius: 20px;
    height: 100%;
    display: flex;
    flex-direction: column;
    box-shadow: 0 20px 45px -10px rgba(0, 0, 0, 0.6), 0 0 0 1px rgba(255, 255, 255, 0.08);
    transition: all 0.3s var(--spring-easing);
  }

  /* Header & Draggable Grip */
  .widget-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 10px 14px 8px 14px;
    border-bottom: 1px solid rgba(255, 255, 255, 0.07);
    cursor: grab;
  }

  .widget-header:active {
    cursor: grabbing;
  }

  .title-area {
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .title-icon {
    font-size: 1.15rem;
  }

  .title-text {
    font-size: 0.85rem;
    font-weight: 700;
    letter-spacing: -0.01em;
    color: #FFFFFF;
  }

  .pulse-dot {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background-color: var(--accent-emerald);
    box-shadow: 0 0 8px var(--accent-emerald);
    animation: livePulse 2s infinite var(--spring-easing);
  }

  @keyframes livePulse {
    0%, 100% { opacity: 1; transform: scale(1); }
    50% { opacity: 0.4; transform: scale(0.85); }
  }

  .controls-area {
    display: flex;
    align-items: center;
    gap: 5px;
  }

  .btn-control {
    background: rgba(255, 255, 255, 0.08);
    border: 1px solid rgba(255, 255, 255, 0.1);
    color: var(--text-secondary);
    border-radius: 8px;
    width: 24px;
    height: 24px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 0.72rem;
    cursor: pointer;
    transition: all 0.2s var(--spring-easing);
  }

  .btn-control:hover {
    background: rgba(255, 255, 255, 0.18);
    color: #FFFFFF;
    transform: scale(1.06);
  }

  .btn-control:active {
    transform: scale(0.92);
  }

  .btn-control.active {
    background: rgba(56, 189, 248, 0.25);
    color: var(--accent-sky);
    border-color: rgba(56, 189, 248, 0.4);
  }

  .btn-control.close:hover {
    background: rgba(239, 68, 68, 0.4);
    color: #FFFFFF;
    border-color: rgba(239, 68, 68, 0.6);
  }

  /* Live Clock */
  .clock-section {
    padding: 10px 14px 10px 14px;
    background: rgba(255, 255, 255, 0.02);
    border-bottom: 1px solid rgba(255, 255, 255, 0.06);
  }

  .clock-row {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
  }

  .clock-utc {
    font-family: "SF Mono", Monaco, "Cascadia Code", Consolas, monospace;
    font-size: 1.15rem;
    font-weight: 700;
    color: #FFFFFF;
    letter-spacing: -0.02em;
  }

  .clock-ist {
    font-size: 0.75rem;
    font-weight: 600;
    color: var(--text-secondary);
  }

  /* Station List View */
  .station-list {
    flex: 1;
    overflow-y: auto;
    padding: 6px 10px;
  }

  .station-list::-webkit-scrollbar {
    width: 4px;
  }
  .station-list::-webkit-scrollbar-thumb {
    background: rgba(255, 255, 255, 0.15);
    border-radius: 4px;
  }

  .station-item {
    background: rgba(255, 255, 255, 0.03);
    border: 1px solid rgba(255, 255, 255, 0.05);
    border-radius: 12px;
    padding: 8px 10px;
    margin-bottom: 6px;
    transition: all 0.2s var(--spring-easing);
  }

  .station-item:hover {
    background: rgba(255, 255, 255, 0.07);
    border-color: rgba(255, 255, 255, 0.12);
  }

  .st-top-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 5px;
  }

  .st-name {
    font-size: 0.78rem;
    font-weight: 600;
    color: #FFFFFF;
    display: flex;
    align-items: center;
    gap: 6px;
  }

  .st-code {
    font-family: monospace;
    font-size: 0.72rem;
    color: var(--accent-sky);
    background: rgba(56, 189, 248, 0.12);
    padding: 1px 5px;
    border-radius: 4px;
  }

  .st-badge {
    font-size: 0.62rem;
    font-weight: 700;
    padding: 2px 6px;
    border-radius: 9999px;
  }

  .badge-normal {
    background: rgba(16, 185, 129, 0.15);
    color: #34D399;
    border: 1px solid rgba(16, 185, 129, 0.25);
  }

  .badge-alert {
    background: rgba(239, 68, 68, 0.2);
    color: #F87171;
    border: 1px solid rgba(239, 68, 68, 0.4);
  }

  .slots-row {
    display: flex;
    gap: 3px;
    justify-content: space-between;
  }

  .slot-chip {
    flex: 1;
    text-align: center;
    font-family: "SF Mono", Monaco, monospace;
    font-size: 0.62rem;
    font-weight: 600;
    padding: 3px 0;
    border-radius: 6px;
    transition: transform 0.15s;
  }

  .slot-chip:hover {
    transform: translateY(-1px);
  }

  .chip-on-time { background: #10B981; color: #FFFFFF; }
  .chip-late { background: #F59E0B; color: #FFFFFF; }
  .chip-missing { background: #EF4444; color: #FFFFFF; }
  .chip-early { background: #0284C7; color: #FFFFFF; }
  .chip-awaiting {
    background: rgba(100, 116, 139, 0.15);
    color: #64748B;
    border: 1px dashed rgba(100, 116, 139, 0.35);
  }
  .chip-not-scheduled {
    background: transparent;
    color: #475569;
    border: 1px solid rgba(255, 255, 255, 0.03);
  }

  /* Footer Action Bar */
  .widget-footer {
    padding: 8px 12px;
    border-top: 1px solid rgba(255, 255, 255, 0.07);
    display: flex;
    align-items: center;
    gap: 8px;
    background: rgba(0, 0, 0, 0.15);
    border-bottom-left-radius: 20px;
    border-bottom-right-radius: 20px;
  }

  .btn-dashboard {
    flex: 1;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 6px;
    background: linear-gradient(135deg, #0284C7, #0369A1);
    color: #FFFFFF;
    border: none;
    border-radius: 10px;
    padding: 7px 12px;
    font-size: 0.74rem;
    font-weight: 600;
    cursor: pointer;
    box-shadow: 0 4px 12px rgba(2, 132, 199, 0.3);
    transition: all 0.2s var(--spring-easing);
  }

  .btn-dashboard:hover {
    transform: translateY(-1px);
    box-shadow: 0 6px 16px rgba(2, 132, 199, 0.45);
    background: linear-gradient(135deg, #0ea5e9, #0284C7);
  }

  .btn-dashboard:active {
    transform: scale(0.97);
  }

  .btn-refresh {
    background: rgba(255, 255, 255, 0.08);
    border: 1px solid rgba(255, 255, 255, 0.1);
    color: var(--text-primary);
    border-radius: 10px;
    width: 32px;
    height: 32px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 0.8rem;
    cursor: pointer;
    transition: all 0.2s var(--spring-easing);
  }

  .btn-refresh:hover {
    background: rgba(255, 255, 255, 0.16);
    transform: scale(1.06);
  }

  .btn-refresh:active {
    transform: scale(0.92);
  }

  .rotating {
    animation: spin 0.8s linear infinite;
  }

  @keyframes spin {
    100% { transform: rotate(360deg); }
  }

  /* Compact Mode Adjustments */
  body.compact-mode .station-list,
  body.compact-mode .widget-footer {
    display: none !important;
  }

  body.compact-mode .widget-card {
    height: 100%;
    border-radius: 16px;
  }
</style>
</head>
<body>

<div class="widget-card">
  <!-- Draggable Header -->
  <div class="widget-header pywebview-drag-region">
    <div class="title-area">
      <span class="title-icon">🌤️</span>
      <span class="title-text">IMD SYNOP SLA</span>
      <span class="pulse-dot" title="Live Synoptic Monitor Active"></span>
    </div>
    <div class="controls-area">
      <button class="btn-control active" id="btnPin" title="Toggle Always on Top" onclick="togglePin()">📌</button>
      <button class="btn-control" id="btnCompact" title="Toggle Compact / Full View" onclick="toggleCompact()">🗕</button>
      <button class="btn-control close" title="Close Widget" onclick="closeWidget()">✕</button>
    </div>
  </div>

  <!-- Live Dual Clocks -->
  <div class="clock-section">
    <div class="clock-row">
      <span class="clock-utc" id="clockUtc">--:--:-- UTC</span>
      <span class="clock-ist" id="clockIst">--:--:-- IST</span>
    </div>
  </div>

  <!-- Station Observation Matrix -->
  <div class="station-list" id="stationList">
    <!-- Populated dynamically via JS -->
    <div style="text-align: center; color: var(--text-muted); padding: 30px; font-size: 0.75rem;">
      Ingesting bulletins...
    </div>
  </div>

  <!-- Footer Actions -->
  <div class="widget-footer">
    <button class="btn-dashboard" onclick="openDashboard()">
      <span>📊</span>
      <span>Open Full Dashboard</span>
    </button>
    <button class="btn-refresh" id="btnRefresh" title="Refresh Now" onclick="triggerRefresh()">
      🔄
    </button>
  </div>
</div>

<script>
  let isPinned = true;
  let isCompact = false;
  let lastData = null;

  // Realtime clock ticks every second
  function updateClocks() {
    const now = new Date();
    const utcHours = String(now.getUTCHours()).padStart(2, '0');
    const utcMins = String(now.getUTCMinutes()).padStart(2, '0');
    const utcSecs = String(now.getUTCSeconds()).padStart(2, '0');
    document.getElementById('clockUtc').innerText = `${utcHours}:${utcMins}:${utcSecs} UTC`;

    // IST is UTC + 5h30m
    const istTime = new Date(now.getTime() + (5.5 * 60 * 60 * 1000));
    const istHours = String(istTime.getUTCHours()).padStart(2, '0');
    const istMins = String(istTime.getUTCMinutes()).padStart(2, '0');
    const istSecs = String(istTime.getUTCSeconds()).padStart(2, '0');
    document.getElementById('clockIst').innerText = `${istHours}:${istMins}:${istSecs} IST`;
  }
  setInterval(updateClocks, 1000);
  updateClocks();

  // Render station observations
  function renderData(data) {
    if (!data || !data.success) return;
    lastData = data;

    // Station list
    const listEl = document.getElementById('stationList');
    if (!data.stations || data.stations.length === 0) {
      listEl.innerHTML = '<div style="text-align: center; color: var(--text-muted); padding: 20px; font-size: 0.75rem;">No station data available.</div>';
      return;
    }

    let html = '';
    data.stations.forEach(st => {
      const isNormal = st.overall_status === 'NORMAL' || st.overall_status === 'ALL_NORMAL';
      const badgeCls = isNormal ? 'badge-normal' : 'badge-alert';
      const badgeText = isNormal ? 'ALL NORMAL' : st.overall_status.replace(/_/g, ' ');

      let slotsHtml = '';
      (st.slots || []).forEach(slot => {
        let chipCls = 'chip-awaiting';
        if (slot.status === 'ON_TIME') chipCls = 'chip-on-time';
        else if (slot.status === 'LATE') chipCls = 'chip-late';
        else if (slot.status === 'MISSING') chipCls = 'chip-missing';
        else if (slot.status === 'EARLY') chipCls = 'chip-early';
        else if (slot.status === 'NOT_SCHEDULED') chipCls = 'chip-not-scheduled';

        slotsHtml += `<div class="slot-chip ${chipCls}" title="${slot.hour.slice(0,2)}Z: ${slot.badge_text}">${slot.label}</div>`;
      });

      html += `
        <div class="station-item">
          <div class="st-top-row">
            <span class="st-name">
              <span class="st-code">${st.id}</span>
              <span>${st.name}</span>
            </span>
            <span class="st-badge ${badgeCls}">${badgeText}</span>
          </div>
          <div class="slots-row">
            ${slotsHtml}
          </div>
        </div>
      `;
    });

    listEl.innerHTML = html;
  }

  // Python API calls
  async function loadData() {
    if (window.pywebview && window.pywebview.api) {
      try {
        const raw = await window.pywebview.api.get_data();
        const data = JSON.parse(raw);
        renderData(data);
      } catch (e) {
        console.error('Failed to load data:', e);
      }
    }
  }

  async function triggerRefresh() {
    const btn = document.getElementById('btnRefresh');
    btn.classList.add('rotating');
    if (window.pywebview && window.pywebview.api) {
      try {
        const raw = await window.pywebview.api.refresh_now();
        const data = JSON.parse(raw);
        renderData(data);
      } catch (e) {
        console.error('Refresh error:', e);
      }
    }
    setTimeout(() => btn.classList.remove('rotating'), 800);
  }

  async function togglePin() {
    if (window.pywebview && window.pywebview.api) {
      isPinned = await window.pywebview.api.toggle_pin();
      const btn = document.getElementById('btnPin');
      if (isPinned) {
        btn.classList.add('active');
        btn.innerText = '📌';
      } else {
        btn.classList.remove('active');
        btn.innerText = '📍';
      }
    }
  }

  async function toggleCompact() {
    if (window.pywebview && window.pywebview.api) {
      isCompact = await window.pywebview.api.toggle_compact();
      document.body.classList.toggle('compact-mode', isCompact);
      const btn = document.getElementById('btnCompact');
      btn.innerText = isCompact ? '🗖' : '🗕';
    }
  }

  function openDashboard() {
    if (window.pywebview && window.pywebview.api) {
      window.pywebview.api.open_dashboard();
    }
  }

  function closeWidget() {
    if (window.pywebview && window.pywebview.api) {
      window.pywebview.api.close();
    }
  }

  // Periodic poll every 60s
  setInterval(loadData, 60000);

  // Initialize once pywebview is ready
  window.addEventListener('pywebviewready', () => {
    loadData();
  });
</script>

</body>
</html>
"""


def main():
    global _widget_window
    api = WidgetAPI()
    screen_width, screen_height = 1920, 1080
    if webview.screens:
        primary = webview.screens[0]
        screen_width, screen_height = primary.width, primary.height

    # Position in the bottom-right corner, 20px margin from screen edges
    widget_w = 370
    widget_h = 420
    pos_x = max(20, screen_width - widget_w - 24)
    pos_y = max(20, screen_height - widget_h - 54)

    _widget_window = webview.create_window(
        title="IMD SYNOP SLA Widget",
        html=WIDGET_HTML,
        js_api=api,
        width=widget_w,
        height=widget_h,
        x=pos_x,
        y=pos_y,
        resizable=True,
        frameless=True,
        easy_drag=True,
        shadow=True,
        on_top=True,
        transparent=True,
        background_color="#0F172A",
    )
    webview.start(debug=False)


if __name__ == "__main__":
    main()
