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
import base64
import socket
import logging
import threading
import subprocess
import webbrowser
import ctypes
from ctypes import windll, wintypes
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any, Optional

import requests
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


def get_app_data_file(filename: str) -> str:
    app_data = os.environ.get("APPDATA")
    if app_data:
        user_dir = os.path.join(app_data, "IMD_SYNOP")
        try:
            os.makedirs(user_dir, exist_ok=True)
            return os.path.join(user_dir, filename)
        except Exception:
            pass
    return os.path.join(EXE_DIR, filename)


def get_user_config_path() -> str:
    return get_app_data_file("stations_config.json")


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


DEFAULT_POLLING_SETTINGS = {
    "mode": "dynamic",               # "dynamic" or "fixed"
    "window_before_mins": 15,        # start expecting N mins before synoptic hour
    "window_after_mins": 30,         # end expectation N mins after synoptic hour
    "active_interval_secs": 60,      # poll interval during expectation window
    "idle_interval_secs": 900,       # poll interval outside window / after late cutoff
    "fixed_interval_secs": 60,       # poll interval when mode == "fixed"
    "early_exit_on_complete": True,  # drop to idle as soon as all stations report
}

DEFAULT_SYNC_CONFIG = {
    "enabled": True,
    "read_url": "https://raw.githubusercontent.com/Aman6390/synop-sanity-checker/main/shared_timestamps.json",
    "publish_url": "",               # Optional HTTP POST webhook or GitHub Contents API URL
    "publish_token": "",             # Optional Bearer / GitHub PAT (stored locally only)
    "auto_publish": True,
}


