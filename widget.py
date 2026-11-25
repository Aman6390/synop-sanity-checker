"""
IMD SYNOP Monitor & SLA Sanity Checker - Windows 10/11 Desktop Floating Widget
Apple Design System styled, frameless, translucent, always-on-top desktop mini-widget.
Features:
- Zero-scroll 12-station matrix with instant synoptic cycle status
- Interactive station drill-down with reverse-chronological synop feeds
- Realtime late synop audio/visual alert system
- Glass opacity level changer preserving frosted acrylic blur
- Configurable scan timing intervals (30s, 1m, 2m, 5m, 10m)
- Station list re-structuring and persistent reordering
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

# Ensure backend directory is in path and support PyInstaller frozen bundles
if getattr(sys, "frozen", False):
    BUNDLE_DIR = sys._MEIPASS
    EXE_DIR = os.path.dirname(sys.executable)
else:
    BUNDLE_DIR = os.path.dirname(os.path.abspath(__file__))
    EXE_DIR = BUNDLE_DIR

BASE_DIR = BUNDLE_DIR
BACKEND_DIR = os.path.join(BUNDLE_DIR, "backend")
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

DEFAULT_CONFIG_PATH = os.path.join(BACKEND_DIR, "stations_config.json")


def get_user_config_path() -> str:
    app_data = os.environ.get("APPDATA")
    if app_data:
        user_dir = os.path.join(app_data, "IMD_SYNOP")
        try:
            os.makedirs(user_dir, exist_ok=True)
            return os.path.join(user_dir, "stations_config.json")
        except Exception:
            pass
    return os.path.join(EXE_DIR, "stations_config.json")


def get_dump_path() -> str:
    exe_dump = os.path.join(EXE_DIR, "sendata_dump.txt")
    if os.path.exists(exe_dump):
        return exe_dump
    return os.path.join(BUNDLE_DIR, "sendata_dump.txt")


CONFIG_PATH = get_user_config_path()
DUMP_PATH = get_dump_path()

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
        target_path = CONFIG_PATH if os.path.exists(CONFIG_PATH) else DEFAULT_CONFIG_PATH
        if os.path.exists(target_path):
            try:
                with open(target_path, "r", encoding="utf-8") as f:
                    return json.load(f).get("stations", [])
            except Exception as e:
                logger.error(f"Error loading stations config from {target_path}: {e}")
        if target_path != DEFAULT_CONFIG_PATH and os.path.exists(DEFAULT_CONFIG_PATH):
            try:
                with open(DEFAULT_CONFIG_PATH, "r", encoding="utf-8") as f:
                    return json.load(f).get("stations", [])
            except Exception as e:
                logger.error(f"Error loading fallback stations config: {e}")
        return []

    def reorder_stations(self, new_order_ids: List[str]) -> bool:
        stations = self.load_stations_config()
        st_map = {str(s["id"]): s for s in stations}
        reordered = []
        for sid in new_order_ids:
            sid_str = str(sid)
            if sid_str in st_map:
                reordered.append(st_map[sid_str])
        for s in stations:
            if s not in reordered:
                reordered.append(s)
        try:
            target_path = get_user_config_path()
            os.makedirs(os.path.dirname(target_path), exist_ok=True)
            with open(target_path, "w", encoding="utf-8") as f:
                json.dump({"stations": reordered}, f, indent=2)
            logger.info(f"Successfully persisted reordered stations to {target_path}.")
            return True
        except Exception as e:
            logger.error(f"Error saving reordered stations: {e}")
            return False

    def fetch_and_evaluate(self) -> Dict[str, Any]:
        raw_text = None
        source = "AMSS Delhi Live"
        try:
            raw_text = self.fetcher.fetch_live_data()
        except Exception as e:
            logger.warning(f"Live fetch failed ({e}), falling back to local dump...")
            dump_file = get_dump_path()
            if os.path.exists(dump_file):
                with open(dump_file, "r", encoding="utf-8", errors="ignore") as f:
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
            late_alerts = []

            for st_cfg in stations:
                st_id = st_cfg["id"]
                st_synops = parsed["synops_by_station"].get(st_id, [])
                eval_res = SLAEngine.evaluate_station_timeliness(st_cfg, st_synops, now_utc)

                # Format slots for widget display
                slots_data = []
                for h in SYNOPTIC_HOURS:
                    slot = eval_res["slots"].get(h, {})
                    slot_status = slot.get("status", "NOT_SCHEDULED")
                    badge_text = slot.get("badge_text", "-")
                    
                    # Capture late / missing alerts
                    if slot_status in ("LATE", "VERY_LATE", "MISSING"):
                        late_alerts.append({
                            "station_id": st_id,
                            "station_name": st_cfg.get("name", st_id),
                            "hour": h,
                            "status": slot_status,
                            "badge_text": badge_text
                        })

                    # Format primary and all reports for drill-down
                    reports_list = []
                    for r in slot.get("reports", []):
                        reports_list.append({
                            "raw_text": r.get("raw_text", ""),
                            "timestamp": r.get("timestamp_str", ""),
                            "seq": r.get("bulletin_seq", ""),
                            "origin": r.get("bulletin_origin", ""),
                            "bulletin": r.get("bulletin_type", ""),
                            "is_primary": r.get("is_primary", False)
                        })

                    slots_data.append({
                        "hour": h,
                        "label": f"{h[:2]}Z",
                        "status": slot_status,
                        "severity": slot.get("severity", "muted"),
                        "badge_text": badge_text,
                        "received": slot.get("received", False),
                        "transmission_count": slot.get("transmission_count", 0),
                        "duplicate_type": slot.get("duplicate_type", "NONE"),
                        "duplicate_badge": slot.get("duplicate_badge", ""),
                        "delta_minutes": slot.get("delta_minutes"),
                        "raw_synop": slot.get("authoritative_synop", {}).get("raw_text", "") or (slot.get("primary_report", {}) or {}).get("raw_text", ""),
                        "reports": reports_list
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
                "late_alerts": late_alerts,
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
            "late_alerts": [],
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
        hwnd = windll.user32.FindWindowW(None, "IMD SYNOP SLA Widget")
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
        self.full_height: int = 470
        self.compact_height: int = 70
        self.width: int = 350

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

    def reorder_stations(self, new_order_ids_json: str) -> bool:
        """Saves a restructured station list order to stations_config.json."""
        try:
            order_ids = json.loads(new_order_ids_json)
            return backend_instance.reorder_stations(order_ids)
        except Exception as e:
            logger.error(f"Error in reorder_stations: {e}")
            return False

    def toggle_pin(self) -> bool:
        """Toggles always-on-top behavior asynchronously without blocking the UI thread."""
        self.is_pinned = not self.is_pinned
        hwnd = get_widget_hwnd()
        if hwnd:
            try:
                target = HWND_TOPMOST if self.is_pinned else HWND_NOTOPMOST
                flags = SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_ASYNCWINDOWPOS
                threading.Thread(
                    target=windll.user32.SetWindowPos,
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
                flags = SWP_NOMOVE | SWP_NOZORDER | SWP_NOACTIVATE | SWP_ASYNCWINDOWPOS
                threading.Thread(
                    target=windll.user32.SetWindowPos,
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
            py_exec = "python" if getattr(sys, "frozen", False) else sys.executable
            app_script = os.path.join(EXE_DIR, "streamlit_app.py")
            if not os.path.exists(app_script):
                app_script = os.path.join(BASE_DIR, "streamlit_app.py")

            if os.path.exists(app_script):
                logger.info("Streamlit server not detected on port 8501. Launching in background...")
                try:
                    cmd = [py_exec, "-m", "streamlit", "run", app_script, "--server.port", str(streamlit_port), "--server.headless", "true"]
                    subprocess.Popen(cmd, cwd=EXE_DIR, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
                except Exception as e:
                    logger.warning(f"Could not launch streamlit subprocess: {e}")

        webbrowser.open(url)
        return "opened"

    def minimize(self) -> None:
        hwnd = get_widget_hwnd()
        if hwnd:
            try:
                threading.Thread(
                    target=windll.user32.ShowWindow,
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
    --bg-glass-alpha: 0.88;
    --bg-glass: rgba(15, 23, 42, var(--bg-glass-alpha));
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
    padding: 6px;
  }

  .widget-card {
    background: var(--bg-glass);
    border: 1px solid var(--border-glass);
    backdrop-filter: blur(28px) saturate(190%);
    -webkit-backdrop-filter: blur(28px) saturate(190%);
    border-radius: 18px;
    height: 100%;
    display: flex;
    flex-direction: column;
    box-shadow: 0 20px 45px -10px rgba(0, 0, 0, 0.65), 0 0 0 1px rgba(255, 255, 255, 0.08);
    transition: background 0.15s ease, border-radius 0.25s var(--spring-easing);
    position: relative;
    overflow: hidden;
  }

  /* Header & Draggable Region */
  .widget-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 8px 10px 6px 10px;
    border-bottom: 1px solid rgba(255, 255, 255, 0.07);
    cursor: grab;
  }

  .widget-header:active {
    cursor: grabbing;
  }

  .title-area {
    display: flex;
    align-items: center;
    gap: 6px;
  }

  .title-icon { font-size: 1.05rem; }

  .title-text {
    font-size: 0.82rem;
    font-weight: 700;
    letter-spacing: -0.01em;
    color: #FFFFFF;
  }

  .pulse-dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background-color: var(--accent-emerald);
    box-shadow: 0 0 6px var(--accent-emerald);
    animation: livePulse 2s infinite var(--spring-easing);
  }

  @keyframes livePulse {
    0%, 100% { opacity: 1; transform: scale(1); }
    50% { opacity: 0.4; transform: scale(0.85); }
  }

  .controls-area {
    display: flex;
    align-items: center;
    gap: 4px;
  }

  .btn-control {
    background: rgba(255, 255, 255, 0.08);
    border: 1px solid rgba(255, 255, 255, 0.1);
    color: var(--text-secondary);
    border-radius: 6px;
    width: 22px;
    height: 22px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 0.68rem;
    cursor: pointer;
    transition: all 0.15s var(--spring-easing);
  }

  .btn-control:hover {
    background: rgba(255, 255, 255, 0.18);
    color: #FFFFFF;
    transform: scale(1.08);
  }

  .btn-control:active {
    transform: scale(0.92);
  }

  .btn-control.active {
    background: rgba(56, 189, 248, 0.25);
    color: var(--accent-sky);
    border-color: rgba(56, 189, 248, 0.4);
  }

  .btn-control.alert-on {
    background: rgba(245, 158, 11, 0.25);
    color: var(--accent-amber);
    border-color: rgba(245, 158, 11, 0.4);
  }

  .btn-control.close:hover {
    background: rgba(239, 68, 68, 0.4);
    color: #FFFFFF;
    border-color: rgba(239, 68, 68, 0.6);
  }

  /* Live Clock & Scan Status Bar */
  .clock-section {
    padding: 6px 10px 5px 10px;
    background: rgba(255, 255, 255, 0.02);
    border-bottom: 1px solid rgba(255, 255, 255, 0.06);
    display: flex;
    align-items: baseline;
    justify-content: space-between;
  }

  .clock-utc {
    font-family: "SF Mono", Monaco, "Cascadia Code", monospace;
    font-size: 1.05rem;
    font-weight: 700;
    color: #FFFFFF;
    letter-spacing: -0.02em;
  }

  .clock-right {
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .clock-ist {
    font-size: 0.72rem;
    font-weight: 600;
    color: var(--text-secondary);
  }

  .scan-pill {
    font-size: 0.60rem;
    font-family: monospace;
    color: var(--accent-sky);
    background: rgba(56, 189, 248, 0.12);
    padding: 1px 5px;
    border-radius: 4px;
    border: 1px solid rgba(56, 189, 248, 0.2);
  }

  /* Active Alert Banner */
  .alert-banner {
    display: none;
    background: linear-gradient(90deg, rgba(239, 68, 68, 0.3), rgba(245, 158, 11, 0.25));
    border-bottom: 1px solid rgba(239, 68, 68, 0.4);
    padding: 4px 10px;
    font-size: 0.68rem;
    font-weight: 600;
    color: #FECACA;
    cursor: pointer;
    align-items: center;
    justify-content: space-between;
    animation: alertGlow 1.5s infinite alternate;
  }

  .alert-banner.show {
    display: flex;
  }

  @keyframes alertGlow {
    from { background-color: rgba(239, 68, 68, 0.2); }
    to { background-color: rgba(239, 68, 68, 0.4); }
  }

  /* Matrix Column Header */
  .matrix-header {
    display: flex;
    align-items: center;
    padding: 4px 10px 3px 10px;
    background: rgba(0, 0, 0, 0.2);
    border-bottom: 1px solid rgba(255, 255, 255, 0.06);
    font-size: 0.58rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    color: var(--text-muted);
  }

  .col-st-title {
    width: 118px;
    display: flex;
    align-items: center;
    gap: 4px;
  }

  .col-cycles-header {
    flex: 1;
    display: flex;
    justify-content: space-between;
    padding-right: 2px;
  }

  .cycle-col-name {
    width: 20px;
    text-align: center;
    font-family: monospace;
    font-size: 0.60rem;
  }

  /* View Container (Matrix, Drilldown, Settings) */
  .view-panel {
    flex: 1;
    display: flex;
    flex-direction: column;
    overflow: hidden;
    position: relative;
  }

  /* Matrix Station Rows (Zero Scrolling, Super Compact) */
  .matrix-body {
    flex: 1;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
    padding: 3px 6px;
    overflow: hidden;
  }

  .station-row {
    display: flex;
    align-items: center;
    padding: 3px 6px;
    border-radius: 6px;
    background: rgba(255, 255, 255, 0.02);
    border: 1px solid transparent;
    cursor: pointer;
    transition: all 0.12s var(--spring-easing);
  }

  .station-row:hover {
    background: rgba(255, 255, 255, 0.08);
    border-color: rgba(255, 255, 255, 0.14);
    transform: translateX(2px);
  }

  .station-row.has-alert {
    border-color: rgba(239, 68, 68, 0.4);
    background: rgba(239, 68, 68, 0.08);
  }

  .st-info {
    width: 114px;
    display: flex;
    align-items: center;
    gap: 5px;
    white-space: nowrap;
    overflow: hidden;
  }

  .st-code {
    font-family: monospace;
    font-size: 0.65rem;
    font-weight: 600;
    color: var(--accent-sky);
    background: rgba(56, 189, 248, 0.12);
    padding: 1px 3px;
    border-radius: 3px;
    line-height: 1.1;
  }

  .st-name {
    font-size: 0.70rem;
    font-weight: 600;
    color: #FFFFFF;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .cycles-cells {
    flex: 1;
    display: flex;
    justify-content: space-between;
    align-items: center;
  }

  .cell-pill {
    width: 20px;
    height: 17px;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: 4px;
    font-family: "SF Mono", Monaco, monospace;
    font-size: 0.55rem;
    font-weight: 700;
    transition: transform 0.1s;
  }

  .cell-pill:hover {
    transform: scale(1.2);
    z-index: 2;
  }

  .cell-on-time {
    background: #10B981;
    color: #FFFFFF;
    box-shadow: 0 0 5px rgba(16, 185, 129, 0.35);
  }

  .cell-late {
    background: #F59E0B;
    color: #FFFFFF;
    box-shadow: 0 0 6px rgba(245, 158, 11, 0.4);
  }

  .cell-missing {
    background: #EF4444;
    color: #FFFFFF;
    box-shadow: 0 0 6px rgba(239, 68, 68, 0.5);
  }

  .cell-early {
    background: #0284C7;
    color: #FFFFFF;
  }

  .cell-awaiting {
    background: rgba(100, 116, 139, 0.15);
    color: #64748B;
    border: 1px dashed rgba(100, 116, 139, 0.35);
  }

  .cell-not-scheduled {
    background: transparent;
    color: #334155;
    border: 1px solid rgba(255, 255, 255, 0.04);
  }

  .row-chevron {
    color: var(--text-muted);
    font-size: 0.60rem;
    margin-left: 3px;
    opacity: 0.4;
  }

  .station-row:hover .row-chevron {
    opacity: 1;
    color: var(--accent-sky);
  }

  /* Footer Action Bar */
  .widget-footer {
    padding: 6px 10px;
    border-top: 1px solid rgba(255, 255, 255, 0.07);
    display: flex;
    align-items: center;
    justify-content: space-between;
    background: rgba(0, 0, 0, 0.2);
  }

  .btn-dashboard {
    flex: 1;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 5px;
    background: linear-gradient(135deg, #0284C7, #0369A1);
    color: #FFFFFF;
    border: none;
    border-radius: 7px;
    padding: 5px 10px;
    font-size: 0.70rem;
    font-weight: 600;
    cursor: pointer;
    box-shadow: 0 3px 10px rgba(2, 132, 199, 0.3);
    transition: all 0.15s var(--spring-easing);
  }

  .btn-dashboard:hover {
    transform: translateY(-1px);
    box-shadow: 0 4px 14px rgba(2, 132, 199, 0.45);
  }

  .btn-refresh {
    background: rgba(255, 255, 255, 0.08);
    border: 1px solid rgba(255, 255, 255, 0.1);
    color: var(--text-primary);
    border-radius: 7px;
    width: 26px;
    height: 26px;
    margin-left: 6px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 0.74rem;
    cursor: pointer;
    transition: all 0.15s;
  }

  .btn-refresh:hover {
    background: rgba(255, 255, 255, 0.18);
  }

  .rotating {
    animation: spin 0.8s linear infinite;
  }

  @keyframes spin { 100% { transform: rotate(360deg); } }

  /* --------------------------------------------------------------------------
     DRILL-DOWN VIEW (Station Synop Feed)
     -------------------------------------------------------------------------- */
  .drilldown-view {
    display: none;
    flex-direction: column;
    height: 100%;
    background: transparent;
  }

  .drilldown-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 8px 10px;
    background: rgba(255, 255, 255, 0.02);
    border-bottom: 1px solid rgba(255, 255, 255, 0.07);
  }

  .btn-back {
    display: flex;
    align-items: center;
    gap: 3px;
    background: rgba(56, 189, 248, 0.12);
    border: 1px solid rgba(56, 189, 248, 0.25);
    color: var(--accent-sky);
    border-radius: 6px;
    padding: 3px 6px;
    font-size: 0.68rem;
    font-weight: 600;
    cursor: pointer;
  }

  .btn-back:hover {
    background: rgba(56, 189, 248, 0.22);
  }

  .drilldown-title {
    font-size: 0.78rem;
    font-weight: 700;
    color: #FFFFFF;
    display: flex;
    align-items: center;
    gap: 5px;
  }

  .drilldown-feed {
    flex: 1;
    overflow-y: auto;
    padding: 6px 8px;
    display: flex;
    flex-direction: column;
    gap: 6px;
  }

  .drilldown-feed::-webkit-scrollbar { width: 4px; }
  .drilldown-feed::-webkit-scrollbar-thumb {
    background: rgba(255, 255, 255, 0.15);
    border-radius: 4px;
  }

  .feed-card {
    background: rgba(255, 255, 255, 0.04);
    border: 1px solid rgba(255, 255, 255, 0.07);
    border-radius: 10px;
    padding: 7px 8px;
    transition: all 0.15s;
  }

  .feed-card:hover {
    background: rgba(255, 255, 255, 0.07);
    border-color: rgba(255, 255, 255, 0.12);
  }

  .feed-card-top {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 3px;
  }

  .feed-obs-time {
    display: flex;
    align-items: center;
    gap: 5px;
    font-size: 0.70rem;
    font-weight: 600;
    color: #FFFFFF;
  }

  .feed-hour-chip {
    background: #10B981;
    color: #FFFFFF;
    font-family: monospace;
    font-size: 0.60rem;
    font-weight: 700;
    padding: 1px 4px;
    border-radius: 4px;
  }

  .feed-status-badge {
    font-size: 0.58rem;
    font-weight: 700;
    padding: 1px 5px;
    border-radius: 9999px;
  }

  .badge-on-time { background: rgba(16, 185, 129, 0.15); color: #34D399; border: 1px solid rgba(16, 185, 129, 0.3); }
  .badge-late { background: rgba(245, 158, 11, 0.2); color: #FBBF24; border: 1px solid rgba(245, 158, 11, 0.4); }
  .badge-missing { background: rgba(239, 68, 68, 0.2); color: #F87171; border: 1px solid rgba(239, 68, 68, 0.4); }
  .badge-awaiting { background: rgba(100, 116, 139, 0.2); color: #94A3B8; }

  .feed-meta-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    font-size: 0.60rem;
    color: var(--text-muted);
    margin-bottom: 4px;
  }

  .feed-raw-text {
    background: rgba(0, 0, 0, 0.4);
    border: 1px solid rgba(255, 255, 255, 0.05);
    border-radius: 5px;
    padding: 4px 6px;
    font-family: "SF Mono", Monaco, "Cascadia Code", monospace;
    font-size: 0.64rem;
    color: #E2E8F0;
    word-break: break-all;
    line-height: 1.3;
  }

  /* --------------------------------------------------------------------------
     SETTINGS OVERLAY VIEW
     -------------------------------------------------------------------------- */
  .settings-view {
    display: none;
    flex-direction: column;
    height: 100%;
    padding: 10px;
    overflow-y: auto;
    background: rgba(15, 23, 42, 0.95);
  }

  .settings-view::-webkit-scrollbar { width: 4px; }
  .settings-view::-webkit-scrollbar-thumb { background: rgba(255, 255, 255, 0.15); border-radius: 4px; }

  .settings-top {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 10px;
    padding-bottom: 6px;
    border-bottom: 1px solid rgba(255, 255, 255, 0.1);
  }

  .settings-heading {
    font-size: 0.85rem;
    font-weight: 700;
    color: #FFFFFF;
    display: flex;
    align-items: center;
    gap: 6px;
  }

  .btn-done {
    background: rgba(56, 189, 248, 0.2);
    border: 1px solid rgba(56, 189, 248, 0.35);
    color: var(--accent-sky);
    border-radius: 6px;
    padding: 3px 10px;
    font-size: 0.70rem;
    font-weight: 600;
    cursor: pointer;
  }

  .setting-group {
    background: rgba(255, 255, 255, 0.03);
    border: 1px solid rgba(255, 255, 255, 0.06);
    border-radius: 10px;
    padding: 8px 10px;
    margin-bottom: 8px;
  }

  .setting-label-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    font-size: 0.70rem;
    font-weight: 600;
    color: #FFFFFF;
    margin-bottom: 6px;
  }

  .setting-val-tag {
    color: var(--accent-sky);
    font-family: monospace;
    font-size: 0.68rem;
  }

  .opacity-slider {
    width: 100%;
    accent-color: #38BDF8;
    cursor: pointer;
  }

  .timing-buttons {
    display: flex;
    gap: 4px;
    justify-content: space-between;
  }

  .btn-timing {
    flex: 1;
    background: rgba(255, 255, 255, 0.06);
    border: 1px solid rgba(255, 255, 255, 0.08);
    color: var(--text-secondary);
    border-radius: 6px;
    padding: 4px 0;
    font-size: 0.64rem;
    font-weight: 600;
    cursor: pointer;
    text-align: center;
  }

  .btn-timing:hover { background: rgba(255, 255, 255, 0.12); color: #FFFFFF; }
  .btn-timing.active {
    background: rgba(56, 189, 248, 0.25);
    border-color: rgba(56, 189, 248, 0.45);
    color: var(--accent-sky);
  }

  .sort-actions {
    display: flex;
    gap: 4px;
    margin-bottom: 6px;
  }

  .btn-sort {
    flex: 1;
    background: rgba(255, 255, 255, 0.05);
    border: 1px solid rgba(255, 255, 255, 0.08);
    color: var(--text-secondary);
    border-radius: 5px;
    padding: 3px 0;
    font-size: 0.60rem;
    font-weight: 600;
    cursor: pointer;
    text-align: center;
  }

  .btn-sort:hover { background: rgba(255, 255, 255, 0.12); color: #FFFFFF; }

  .reorder-list {
    max-height: 120px;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
    gap: 3px;
    padding-right: 2px;
  }

  .reorder-item {
    display: flex;
    align-items: center;
    justify-content: space-between;
    background: rgba(0, 0, 0, 0.25);
    border: 1px solid rgba(255, 255, 255, 0.04);
    border-radius: 5px;
    padding: 2px 6px;
    font-size: 0.65rem;
  }

  .reorder-btns {
    display: flex;
    gap: 3px;
  }

  .btn-shift {
    background: rgba(255, 255, 255, 0.08);
    border: none;
    color: #FFFFFF;
    border-radius: 3px;
    width: 16px;
    height: 16px;
    font-size: 0.55rem;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .btn-shift:hover { background: rgba(56, 189, 248, 0.3); }

  .btn-save-order {
    width: 100%;
    margin-top: 6px;
    background: linear-gradient(135deg, #10B981, #059669);
    color: #FFFFFF;
    border: none;
    border-radius: 6px;
    padding: 5px;
    font-size: 0.68rem;
    font-weight: 600;
    cursor: pointer;
  }

  /* Compact Mode Adjustments */
  body.compact-mode .matrix-header,
  body.compact-mode .matrix-body,
  body.compact-mode .widget-footer,
  body.compact-mode .alert-banner {
    display: none !important;
  }

  body.compact-mode .widget-card {
    height: 100%;
    border-radius: 14px;
  }
</style>
</head>
<body>

<div class="widget-card" id="widgetCard">
  <!-- Draggable Header -->
  <div class="widget-header pywebview-drag-region">
    <div class="title-area">
      <span class="title-icon">🌤️</span>
      <span class="title-text">IMD SYNOP</span>
      <span class="pulse-dot" title="Live Observation Active"></span>
    </div>
    <div class="controls-area">
      <button class="btn-control alert-on" id="btnSound" title="Toggle Late Synop Audio Alert" onclick="toggleSound()">🔔</button>
      <button class="btn-control" id="btnSettings" title="Widget Settings (Opacity, Scan, Ordering)" onclick="openSettings()">⚙️</button>
      <button class="btn-control active" id="btnPin" title="Toggle Always on Top" onclick="togglePin()">📌</button>
      <button class="btn-control" id="btnCompact" title="Toggle Compact Glance" onclick="toggleCompact()">🗕</button>
      <button class="btn-control close" title="Close Widget" onclick="closeWidget()">✕</button>
    </div>
  </div>

  <!-- Clock & Scan Status Bar -->
  <div class="clock-section">
    <span class="clock-utc" id="clockUtc">--:--:-- UTC</span>
    <div class="clock-right">
      <span class="clock-ist" id="clockIst">--:--:-- IST</span>
      <span class="scan-pill" id="scanCountdown" title="Current Scan Timing">Scan: 1m</span>
    </div>
  </div>

  <!-- Alert Banner (shown when a station sends late synop) -->
  <div class="alert-banner" id="alertBanner" onclick="onAlertBannerClick()">
    <span id="alertBannerText">⚠️ Late Synop Detected</span>
    <span>Inspect ›</span>
  </div>

  <!-- 1. ZERO-SCROLL MATRIX VIEW -->
  <div class="view-panel" id="viewMatrix">
    <div class="matrix-header">
      <span class="col-st-title">Station (12)</span>
      <div class="col-cycles-header">
        <span class="cycle-col-name">00</span>
        <span class="cycle-col-name">03</span>
        <span class="cycle-col-name">06</span>
        <span class="cycle-col-name">09</span>
        <span class="cycle-col-name">12</span>
        <span class="cycle-col-name">15</span>
        <span class="cycle-col-name">18</span>
        <span class="cycle-col-name">21</span>
      </div>
    </div>
    <div class="matrix-body" id="matrixRows">
      <div style="text-align: center; color: var(--text-muted); padding: 40px; font-size: 0.75rem;">
        Ingesting bulletins...
      </div>
    </div>
    <div class="widget-footer">
      <button class="btn-dashboard" onclick="openDashboard()">
        <span>📊</span>
        <span>Open Web Dashboard</span>
      </button>
      <button class="btn-refresh" id="btnRefresh" title="Refresh Now" onclick="triggerRefresh()">🔄</button>
    </div>
  </div>

  <!-- 2. STATION DRILL-DOWN VIEW (Reverse Chronological Synop Feed) -->
  <div class="view-panel drilldown-view" id="viewDrilldown">
    <div class="drilldown-header">
      <button class="btn-back" onclick="closeDrilldown()">‹ All Stations</button>
      <div class="drilldown-title">
        <span id="ddStCode">42027</span>
        <span id="ddStName">Srinagar</span>
      </div>
      <span class="feed-status-badge badge-on-time" id="ddStBadge">ALL NORMAL</span>
    </div>
    <div class="drilldown-feed" id="drilldownFeed"></div>
    <div class="widget-footer">
      <button class="btn-dashboard" onclick="copyLatestSynop()">
        <span>📋</span>
        <span>Copy Latest AAXX</span>
      </button>
      <button class="btn-refresh" title="Refresh Station" onclick="triggerRefresh()">🔄</button>
    </div>
  </div>

  <!-- 3. SETTINGS OVERLAY VIEW (Opacity, Scan Interval, Re-ordering) -->
  <div class="view-panel settings-view" id="viewSettings">
    <div class="settings-top">
      <span class="settings-heading">⚙️ Widget Preferences</span>
      <button class="btn-done" onclick="closeSettings()">‹ Done</button>
    </div>

    <!-- Opacity Level Changer -->
    <div class="setting-group">
      <div class="setting-label-row">
        <span>Glass Opacity</span>
        <span class="setting-val-tag" id="opacityVal">88%</span>
      </div>
      <input type="range" class="opacity-slider" id="opacitySlider" min="30" max="100" value="88" oninput="changeOpacity(this.value)">
    </div>

    <!-- Scan Timing Changer -->
    <div class="setting-group">
      <div class="setting-label-row">
        <span>Scan Frequency</span>
        <span class="setting-val-tag" id="timingVal">1m</span>
      </div>
      <div class="timing-buttons">
        <div class="btn-timing" onclick="changeScanTiming(30, '30s')">30s</div>
        <div class="btn-timing active" onclick="changeScanTiming(60, '1m')">1m</div>
        <div class="btn-timing" onclick="changeScanTiming(120, '2m')">2m</div>
        <div class="btn-timing" onclick="changeScanTiming(300, '5m')">5m</div>
        <div class="btn-timing" onclick="changeScanTiming(600, '10m')">10m</div>
      </div>
    </div>

    <!-- Sound Alert Setting -->
    <div class="setting-group">
      <div class="setting-label-row">
        <span>Late Synop Chime</span>
        <button class="btn-back" style="font-size: 0.60rem; padding: 1px 6px;" onclick="testAlertSound()">🔊 Test Sound</button>
      </div>
      <div style="font-size: 0.65rem; color: var(--text-muted);">
        Plays an acoustic notification when a station is detected late or missing.
      </div>
    </div>

    <!-- Station Re-structuring -->
    <div class="setting-group">
      <div class="setting-label-row">
        <span>Re-structure Station Order</span>
      </div>
      <div class="sort-actions">
        <div class="btn-sort" onclick="sortStations('attention')">⚠️ Attention First</div>
        <div class="btn-sort" onclick="sortStations('id')">🔢 By ID</div>
        <div class="btn-sort" onclick="sortStations('name')">🔤 By Name</div>
      </div>
      <div class="reorder-list" id="reorderList"></div>
      <button class="btn-save-order" onclick="saveStationOrder()">💾 Save & Persist Station Order</button>
    </div>
  </div>

</div>

<script>
  let isPinned = true;
  let isCompact = false;
  let isSoundEnabled = true;
  let currentScanSecs = 60;
  let scanRemainingSecs = 60;
  let scanTimerInterval = null;
  let lastData = null;
  let activeDrilldownId = null;
  let stationsOrder = [];

  // --------------------------------------------------------------------------
  // Realtime Clocks & Scan Countdown
  // --------------------------------------------------------------------------
  function updateClocks() {
    const now = new Date();
    const utcHours = String(now.getUTCHours()).padStart(2, '0');
    const utcMins = String(now.getUTCMinutes()).padStart(2, '0');
    const utcSecs = String(now.getUTCSeconds()).padStart(2, '0');
    document.getElementById('clockUtc').innerText = `${utcHours}:${utcMins}:${utcSecs} UTC`;

    const istTime = new Date(now.getTime() + (5.5 * 60 * 60 * 1000));
    const istHours = String(istTime.getUTCHours()).padStart(2, '0');
    const istMins = String(istTime.getUTCMinutes()).padStart(2, '0');
    const istSecs = String(istTime.getUTCSeconds()).padStart(2, '0');
    document.getElementById('clockIst').innerText = `${istHours}:${istMins}:${istSecs} IST`;

    // Scan countdown
    scanRemainingSecs--;
    if (scanRemainingSecs <= 0) {
      scanRemainingSecs = currentScanSecs;
      loadData();
    }
    const mins = Math.floor(scanRemainingSecs / 60);
    const secs = scanRemainingSecs % 60;
    const timeStr = mins > 0 ? `${mins}m ${secs}s` : `${secs}s`;
    document.getElementById('scanCountdown').innerText = `Scan in ${timeStr}`;
  }
  setInterval(updateClocks, 1000);
  updateClocks();

  // --------------------------------------------------------------------------
  // Web Audio Synthesizer (Acoustic Chime for Late Synops)
  // --------------------------------------------------------------------------
  function playAlertSound() {
    if (!isSoundEnabled) return;
    try {
      const audioCtx = new (window.AudioContext || window.webkitAudioContext)();
      const osc = audioCtx.createOscillator();
      const gain = audioCtx.createGain();
      osc.type = 'sine';
      osc.frequency.setValueAtTime(587.33, audioCtx.currentTime); // D5
      osc.frequency.exponentialRampToValueAtTime(880, audioCtx.currentTime + 0.15); // A5
      gain.gain.setValueAtTime(0.2, audioCtx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.001, audioCtx.currentTime + 0.45);
      osc.connect(gain);
      gain.connect(audioCtx.destination);
      osc.start();
      osc.stop(audioCtx.currentTime + 0.45);
    } catch(e) {
      console.warn('Audio synthesis unavailable:', e);
    }
  }

  function testAlertSound() {
    playAlertSound();
  }

  function toggleSound() {
    isSoundEnabled = !isSoundEnabled;
    const btn = document.getElementById('btnSound');
    if (isSoundEnabled) {
      btn.innerText = '🔔';
      btn.classList.add('alert-on');
      btn.title = 'Late Synop Audio Alert: ON';
    } else {
      btn.innerText = '🔕';
      btn.classList.remove('alert-on');
      btn.title = 'Late Synop Audio Alert: MUTED';
    }
    localStorage.setItem('synop_sound_alert', isSoundEnabled ? '1' : '0');
  }

  // --------------------------------------------------------------------------
  // Opacity Level Changer
  // --------------------------------------------------------------------------
  function changeOpacity(val) {
    const alpha = (val / 100).toFixed(2);
    document.documentElement.style.setProperty('--bg-glass-alpha', alpha);
    document.getElementById('opacityVal').innerText = `${val}%`;
    localStorage.setItem('synop_opacity_val', val);
  }

  function initSavedOpacity() {
    const saved = localStorage.getItem('synop_opacity_val') || '88';
    document.getElementById('opacitySlider').value = saved;
    changeOpacity(saved);
  }

  // --------------------------------------------------------------------------
  // Scan Timing Interval Changer
  // --------------------------------------------------------------------------
  function changeScanTiming(secs, label) {
    currentScanSecs = secs;
    scanRemainingSecs = secs;
    document.getElementById('timingVal').innerText = label;
    document.querySelectorAll('.btn-timing').forEach(b => {
      b.classList.toggle('active', b.innerText === label);
    });
    localStorage.setItem('synop_scan_timing', secs);
  }

  // --------------------------------------------------------------------------
  // Matrix Render & Late Alerts
  // --------------------------------------------------------------------------
  function renderData(data) {
    if (!data || !data.success) return;
    lastData = data;
    stationsOrder = (data.stations || []).map(s => s.id);

    // Check Late Alerts
    const alerts = data.late_alerts || [];
    const banner = document.getElementById('alertBanner');
    const bannerText = document.getElementById('alertBannerText');

    if (alerts.length > 0) {
      const topAlert = alerts[0];
      bannerText.innerText = `⚠️ ${topAlert.station_name} sent Late Synop (${topAlert.hour.slice(0,2)}Z)`;
      banner.classList.add('show');
      playAlertSound();
    } else {
      banner.classList.remove('show');
    }

    // Render Matrix Rows
    const rowsEl = document.getElementById('matrixRows');
    if (!data.stations || data.stations.length === 0) {
      rowsEl.innerHTML = '<div style="text-align: center; color: var(--text-muted); padding: 30px;">No station data available.</div>';
      return;
    }

    let rowsHtml = '';
    data.stations.forEach(st => {
      const hasLate = (st.slots || []).some(s => s.status === 'LATE' || s.status === 'VERY_LATE' || s.status === 'MISSING');
      const rowAlertCls = hasLate ? 'has-alert' : '';

      let cellsHtml = '';
      (st.slots || []).forEach(slot => {
        let pillCls = 'cell-awaiting';
        let pillText = slot.hour.slice(0, 2);

        if (slot.status === 'ON_TIME') { pillCls = 'cell-on-time'; pillText = '✓'; }
        else if (slot.status === 'LATE' || slot.status === 'VERY_LATE') { pillCls = 'cell-late'; pillText = '⚠️'; }
        else if (slot.status === 'MISSING') { pillCls = 'cell-missing'; pillText = '✕'; }
        else if (slot.status === 'EARLY') { pillCls = 'cell-early'; pillText = 'E'; }
        else if (slot.status === 'NOT_SCHEDULED') { pillCls = 'cell-not-scheduled'; pillText = '-'; }

        cellsHtml += `<span class="cell-pill ${pillCls}" title="${slot.hour.slice(0,2)}Z: ${slot.badge_text}">${pillText}</span>`;
      });

      rowsHtml += `
        <div class="station-row ${rowAlertCls}" onclick="openDrilldown('${st.id}')">
          <div class="st-info">
            <span class="st-code">${st.id}</span>
            <span class="st-name" title="${st.name}">${st.name}</span>
          </div>
          <div class="cycles-cells">
            ${cellsHtml}
          </div>
          <span class="row-chevron">›</span>
        </div>
      `;
    });

    rowsEl.innerHTML = rowsHtml;

    // Refresh drilldown if active
    if (activeDrilldownId) {
      renderDrilldown(activeDrilldownId);
    }
  }

  // --------------------------------------------------------------------------
  // Station Drill-Down (Reverse Chronological Synop History)
  // --------------------------------------------------------------------------
  function openDrilldown(stationId) {
    activeDrilldownId = stationId;
    renderDrilldown(stationId);
    document.getElementById('viewMatrix').style.display = 'none';
    document.getElementById('viewSettings').style.display = 'none';
    document.getElementById('viewDrilldown').style.display = 'flex';
  }

  function closeDrilldown() {
    activeDrilldownId = null;
    document.getElementById('viewDrilldown').style.display = 'none';
    document.getElementById('viewSettings').style.display = 'none';
    document.getElementById('viewMatrix').style.display = 'flex';
  }

  function onAlertBannerClick() {
    if (lastData && lastData.late_alerts && lastData.late_alerts.length > 0) {
      openDrilldown(lastData.late_alerts[0].station_id);
    }
  }

  function renderDrilldown(stationId) {
    if (!lastData || !lastData.stations) return;
    const st = lastData.stations.find(s => String(s.id) === String(stationId));
    if (!st) return;

    document.getElementById('ddStCode').innerText = st.id;
    document.getElementById('ddStName').innerText = st.name;
    const badgeEl = document.getElementById('ddStBadge');
    badgeEl.innerText = st.overall_status.replace(/_/g, ' ');
    badgeEl.className = st.overall_status === 'ALL_NORMAL' ? 'feed-status-badge badge-on-time' : 'feed-status-badge badge-late';

    const feedEl = document.getElementById('drilldownFeed');
    let feedHtml = '';

    // Reverse chronological order: 21Z -> 18Z -> 15Z -> 12Z -> 09Z -> 06Z -> 03Z -> 00Z
    const reversedSlots = [...(st.slots || [])].reverse();

    reversedSlots.forEach(slot => {
      let badgeClass = 'badge-awaiting';
      if (slot.status === 'ON_TIME') badgeClass = 'badge-on-time';
      else if (slot.status === 'LATE' || slot.status === 'VERY_LATE') badgeClass = 'badge-late';
      else if (slot.status === 'MISSING') badgeClass = 'badge-missing';

      const transLabel = slot.duplicate_badge || (slot.transmission_count > 1 ? `Collective Echo (${slot.transmission_count})` : 'Single Transmission');
      const rawSynop = slot.raw_synop || (slot.received ? 'SYNOP received but text unavailable.' : 'Pending observation window.');

      feedHtml += `
        <div class="feed-card">
          <div class="feed-card-top">
            <div class="feed-obs-time">
              <span class="feed-hour-chip">${slot.label}</span>
              <span>${slot.hour.slice(0,2)}:00 UTC</span>
            </div>
            <span class="feed-status-badge ${badgeClass}">${slot.badge_text}</span>
          </div>
          <div class="feed-meta-row">
            <span>${slot.received ? `Transmissions: ${slot.transmission_count}` : 'Awaiting schedule'}</span>
            <span style="color: var(--accent-sky); font-weight: 600;">${transLabel}</span>
          </div>
          <div class="feed-raw-text">${rawSynop}</div>
        </div>
      `;
    });

    feedEl.innerHTML = feedHtml;
  }

  function copyLatestSynop() {
    if (!activeDrilldownId || !lastData) return;
    const st = lastData.stations.find(s => String(s.id) === String(activeDrilldownId));
    if (!st) return;
    const receivedSlot = [...(st.slots || [])].reverse().find(s => s.received && s.raw_synop);
    if (receivedSlot && receivedSlot.raw_synop) {
      navigator.clipboard.writeText(receivedSlot.raw_synop);
      alert('Latest AAXX copied to clipboard!');
    } else {
      alert('No received AAXX report available to copy.');
    }
  }

  // --------------------------------------------------------------------------
  // Settings Overlay & Station Re-ordering
  // --------------------------------------------------------------------------
  function openSettings() {
    document.getElementById('viewMatrix').style.display = 'none';
    document.getElementById('viewDrilldown').style.display = 'none';
    document.getElementById('viewSettings').style.display = 'flex';
    renderReorderList();
  }

  function closeSettings() {
    document.getElementById('viewSettings').style.display = 'none';
    if (activeDrilldownId) {
      document.getElementById('viewDrilldown').style.display = 'flex';
    } else {
      document.getElementById('viewMatrix').style.display = 'flex';
    }
  }

  function renderReorderList() {
    const listEl = document.getElementById('reorderList');
    if (!lastData || !lastData.stations) return;

    let html = '';
    stationsOrder.forEach((sid, idx) => {
      const st = lastData.stations.find(s => String(s.id) === String(sid));
      if (!st) return;
      html += `
        <div class="reorder-item">
          <span><strong>${st.id}</strong> ${st.name}</span>
          <div class="reorder-btns">
            <button class="btn-shift" onclick="moveStation(${idx}, -1)" ${idx === 0 ? 'disabled' : ''}>▲</button>
            <button class="btn-shift" onclick="moveStation(${idx}, 1)" ${idx === stationsOrder.length - 1 ? 'disabled' : ''}>▼</button>
          </div>
        </div>
      `;
    });
    listEl.innerHTML = html;
  }

  function moveStation(idx, dir) {
    const newIdx = idx + dir;
    if (newIdx < 0 || newIdx >= stationsOrder.length) return;
    const temp = stationsOrder[idx];
    stationsOrder[idx] = stationsOrder[newIdx];
    stationsOrder[newIdx] = temp;
    renderReorderList();
  }

  function sortStations(mode) {
    if (!lastData || !lastData.stations) return;
    if (mode === 'id') {
      stationsOrder.sort((a, b) => a.localeCompare(b));
    } else if (mode === 'name') {
      stationsOrder.sort((a, b) => {
        const sa = lastData.stations.find(s => s.id === a);
        const sb = lastData.stations.find(s => s.id === b);
        return (sa ? sa.name : '').localeCompare(sb ? sb.name : '');
      });
    } else if (mode === 'attention') {
      stationsOrder.sort((a, b) => {
        const sa = lastData.stations.find(s => s.id === a);
        const sb = lastData.stations.find(s => s.id === b);
        const aAlert = sa && (sa.slots || []).some(s => s.status === 'LATE' || s.status === 'MISSING');
        const bAlert = sb && (sb.slots || []).some(s => s.status === 'LATE' || s.status === 'MISSING');
        return (bAlert ? 1 : 0) - (aAlert ? 1 : 0);
      });
    }
    renderReorderList();
  }

  async function saveStationOrder() {
    if (window.pywebview && window.pywebview.api) {
      try {
        const res = await window.pywebview.api.reorder_stations(JSON.stringify(stationsOrder));
        if (res) {
          alert('Station order persisted successfully!');
          triggerRefresh();
        } else {
          alert('Failed to persist station order.');
        }
      } catch(e) {
        console.error(e);
      }
    }
  }

  // --------------------------------------------------------------------------
  // Python Bridge Actions
  // --------------------------------------------------------------------------
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
    scanRemainingSecs = currentScanSecs;
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

  // Initial load
  initSavedOpacity();
  const savedTiming = localStorage.getItem('synop_scan_timing');
  if (savedTiming) {
    const s = parseInt(savedTiming, 10);
    const lbl = s < 60 ? `${s}s` : `${Math.floor(s/60)}m`;
    changeScanTiming(s, lbl);
  }

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

    widget_w = 350
    widget_h = 470
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