class TimestampSyncManager:
    """
    Records exact UTC first-seen timestamps when SYNOPs appear on AMSS,
    merges with a shared public JSON feed, and optionally publishes updates
    so all users of the software share past arrival timings.
    """

    def __init__(self):
        self.cache_path = get_app_data_file("seen_timestamps.json")
        self.config_path = get_app_data_file("sync_config.json")
        self.timestamps: Dict[str, Dict[str, Any]] = {}
        self.last_remote_fetch: Optional[datetime] = None
        self._lock = threading.Lock()
        self._load_cache()

    def load_config(self) -> Dict[str, Any]:
        cfg = dict(DEFAULT_SYNC_CONFIG)
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    cfg.update(json.load(f))
            except Exception as e:
                logger.warning(f"Failed loading sync config: {e}")
        return cfg

    def save_config(self, new_cfg: Dict[str, Any]) -> Dict[str, Any]:
        cfg = self.load_config()
        for k in DEFAULT_SYNC_CONFIG:
            if k in new_cfg:
                cfg[k] = new_cfg[k]
        try:
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=2)
        except Exception as e:
            logger.error(f"Failed saving sync config: {e}")
        return cfg

    def _load_cache(self) -> None:
        if os.path.exists(self.cache_path):
            try:
                with open(self.cache_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.timestamps = data.get("station_timestamps", {})
            except Exception as e:
                logger.warning(f"Failed loading timestamp cache: {e}")

    def _save_cache(self) -> None:
        try:
            payload = self.build_payload()
            with open(self.cache_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)
        except Exception as e:
            logger.warning(f"Failed saving timestamp cache: {e}")

    def prune_old(self, now_utc: datetime) -> None:
        cutoff = now_utc - timedelta(hours=48)
        to_del = []
        for k, v in self.timestamps.items():
            try:
                dt = datetime.fromisoformat(v.get("first_seen_utc", ""))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                if dt < cutoff:
                    to_del.append(k)
            except Exception:
                to_del.append(k)
        for k in to_del:
            del self.timestamps[k]

    def build_payload(self) -> Dict[str, Any]:
        return {
            "schema_version": 1,
            "updated_utc": datetime.now(timezone.utc).isoformat(),
            "station_timestamps": self.timestamps,
        }

    def fetch_remote(self, force: bool = False) -> None:
        cfg = self.load_config()
        if not cfg.get("enabled") or not cfg.get("read_url"):
            return
        now_utc = datetime.now(timezone.utc)
        if not force and self.last_remote_fetch and (now_utc - self.last_remote_fetch).total_seconds() < 45:
            return
        try:
            resp = requests.get(cfg["read_url"], timeout=4)
            if resp.status_code == 200:
                remote_data = resp.json()
                remote_ts = remote_data.get("station_timestamps", {})
                with self._lock:
                    for k, v in remote_ts.items():
                        if k not in self.timestamps:
                            self.timestamps[k] = v
                self.last_remote_fetch = now_utc
        except Exception as e:
            logger.debug(f"Remote timestamp fetch skipped: {e}")

    def record_if_live(self, station_id: str, date_str: str, hour: str, slot_time: datetime, now_utc: datetime) -> Optional[Dict[str, Any]]:
        key = f"{station_id}_{date_str}_{hour}"
        with self._lock:
            if key in self.timestamps:
                return self.timestamps[key]
            # Only stamp live arrival if now_utc is within [-45m, +120m] of slot_time
            delta_mins = (now_utc - slot_time).total_seconds() / 60.0
            if -45 <= delta_mins <= 120:
                entry = {
                    "station_id": str(station_id),
                    "date_utc": date_str,
                    "hour": hour,
                    "first_seen_utc": now_utc.isoformat(),
                    "delta_minutes": round(delta_mins, 1),
                    "source": "amss_live_seen",
                }
                self.timestamps[key] = entry
                return entry
        return None

    def get_entry(self, station_id: str, date_str: str, hour: str) -> Optional[Dict[str, Any]]:
        key = f"{station_id}_{date_str}_{hour}"
        return self.timestamps.get(key)

    def publish_async(self) -> None:
        cfg = self.load_config()
        pub_url = (cfg.get("publish_url") or "").strip()
        if not cfg.get("enabled") or not pub_url:
            return

        def _worker():
            try:
                payload = self.build_payload()
                token = (cfg.get("publish_token") or "").strip()
                headers = {"Content-Type": "application/json"}
                if token:
                    headers["Authorization"] = f"Bearer {token}"

                # Support GitHub Contents API PUT (api.github.com/repos/.../contents/...)
                if "api.github.com/repos/" in pub_url and "/contents/" in pub_url:
                    sha = None
                    get_r = requests.get(pub_url, headers=headers, timeout=5)
                    if get_r.status_code == 200:
                        sha = get_r.json().get("sha")
                    content_b64 = base64.b64encode(json.dumps(payload, indent=2).encode("utf-8")).decode("ascii")
                    body = {
                        "message": f"Update shared SYNOP timestamps ({payload['updated_utc']})",
                        "content": content_b64,
                    }
                    if sha:
                        body["sha"] = sha
                    requests.put(pub_url, headers=headers, json=body, timeout=6)
                else:
                    requests.post(pub_url, headers=headers, json=payload, timeout=5)
            except Exception as e:
                logger.warning(f"Timestamp publish failed: {e}")

        threading.Thread(target=_worker, daemon=True).start()


class WidgetBackend:
    """Manages cached data fetching, parsing, dynamic polling, and SLA engine analysis."""

    def __init__(self):
        self.cached_data: Optional[Dict[str, Any]] = None
        self.last_fetch_time: Optional[datetime] = None
        self.last_source: str = "Uninitialized"
        self.fetcher = AMSSFetcher()
        self.sync_mgr = TimestampSyncManager()
        self.polling_cfg_path = get_app_data_file("polling_settings.json")

    def load_polling_settings(self) -> Dict[str, Any]:
        cfg = dict(DEFAULT_POLLING_SETTINGS)
        if os.path.exists(self.polling_cfg_path):
            try:
                with open(self.polling_cfg_path, "r", encoding="utf-8") as f:
                    cfg.update(json.load(f))
            except Exception as e:
                logger.warning(f"Failed loading polling settings: {e}")
        return cfg

    def save_polling_settings(self, new_cfg: Dict[str, Any]) -> Dict[str, Any]:
        cfg = self.load_polling_settings()
        for k in DEFAULT_POLLING_SETTINGS:
            if k in new_cfg:
                cfg[k] = new_cfg[k]
        try:
            with open(self.polling_cfg_path, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=2)
        except Exception as e:
            logger.error(f"Failed saving polling settings: {e}")
        return cfg

    def compute_dynamic_window(
        self,
        now_utc: datetime,
        settings: Dict[str, Any],
        evaluated_stations: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        before_m = int(settings.get("window_before_mins", 15))
        after_m = int(settings.get("window_after_mins", 30))
        active_secs = max(15, int(settings.get("active_interval_secs", 60)))
        idle_secs = max(60, int(settings.get("idle_interval_secs", 900)))
        fixed_secs = max(15, int(settings.get("fixed_interval_secs", 60)))
        mode = settings.get("mode", "dynamic")
        early_exit = bool(settings.get("early_exit_on_complete", True))

        synoptic_hours = [0, 3, 6, 9, 12, 15, 18, 21]
        candidates = []
        for day_offset in [-1, 0, 1]:
            base_date = (now_utc + timedelta(days=day_offset)).date()
            for h in synoptic_hours:
                obs_dt = datetime(base_date.year, base_date.month, base_date.day, h, 0, tzinfo=timezone.utc)
                w_start = obs_dt - timedelta(minutes=before_m)
                w_end = obs_dt + timedelta(minutes=after_m)
                candidates.append((obs_dt, w_start, w_end, f"{h:02d}00", f"{h:02d}Z"))

        in_expectation = False
        active_cycle_str = ""
        active_hour_key = ""
        mins_left = 0

        for obs_dt, w_start, w_end, h_key, h_lbl in candidates:
            if w_start <= now_utc <= w_end:
                in_expectation = True
                active_cycle_str = h_lbl
                active_hour_key = h_key
                mins_left = max(0, int((w_end - now_utc).total_seconds() / 60))
                break

        # Check if all stations requiring the active hour have already reported
        all_complete = False
        if in_expectation and evaluated_stations:
            required_for_cycle = []
            for st in evaluated_stations:
                slot = next((sl for sl in st.get("slots", []) if sl.get("hour") == active_hour_key), None)
                if slot and slot.get("status") != "NOT_SCHEDULED":
                    required_for_cycle.append(slot.get("received", False))
            if required_for_cycle and all(required_for_cycle):
                all_complete = True

        if mode == "fixed":
            return {
                "mode": "fixed",
                "is_active": in_expectation,
                "is_expectation_window": in_expectation,
                "all_complete": all_complete,
                "cycle": active_cycle_str or "Fixed",
                "target_poll_seconds": fixed_secs,
                "status_text": f"Fixed Poll ({fixed_secs}s)" + (f" · {active_cycle_str}" if in_expectation else ""),
            }

        if in_expectation:
            if early_exit and all_complete:
                return {
                    "mode": "dynamic",
                    "is_active": False,
                    "is_expectation_window": False,
                    "all_complete": True,
                    "cycle": active_cycle_str,
                    "target_poll_seconds": idle_secs,
                    "status_text": f"{active_cycle_str} Complete · Idle",
                }
            return {
                "mode": "dynamic",
                "is_active": True,
                "is_expectation_window": True,
                "all_complete": False,
                "cycle": active_cycle_str,
                "target_poll_seconds": active_secs,
                "status_text": f"Expecting {active_cycle_str} ({mins_left}m left)",
            }

        future_windows = [c for c in candidates if c[1] > now_utc]
        next_label = min(future_windows, key=lambda x: x[1])[4] if future_windows else "00Z"
        return {
            "mode": "dynamic",
            "is_active": False,
            "is_expectation_window": False,
            "all_complete": False,
            "cycle": next_label,
            "target_poll_seconds": idle_secs,
            "status_text": f"Idle · Next {next_label}",
        }

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
            date_str = now_utc.strftime("%Y-%m-%d")
            polling_settings = self.load_polling_settings()
            stations = self.load_stations_config()

            # Sync remote shared timestamps & prune old >48h entries
            self.sync_mgr.fetch_remote()
            self.sync_mgr.prune_old(now_utc)
            new_timestamps_recorded = False

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
                    is_received = slot.get("received", False)

                    # Record or lookup shared first-seen timestamp
                    slot_dt = now_utc.replace(hour=int(h[:2]), minute=0, second=0, microsecond=0)
                    ts_entry = self.sync_mgr.get_entry(st_id, date_str, h)
                    if is_received and source == "AMSS Delhi Live" and not ts_entry:
                        recorded = self.sync_mgr.record_if_live(st_id, date_str, h, slot_dt, now_utc)
                        if recorded:
                            ts_entry = recorded
                            new_timestamps_recorded = True

                    first_seen_time = ""
                    first_seen_delta = None
                    if ts_entry and ts_entry.get("first_seen_utc"):
                        try:
                            fs_dt = datetime.fromisoformat(ts_entry["first_seen_utc"])
                            first_seen_time = fs_dt.strftime("%H:%M:%S UTC")
                            first_seen_delta = ts_entry.get("delta_minutes")
                        except Exception:
                            pass

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

                    earliest_ht = (slot.get("earliest_report", {}) or {}).get("header_timestamp", "")
                    filing_time = f"{earliest_ht[2:4]}:{earliest_ht[4:6]} UTC" if len(earliest_ht) >= 6 else ""

                    slots_data.append({
                        "hour": h,
                        "label": f"{h[:2]}Z",
                        "status": slot_status,
                        "severity": slot.get("severity", "muted"),
                        "badge_text": badge_text,
                        "received": is_received,
                        "transmission_count": slot.get("transmission_count", 0),
                        "duplicate_type": slot.get("duplicate_type", "NONE"),
                        "duplicate_badge": slot.get("duplicate_badge", ""),
                        "delta_minutes": slot.get("delta_minutes"),
                        "filing_time": filing_time,
                        "first_seen_time": first_seen_time,
                        "first_seen_delta": first_seen_delta,
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

            if new_timestamps_recorded:
                self.sync_mgr._save_cache()
                sync_cfg = self.sync_mgr.load_config()
                if sync_cfg.get("auto_publish", True):
                    self.sync_mgr.publish_async()

            window_status = self.compute_dynamic_window(now_utc, polling_settings, evaluated_stations)
            self.last_fetch_time = now_utc
            self.last_source = source

            sync_cfg = self.sync_mgr.load_config()
            self.cached_data = {
                "success": True,
                "source": source,
                "total_bulletins": parsed.get("total_bulletins", 0),
                "last_fetch_iso": now_utc.isoformat(),
                "window_status": window_status,
                "polling_settings": polling_settings,
                "sync_info": {
                    "enabled": sync_cfg.get("enabled", True),
                    "read_url": sync_cfg.get("read_url", ""),
                    "publish_url": sync_cfg.get("publish_url", ""),
                    "has_token": bool(sync_cfg.get("publish_token")),
                    "auto_publish": sync_cfg.get("auto_publish", True),
                    "recorded_count": len(self.sync_mgr.timestamps),
                },
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

# Define 64-bit safe SetWindowPos signature so HWND_TOPMOST (-1) / HWND_NOTOPMOST (-2) work properly
_SetWindowPos = windll.user32.SetWindowPos
_SetWindowPos.argtypes = [
    wintypes.HWND,
    wintypes.HWND,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_uint,
]
_SetWindowPos.restype = wintypes.BOOL

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

    def save_polling_settings(self, settings_json: str) -> str:
        """Persists user-configured dynamic/fixed polling parameters."""
        try:
            parsed = json.loads(settings_json)
            saved = backend_instance.save_polling_settings(parsed)
            return json.dumps({"success": True, "settings": saved})
        except Exception as e:
            logger.error(f"Error saving polling settings: {e}")
            return json.dumps({"success": False, "error": str(e)})

    def save_sync_config(self, sync_json: str) -> str:
        """Persists shared timestamp sync URL and optional publish settings."""
        try:
            parsed = json.loads(sync_json)
            saved = backend_instance.sync_mgr.save_config(parsed)
            return json.dumps({"success": True, "enabled": saved.get("enabled", True)})
        except Exception as e:
            logger.error(f"Error saving sync config: {e}")
            return json.dumps({"success": False, "error": str(e)})

    def export_timestamps_json(self) -> str:
        """Exports all recorded SYNOP arrival timestamps to shared_timestamps.json next to executable."""
        try:
            payload = backend_instance.sync_mgr.build_payload()
            out_path = os.path.join(EXE_DIR, "shared_timestamps.json")
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)
            return json.dumps({
                "success": True,
                "path": out_path,
                "count": len(payload.get("station_timestamps", {})),
                "json_text": json.dumps(payload, indent=2),
            })
        except Exception as e:
            logger.error(f"Error exporting timestamps JSON: {e}")
            return json.dumps({"success": False, "error": str(e)})

    def push_timestamps_now(self) -> str:
        """Manually triggers publishing timestamps JSON to the configured publish URL."""
        try:
            cfg = backend_instance.sync_mgr.load_config()
            if not (cfg.get("publish_url") or "").strip():
                return json.dumps({"success": False, "error": "No Publish URL configured in Settings."})
            backend_instance.sync_mgr.publish_async()
            return json.dumps({"success": True})
        except Exception as e:
            return json.dumps({"success": False, "error": str(e)})

    def toggle_pin(self) -> bool:
        """Toggles always-on-top behavior asynchronously without blocking the UI thread."""
        self.is_pinned = not self.is_pinned
        pinned = self.is_pinned

        # 1. Update WinForms Form.TopMost asynchronously on the WinForms UI thread (no deadlock)
        if _widget_window:
            try:
                import webview.platforms.winforms as wf
                from System import Action
                inst = wf.BrowserView.instances.get(_widget_window.uid)
                if inst:
                    inst.BeginInvoke(Action(lambda: setattr(inst, "TopMost", pinned)))
            except Exception as e:
                logger.warning(f"WinForms BeginInvoke TopMost error: {e}")

        # 2. Also apply 64-bit safe Win32 SetWindowPos asynchronously
        hwnd = get_widget_hwnd()
        if hwnd:
            try:
                target = HWND_TOPMOST if pinned else HWND_NOTOPMOST
                flags = SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_ASYNCWINDOWPOS
                threading.Thread(
                    target=_SetWindowPos,
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
    display: flex;
    align-items: center;
    gap: 4px;
  }

  .active-poll-spinner {
    display: none;
    width: 9px;
    height: 9px;
    border: 1.5px solid rgba(56, 189, 248, 0.28);
    border-top-color: #38BDF8;
    border-radius: 50%;
    animation: spin 1.1s linear infinite;
  }

  .active-poll-spinner.active {
    display: inline-block;
  }

  .active-poll-spinner.fetching {
    display: inline-block;
    border-top-color: #10B981;
    animation: spin 0.45s linear infinite;
  }

  .setting-subgrid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 6px;
    margin-top: 6px;
  }

  .setting-field {
    display: flex;
    flex-direction: column;
    gap: 2px;
  }

  .setting-field label {
    font-size: 0.58rem;
    color: var(--text-muted);
    font-weight: 600;
  }

  .setting-select, .setting-input {
    width: 100%;
    background: rgba(0, 0, 0, 0.35);
    border: 1px solid rgba(255, 255, 255, 0.14);
    color: #F8FAFC;
    border-radius: 5px;
    padding: 3px 5px;
    font-size: 0.62rem;
    outline: none;
  }

  .setting-select:focus, .setting-input:focus {
    border-color: var(--accent-sky);
  }

  .setting-check-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    font-size: 0.62rem;
    color: var(--text-secondary);
    margin-top: 6px;
    cursor: pointer;
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

  /* Status Legend Header (replaces table column header for Box Grid) */
  .matrix-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 5px 10px;
    background: rgba(0, 0, 0, 0.22);
    border-bottom: 1px solid rgba(255, 255, 255, 0.06);
    font-size: 0.58rem;
    font-weight: 600;
    color: var(--text-muted);
  }

  .legend-title {
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    color: #CBD5E1;
  }

  .legend-pills {
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .legend-item {
    display: flex;
    align-items: center;
    gap: 3px;
    font-size: 0.57rem;
    color: #CBD5E1;
  }

  .legend-dot {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    display: inline-block;
  }

  .dot-ok { background: #10B981; box-shadow: 0 0 5px rgba(16, 185, 129, 0.6); }
  .dot-early { background: #EAB308; box-shadow: 0 0 5px rgba(234, 179, 8, 0.6); }
  .dot-late { background: #F97316; box-shadow: 0 0 5px rgba(249, 115, 22, 0.6); }
  .dot-missing { background: #EF4444; box-shadow: 0 0 5px rgba(239, 68, 68, 0.6); }

  /* View Container (Matrix, Drilldown, Settings) */
  .view-panel {
    flex: 1;
    display: flex;
    flex-direction: column;
    overflow: hidden;
    position: relative;
  }

  /* Box-Type 3x4 Grid (Zero Scrolling, All 12 Stations Visible) */
  .matrix-body {
    flex: 1;
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    grid-auto-rows: 1fr;
    gap: 6px;
    padding: 7px 8px;
    overflow: hidden;
  }

  .station-box {
    display: flex;
    flex-direction: column;
    justify-content: space-between;
    padding: 6px 7px;
    border-radius: 10px;
    cursor: pointer;
    position: relative;
    overflow: hidden;
    transition: transform 0.16s var(--spring-easing), box-shadow 0.16s ease, border-color 0.16s ease, background 0.16s ease;
    backdrop-filter: blur(8px);
  }

  .station-box:hover {
    transform: translateY(-2px) scale(1.02);
    z-index: 2;
  }

  .station-box:active {
    transform: scale(0.98);
  }

  /* Green: Everything OK */
  .station-box.box-ok {
    background: linear-gradient(145deg, rgba(16, 185, 129, 0.24), rgba(5, 150, 105, 0.12));
    border: 1px solid rgba(16, 185, 129, 0.52);
    box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.12), 0 2px 8px rgba(16, 185, 129, 0.12);
  }
  .station-box.box-ok:hover {
    border-color: rgba(52, 211, 153, 0.85);
    box-shadow: 0 4px 12px rgba(16, 185, 129, 0.28);
  }

  /* Yellow: Early Synop */
  .station-box.box-early {
    background: linear-gradient(145deg, rgba(234, 179, 8, 0.26), rgba(161, 98, 7, 0.14));
    border: 1px solid rgba(234, 179, 8, 0.65);
    box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.12), 0 2px 8px rgba(234, 179, 8, 0.15);
  }
  .station-box.box-early:hover {
    border-color: rgba(250, 204, 21, 0.9);
    box-shadow: 0 4px 12px rgba(234, 179, 8, 0.30);
  }

  /* Orange: Late Synop */
  .station-box.box-late {
    background: linear-gradient(145deg, rgba(249, 115, 22, 0.28), rgba(194, 65, 12, 0.15));
    border: 1px solid rgba(249, 115, 22, 0.70);
    box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.12), 0 2px 8px rgba(249, 115, 22, 0.18);
  }
  .station-box.box-late:hover {
    border-color: rgba(251, 146, 60, 0.95);
    box-shadow: 0 4px 12px rgba(249, 115, 22, 0.35);
  }

  /* Red: Missing Synop */
  .station-box.box-missing {
    background: linear-gradient(145deg, rgba(239, 68, 68, 0.30), rgba(185, 28, 28, 0.16));
    border: 1px solid rgba(239, 68, 68, 0.75);
    box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.12), 0 2px 10px rgba(239, 68, 68, 0.22);
  }
  .station-box.box-missing:hover {
    border-color: rgba(248, 113, 113, 0.95);
    box-shadow: 0 4px 14px rgba(239, 68, 68, 0.40);
  }

  .box-top {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 3px;
  }

  .box-id {
    font-family: "SF Mono", Monaco, monospace;
    font-size: 0.58rem;
    font-weight: 700;
    color: rgba(255, 255, 255, 0.85);
    background: rgba(0, 0, 0, 0.26);
    padding: 1px 4px;
    border-radius: 4px;
    line-height: 1.15;
  }

  .box-status-tag {
    font-size: 0.52rem;
    font-weight: 800;
    letter-spacing: 0.03em;
    padding: 1px 4px;
    border-radius: 4px;
    text-transform: uppercase;
  }

  .tag-ok { background: rgba(16, 185, 129, 0.35); color: #A7F3D0; }
  .tag-early { background: rgba(234, 179, 8, 0.35); color: #FEF08A; }
  .tag-late { background: rgba(249, 115, 22, 0.38); color: #FED7AA; }
  .tag-missing { background: rgba(239, 68, 68, 0.40); color: #FECACA; }

  .box-name {
    font-size: 0.72rem;
    font-weight: 700;
    color: #FFFFFF;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    margin: 2px 0;
    text-shadow: 0 1px 2px rgba(0, 0, 0, 0.35);
  }

  .box-bottom {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 4px;
  }

  .box-dots {
    display: flex;
    align-items: center;
    gap: 2px;
  }

  .mini-slot {
    width: 5px;
    height: 5px;
    border-radius: 2px;
  }

  .ms-on-time { background: #34D399; }
  .ms-early { background: #FACC15; }
  .ms-late { background: #FB923C; }
  .ms-missing { background: #F87171; }
  .ms-awaiting { background: rgba(255, 255, 255, 0.22); }
  .ms-not-scheduled { background: rgba(255, 255, 255, 0.08); }

  .box-count {
    font-family: "SF Mono", Monaco, monospace;
    font-size: 0.54rem;
    font-weight: 600;
    color: rgba(255, 255, 255, 0.75);
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

  .badge-on-time { background: rgba(16, 185, 129, 0.18); color: #34D399; border: 1px solid rgba(16, 185, 129, 0.35); }
  .badge-early { background: rgba(234, 179, 8, 0.20); color: #FACC15; border: 1px solid rgba(234, 179, 8, 0.45); }
  .badge-late { background: rgba(249, 115, 22, 0.20); color: #FB923C; border: 1px solid rgba(249, 115, 22, 0.45); }
  .badge-missing { background: rgba(239, 68, 68, 0.22); color: #F87171; border: 1px solid rgba(239, 68, 68, 0.45); }
  .badge-awaiting { background: rgba(100, 116, 139, 0.2); color: #94A3B8; border: 1px solid rgba(100, 116, 139, 0.25); }

  .drilldown-summary {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 5px 10px;
    background: rgba(0, 0, 0, 0.22);
    border-bottom: 1px solid rgba(255, 255, 255, 0.06);
    font-size: 0.58rem;
    color: var(--text-muted);
  }

  .dd-stat-chips {
    display: flex;
    align-items: center;
    gap: 5px;
  }

  .dd-chip {
    padding: 1px 5px;
    border-radius: 4px;
    font-weight: 700;
    font-size: 0.56rem;
  }

  .feed-card.card-ok { border-left: 3px solid #10B981; }
  .feed-card.card-early { border-left: 3px solid #EAB308; }
  .feed-card.card-late { border-left: 3px solid #F97316; }
  .feed-card.card-missing { border-left: 3px solid #EF4444; }
  .feed-card.card-awaiting { border-left: 3px solid #64748B; }

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
      <span class="scan-pill" title="Dynamic Polling Status">
        <span class="active-poll-spinner" id="activePollSpinner" title="Synop Expectation Period Active"></span>
        <span id="scanCountdown">Scan: 1m</span>
      </span>
    </div>
  </div>

  <!-- Alert Banner (shown when a station sends late synop) -->
  <div class="alert-banner" id="alertBanner" onclick="onAlertBannerClick()">
    <span id="alertBannerText">⚠️ Late Synop Detected</span>
    <div style="display: flex; align-items: center; gap: 6px;">
      <button onclick="acknowledgeAlert(event)" style="background: rgba(255,255,255,0.2); border: 1px solid rgba(255,255,255,0.35); color: #fff; border-radius: 4px; padding: 1px 6px; font-size: 0.62rem; font-weight: 700; cursor: pointer;" title="Silence alert tone">OK</button>
      <span>Inspect ›</span>
    </div>
  </div>

  <!-- 1. ZERO-SCROLL BOX GRID VIEW -->
  <div class="view-panel" id="viewMatrix">
    <div class="matrix-header">
      <span class="legend-title">Stations (12)</span>
      <div class="legend-pills" id="legendCounts">
        <span class="legend-item"><span class="legend-dot dot-ok"></span>OK</span>
        <span class="legend-item"><span class="legend-dot dot-early"></span>Early</span>
        <span class="legend-item"><span class="legend-dot dot-late"></span>Late</span>
        <span class="legend-item"><span class="legend-dot dot-missing"></span>Miss</span>
      </div>
    </div>
    <div class="matrix-body" id="matrixRows">
      <div style="grid-column: 1 / -1; text-align: center; color: var(--text-muted); padding: 40px; font-size: 0.75rem;">
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

  <!-- 2. STATION DRILL-DOWN VIEW (All Relevant Information + Reverse Chronological Feed) -->
  <div class="view-panel drilldown-view" id="viewDrilldown">
    <div class="drilldown-header">
      <button class="btn-back" onclick="closeDrilldown()">‹ All Stations</button>
      <div class="drilldown-title">
        <span id="ddStCode">42027</span>
        <span id="ddStName">Srinagar</span>
      </div>
      <span class="feed-status-badge badge-on-time" id="ddStBadge">ALL NORMAL</span>
    </div>
    <div class="drilldown-summary" id="ddSummaryBar"></div>
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

    <!-- Dynamic Polling & Window Controls -->
    <div class="setting-group">
      <div class="setting-label-row">
        <span>Polling Mode & Timing</span>
        <span class="setting-val-tag" id="timingVal">Dynamic</span>
      </div>
      <div class="timing-buttons" style="margin-bottom: 6px;">
        <div class="btn-timing active" id="modeDynamicBtn" onclick="setPollingMode('dynamic')">⚡ Auto Dynamic</div>
        <div class="btn-timing" id="modeFixedBtn" onclick="setPollingMode('fixed')">⏱️ Fixed</div>
      </div>

      <div id="dynamicControls">
        <div class="setting-subgrid">
          <div class="setting-field">
            <label>Window Start (Before)</label>
            <select class="setting-select" id="cfgBeforeMins" onchange="applyPollingSettings()">
              <option value="0">0m (At Synop)</option>
              <option value="5">-5m before</option>
              <option value="10">-10m before</option>
              <option value="15" selected>-15m before</option>
              <option value="30">-30m before</option>
            </select>
          </div>
          <div class="setting-field">
            <label>Window End (After)</label>
            <select class="setting-select" id="cfgAfterMins" onchange="applyPollingSettings()">
              <option value="15">+15m after</option>
              <option value="20">+20m after</option>
              <option value="30" selected>+30m after</option>
              <option value="45">+45m after</option>
              <option value="60">+60m after</option>
            </select>
          </div>
          <div class="setting-field">
            <label>Active Window Poll</label>
            <select class="setting-select" id="cfgActiveSecs" onchange="applyPollingSettings()">
              <option value="30">Every 30s</option>
              <option value="60" selected>Every 60s</option>
              <option value="90">Every 90s</option>
              <option value="120">Every 2m</option>
            </select>
          </div>
          <div class="setting-field">
            <label>Idle / Post-Late Poll</label>
            <select class="setting-select" id="cfgIdleSecs" onchange="applyPollingSettings()">
              <option value="300">Every 5m</option>
              <option value="600">Every 10m</option>
              <option value="900" selected>Every 15m</option>
              <option value="1800">Every 30m</option>
              <option value="3600">Every 60m</option>
            </select>
          </div>
        </div>
        <label class="setting-check-row">
          <span>Early-exit when all stations report</span>
          <input type="checkbox" id="cfgEarlyExit" checked onchange="applyPollingSettings()">
        </label>
      </div>

      <div id="fixedControls" style="display: none;">
        <div class="timing-buttons">
          <div class="btn-timing" onclick="changeFixedTiming(30, '30s')">30s</div>
          <div class="btn-timing active" onclick="changeFixedTiming(60, '1m')">1m</div>
          <div class="btn-timing" onclick="changeFixedTiming(120, '2m')">2m</div>
          <div class="btn-timing" onclick="changeFixedTiming(300, '5m')">5m</div>
          <div class="btn-timing" onclick="changeFixedTiming(600, '10m')">10m</div>
        </div>
      </div>
    </div>

    <!-- Shared Timestamps JSON Sync -->
    <div class="setting-group">
      <div class="setting-label-row">
        <span>Shared Timestamps JSON</span>
        <span class="setting-val-tag" id="syncCountTag">0 saved</span>
      </div>
      <label class="setting-check-row" style="margin-top: 0; margin-bottom: 5px;">
        <span>Sync past arrival timings via JSON</span>
        <input type="checkbox" id="cfgSyncEnabled" checked onchange="applySyncConfig()">
      </label>
      <div class="setting-field" style="margin-bottom: 4px;">
        <label>Shared Feed URL (Read)</label>
        <input type="text" class="setting-input" id="cfgReadUrl" placeholder="https://raw.githubusercontent.com/.../shared_timestamps.json">
      </div>
      <div class="setting-field" style="margin-bottom: 4px;">
        <label>Publish URL (Optional POST / GitHub API)</label>
        <input type="text" class="setting-input" id="cfgPublishUrl" placeholder="Optional webhook or GitHub contents API URL">
      </div>
      <div class="setting-field" style="margin-bottom: 5px;">
        <label>Auth Token (Optional, local only)</label>
        <input type="password" class="setting-input" id="cfgPublishToken" placeholder="Leave blank if public/unauthenticated">
      </div>
      <div style="display: flex; gap: 4px;">
        <button class="btn-sort" style="flex: 1;" onclick="applySyncConfig(true)">💾 Save Sync</button>
        <button class="btn-sort" style="flex: 1;" onclick="exportTimestampsJson()">📤 Export JSON</button>
        <button class="btn-sort" style="flex: 1;" onclick="pushTimestampsNow()">☁️ Push Now</button>
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
  // Web Audio Synthesizer (Continuous Chime Until Acknowledged)
  // --------------------------------------------------------------------------
  let alertLoopInterval = null;
  let currentAlertSig = null;
  let acknowledgedAlertSig = null;

  function playAlertSound() {
    if (!isSoundEnabled) return;
    try {
      const audioCtx = new (window.AudioContext || window.webkitAudioContext)();
      const osc = audioCtx.createOscillator();
      const gain = audioCtx.createGain();
      osc.type = 'sine';
      osc.frequency.setValueAtTime(587.33, audioCtx.currentTime); // D5
      osc.frequency.exponentialRampToValueAtTime(880, audioCtx.currentTime + 0.15); // A5
      gain.gain.setValueAtTime(0.22, audioCtx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.001, audioCtx.currentTime + 0.45);
      osc.connect(gain);
      gain.connect(audioCtx.destination);
      osc.start();
      osc.stop(audioCtx.currentTime + 0.45);
    } catch(e) {
      console.warn('Audio synthesis unavailable:', e);
    }
  }

  function startContinuousAlert() {
    if (!isSoundEnabled) return;
    if (alertLoopInterval) return; // already ringing
    playAlertSound();
    alertLoopInterval = setInterval(() => {
      if (!isSoundEnabled || currentAlertSig === acknowledgedAlertSig) {
        stopContinuousAlert();
        return;
      }
      playAlertSound();
    }, 2500);
  }

  function stopContinuousAlert() {
    if (alertLoopInterval) {
      clearInterval(alertLoopInterval);
      alertLoopInterval = null;
    }
  }

  function acknowledgeAlert(e) {
    if (e) e.stopPropagation();
    acknowledgedAlertSig = currentAlertSig;
    stopContinuousAlert();
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
      if (currentAlertSig && currentAlertSig !== acknowledgedAlertSig) {
        startContinuousAlert();
      }
    } else {
      btn.innerText = '🔕';
      btn.classList.remove('alert-on');
      btn.title = 'Late Synop Audio Alert: MUTED';
      stopContinuousAlert();
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
  // Dynamic Polling & Shared Timestamp Sync Controls
  // --------------------------------------------------------------------------
  let currentPollingMode = 'dynamic';

  function hydratePollingAndSyncUI(data) {
    const ps = data.polling_settings || {};
    currentPollingMode = ps.mode || 'dynamic';
    document.getElementById('modeDynamicBtn').classList.toggle('active', currentPollingMode === 'dynamic');
    document.getElementById('modeFixedBtn').classList.toggle('active', currentPollingMode === 'fixed');
    document.getElementById('dynamicControls').style.display = currentPollingMode === 'dynamic' ? 'block' : 'none';
    document.getElementById('fixedControls').style.display = currentPollingMode === 'fixed' ? 'block' : 'none';

    if (ps.window_before_mins !== undefined) document.getElementById('cfgBeforeMins').value = String(ps.window_before_mins);
    if (ps.window_after_mins !== undefined) document.getElementById('cfgAfterMins').value = String(ps.window_after_mins);
    if (ps.active_interval_secs !== undefined) document.getElementById('cfgActiveSecs').value = String(ps.active_interval_secs);
    if (ps.idle_interval_secs !== undefined) document.getElementById('cfgIdleSecs').value = String(ps.idle_interval_secs);
    if (ps.early_exit_on_complete !== undefined) document.getElementById('cfgEarlyExit').checked = Boolean(ps.early_exit_on_complete);

    const fixedSecs = ps.fixed_interval_secs || 60;
    const fixedLbl = fixedSecs < 60 ? `${fixedSecs}s` : `${Math.floor(fixedSecs/60)}m`;
    document.querySelectorAll('#fixedControls .btn-timing').forEach(b => {
      b.classList.toggle('active', b.innerText === fixedLbl);
    });

    const ws = data.window_status || {};
    const targetSecs = ws.target_poll_seconds || 60;
    if (currentScanSecs !== targetSecs) {
      currentScanSecs = targetSecs;
      if (scanRemainingSecs > targetSecs) scanRemainingSecs = targetSecs;
    }

    const timingTag = document.getElementById('timingVal');
    if (timingTag) {
      timingTag.innerText = ws.status_text || (currentPollingMode === 'dynamic' ? 'Dynamic' : fixedLbl);
    }

    // Top-right spinner during expectation period
    const spinner = document.getElementById('activePollSpinner');
    if (spinner) {
      spinner.classList.toggle('active', Boolean(ws.is_expectation_window));
      spinner.title = ws.status_text || 'Dynamic Polling Status';
    }

    // Hydrate Sync Info
    const si = data.sync_info || {};
    if (document.getElementById('cfgSyncEnabled')) {
      document.getElementById('cfgSyncEnabled').checked = Boolean(si.enabled !== false);
      if (si.read_url !== undefined) document.getElementById('cfgReadUrl').value = si.read_url || '';
      if (si.publish_url !== undefined) document.getElementById('cfgPublishUrl').value = si.publish_url || '';
      document.getElementById('syncCountTag').innerText = `${si.recorded_count || 0} saved`;
    }
  }

  function setPollingMode(mode) {
    currentPollingMode = mode;
    document.getElementById('modeDynamicBtn').classList.toggle('active', mode === 'dynamic');
    document.getElementById('modeFixedBtn').classList.toggle('active', mode === 'fixed');
    document.getElementById('dynamicControls').style.display = mode === 'dynamic' ? 'block' : 'none';
    document.getElementById('fixedControls').style.display = mode === 'fixed' ? 'block' : 'none';
    applyPollingSettings();
  }

  async function applyPollingSettings() {
    const payload = {
      mode: currentPollingMode,
      window_before_mins: parseInt(document.getElementById('cfgBeforeMins').value, 10),
      window_after_mins: parseInt(document.getElementById('cfgAfterMins').value, 10),
      active_interval_secs: parseInt(document.getElementById('cfgActiveSecs').value, 10),
      idle_interval_secs: parseInt(document.getElementById('cfgIdleSecs').value, 10),
      early_exit_on_complete: document.getElementById('cfgEarlyExit').checked,
    };
    if (window.pywebview && window.pywebview.api) {
      await window.pywebview.api.save_polling_settings(JSON.stringify(payload));
      triggerRefresh();
    }
  }

  async function changeFixedTiming(secs, label) {
    document.querySelectorAll('#fixedControls .btn-timing').forEach(b => {
      b.classList.toggle('active', b.innerText === label);
    });
    currentScanSecs = secs;
    scanRemainingSecs = secs;
    if (window.pywebview && window.pywebview.api) {
      await window.pywebview.api.save_polling_settings(JSON.stringify({ mode: 'fixed', fixed_interval_secs: secs }));
      triggerRefresh();
    }
  }

  async function applySyncConfig(showAlert) {
    const payload = {
      enabled: document.getElementById('cfgSyncEnabled').checked,
      read_url: document.getElementById('cfgReadUrl').value.trim(),
      publish_url: document.getElementById('cfgPublishUrl').value.trim(),
    };
    const tok = document.getElementById('cfgPublishToken').value.trim();
    if (tok) payload.publish_token = tok;
    if (window.pywebview && window.pywebview.api) {
      await window.pywebview.api.save_sync_config(JSON.stringify(payload));
      if (showAlert) alert('Sync settings saved!');
      triggerRefresh();
    }
  }

  async function exportTimestampsJson() {
    if (window.pywebview && window.pywebview.api) {
      const res = JSON.parse(await window.pywebview.api.export_timestamps_json());
      if (res.success) {
        try { await navigator.clipboard.writeText(res.json_text); } catch(e) {}
        alert(`Exported ${res.count} timestamps to:\n${res.path}\n(Also copied to clipboard!)`);
      } else {
        alert('Export failed: ' + (res.error || 'Unknown error'));
      }
    }
  }

  async function pushTimestampsNow() {
    if (window.pywebview && window.pywebview.api) {
      const res = JSON.parse(await window.pywebview.api.push_timestamps_now());
      if (res.success) {
        alert('Publishing timestamps JSON in background!');
      } else {
        alert(res.error || 'Failed to push timestamps.');
      }
    }
  }

  // --------------------------------------------------------------------------
  // Matrix Render & Late Alerts
  // --------------------------------------------------------------------------
  function renderData(data) {
    if (!data || !data.success) return;
    lastData = data;
    stationsOrder = (data.stations || []).map(s => s.id);
    hydratePollingAndSyncUI(data);

    // Check Late Alerts
    const alerts = data.late_alerts || [];
    const banner = document.getElementById('alertBanner');
    const bannerText = document.getElementById('alertBannerText');

    if (alerts.length > 0) {
      const topAlert = alerts[0];
      currentAlertSig = alerts.map(a => `${a.station_id}:${a.hour}:${a.status}`).join('|');
      bannerText.innerText = `⚠️ ${topAlert.station_name} sent Late Synop (${topAlert.hour.slice(0,2)}Z)`;
      banner.classList.add('show');
      if (currentAlertSig !== acknowledgedAlertSig) {
        startContinuousAlert();
      }
    } else {
      currentAlertSig = null;
      acknowledgedAlertSig = null;
      stopContinuousAlert();
      banner.classList.remove('show');
    }

    // Render Station Boxes (3x4 Grid)
    const rowsEl = document.getElementById('matrixRows');
    if (!data.stations || data.stations.length === 0) {
      rowsEl.innerHTML = '<div style="grid-column: 1 / -1; text-align: center; color: var(--text-muted); padding: 30px;">No station data available.</div>';
      return;
    }

    let okStations = 0, earlyStations = 0, lateStations = 0, missingStations = 0;
    let boxesHtml = '';

    data.stations.forEach(st => {
      const slots = st.slots || [];
      let onTimeCount = 0, earlyCount = 0, lateCount = 0, missingCount = 0, expectedCount = 0;
      let dotsHtml = '';

      slots.forEach(slot => {
        let dotCls = 'ms-awaiting';
        if (slot.status === 'ON_TIME') { onTimeCount++; expectedCount++; dotCls = 'ms-on-time'; }
        else if (slot.status === 'EARLY') { earlyCount++; expectedCount++; dotCls = 'ms-early'; }
        else if (slot.status === 'LATE' || slot.status === 'VERY_LATE' || slot.status === 'LATE_OVERDUE') { lateCount++; expectedCount++; dotCls = 'ms-late'; }
        else if (slot.status === 'MISSING') { missingCount++; expectedCount++; dotCls = 'ms-missing'; }
        else if (slot.status === 'NOT_SCHEDULED') { dotCls = 'ms-not-scheduled'; }

        dotsHtml += `<span class="mini-slot ${dotCls}" title="${slot.hour.slice(0,2)}Z: ${slot.badge_text}"></span>`;
      });

      let boxCls = 'box-ok';
      let tagCls = 'tag-ok';
      let tagText = 'OK';

      if (missingCount > 0) {
        boxCls = 'box-missing';
        tagCls = 'tag-missing';
        tagText = `${missingCount} MISS`;
        missingStations++;
      } else if (lateCount > 0) {
        boxCls = 'box-late';
        tagCls = 'tag-late';
        tagText = `${lateCount} LATE`;
        lateStations++;
      } else if (earlyCount > 0) {
        boxCls = 'box-early';
        tagCls = 'tag-early';
        tagText = `${earlyCount} EARLY`;
        earlyStations++;
      } else {
        okStations++;
      }

      const receivedTotal = onTimeCount + earlyCount + lateCount;
      const countText = expectedCount > 0 ? `${receivedTotal}/${expectedCount}` : '0/0';

      boxesHtml += `
        <div class="station-box ${boxCls}" onclick="openDrilldown('${st.id}')" title="${st.name} (${st.id}) - Click for details">
          <div class="box-top">
            <span class="box-id">${st.id}</span>
            <span class="box-status-tag ${tagCls}">${tagText}</span>
          </div>
          <div class="box-name">${st.name}</div>
          <div class="box-bottom">
            <div class="box-dots">${dotsHtml}</div>
            <span class="box-count">${countText}</span>
          </div>
        </div>
      `;
    });

    rowsEl.innerHTML = boxesHtml;

    const legendEl = document.getElementById('legendCounts');
    if (legendEl) {
      legendEl.innerHTML = `
        <span class="legend-item"><span class="legend-dot dot-ok"></span>${okStations} OK</span>
        <span class="legend-item"><span class="legend-dot dot-early"></span>${earlyStations} Early</span>
        <span class="legend-item"><span class="legend-dot dot-late"></span>${lateStations} Late</span>
        <span class="legend-item"><span class="legend-dot dot-missing"></span>${missingStations} Miss</span>
      `;
    }

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
    const feedEl = document.getElementById('drilldownFeed');
    if (feedEl) feedEl.scrollTop = 0;
  }

  function closeDrilldown() {
    activeDrilldownId = null;
    document.getElementById('viewDrilldown').style.display = 'none';
    document.getElementById('viewSettings').style.display = 'none';
    document.getElementById('viewMatrix').style.display = 'flex';
  }

  function onAlertBannerClick() {
    acknowledgeAlert();
    if (lastData && lastData.late_alerts && lastData.late_alerts.length > 0) {
      openDrilldown(lastData.late_alerts[0].station_id);
    }
  }

  function renderDrilldown(stationId) {
    if (!lastData || !lastData.stations) return;
    const st = lastData.stations.find(s => String(s.id) === String(stationId));
    if (!st) return;

    const slots = st.slots || [];
    let onTimeCount = 0, earlyCount = 0, lateCount = 0, missingCount = 0;
    slots.forEach(slot => {
      if (slot.status === 'ON_TIME') onTimeCount++;
      else if (slot.status === 'EARLY') earlyCount++;
      else if (slot.status === 'LATE' || slot.status === 'VERY_LATE') lateCount++;
      else if (slot.status === 'MISSING') missingCount++;
    });

    document.getElementById('ddStCode').innerText = st.id;
    document.getElementById('ddStName').innerText = st.name;

    const badgeEl = document.getElementById('ddStBadge');
    if (missingCount > 0) {
      badgeEl.innerText = `${missingCount} MISSING`;
      badgeEl.className = 'feed-status-badge badge-missing';
    } else if (lateCount > 0) {
      badgeEl.innerText = `${lateCount} LATE`;
      badgeEl.className = 'feed-status-badge badge-late';
    } else if (earlyCount > 0) {
      badgeEl.innerText = `${earlyCount} EARLY`;
      badgeEl.className = 'feed-status-badge badge-early';
    } else {
      badgeEl.innerText = 'ALL NORMAL';
      badgeEl.className = 'feed-status-badge badge-on-time';
    }

    const summaryEl = document.getElementById('ddSummaryBar');
    if (summaryEl) {
      summaryEl.innerHTML = `
        <div class="dd-stat-chips">
          <span class="dd-chip badge-on-time">${onTimeCount} OK</span>
          <span class="dd-chip badge-early">${earlyCount} Early</span>
          <span class="dd-chip badge-late">${lateCount} Late</span>
          <span class="dd-chip badge-missing">${missingCount} Miss</span>
        </div>
        <span>${lastData.source || 'Live'}</span>
      `;
    }

    const feedEl = document.getElementById('drilldownFeed');
    let feedHtml = '';

    // Reverse chronological order: 21Z -> 18Z -> 15Z -> 12Z -> 09Z -> 06Z -> 03Z -> 00Z
    const reversedSlots = [...slots].reverse();

    reversedSlots.forEach(slot => {
      let badgeClass = 'badge-awaiting';
      let cardClass = 'card-awaiting';
      if (slot.status === 'ON_TIME') { badgeClass = 'badge-on-time'; cardClass = 'card-ok'; }
      else if (slot.status === 'EARLY') { badgeClass = 'badge-early'; cardClass = 'card-early'; }
      else if (slot.status === 'LATE' || slot.status === 'VERY_LATE') { badgeClass = 'badge-late'; cardClass = 'card-late'; }
      else if (slot.status === 'MISSING') { badgeClass = 'badge-missing'; cardClass = 'card-missing'; }

      const transLabel = slot.duplicate_badge || (slot.transmission_count > 1 ? `Collective Echo (${slot.transmission_count})` : 'Single Transmission');
      const rawSynop = slot.raw_synop || (slot.received ? 'SYNOP received but text unavailable.' : 'Pending observation window.');
      let timingInfo = 'Awaiting schedule';
      if (slot.received) {
        if (slot.first_seen_time) {
          const fsDelta = (slot.first_seen_delta !== null && slot.first_seen_delta !== undefined)
            ? ` (${slot.first_seen_delta >= 0 ? '+' : ''}${slot.first_seen_delta}m)`
            : '';
          timingInfo = `Seen ${slot.first_seen_time}${fsDelta}`;
        } else {
          const deltaStr = (slot.delta_minutes !== null && slot.delta_minutes !== undefined)
            ? ` (${slot.delta_minutes >= 0 ? '+' : ''}${slot.delta_minutes}m)`
            : '';
          timingInfo = slot.filing_time ? `Filed ${slot.filing_time}${deltaStr}` : `Transmissions: ${slot.transmission_count}${deltaStr}`;
        }
      } else if (slot.status === 'MISSING') {
        timingInfo = 'Not received within +30m SLA';
      }

      feedHtml += `
        <div class="feed-card ${cardClass}">
          <div class="feed-card-top">
            <div class="feed-obs-time">
              <span class="feed-hour-chip">${slot.label}</span>
              <span>${slot.hour.slice(0,2)}:00 UTC</span>
            </div>
            <span class="feed-status-badge ${badgeClass}">${slot.badge_text}</span>
          </div>
          <div class="feed-meta-row">
            <span>${timingInfo}</span>
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
    const spinner = document.getElementById('activePollSpinner');
    if (spinner) spinner.classList.add('fetching');
    if (window.pywebview && window.pywebview.api) {
      try {
        const raw = await window.pywebview.api.get_data();
        const data = JSON.parse(raw);
        renderData(data);
      } catch (e) {
        console.error('Failed to load data:', e);
      }
    }
    if (spinner) spinner.classList.remove('fetching');
  }

  async function triggerRefresh() {
    const btn = document.getElementById('btnRefresh');
    const spinner = document.getElementById('activePollSpinner');
    btn.classList.add('rotating');
    if (spinner) spinner.classList.add('fetching');
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
    setTimeout(() => {
      btn.classList.remove('rotating');
      if (spinner) spinner.classList.remove('fetching');
    }, 600);
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
