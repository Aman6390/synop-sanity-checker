"""
IMD SYNOP Monitor & SLA Sanity Checker
Streamlit Web Application for GTS Weather Bulletin Monitoring and Timeliness Verification.
"""

from __future__ import annotations

import os
import sys
import json
import re
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any, Optional

import streamlit as st

# Ensure backend modules can be imported directly
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

# -----------------------------------------------------------------------------
# Streamlit Page Configuration
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="IMD SYNOP Monitor & SLA Sanity Checker",
    page_icon="🌤️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom Styling (Apple Design-inspired, clean hierarchy, sleek pills)
st.markdown(
    """
    <style>
    /* Clean layout styling */
    .block-container {
        padding-top: 1.8rem;
        padding-bottom: 2rem;
        max-width: 96%;
    }
    .stMetric {
        background-color: rgba(255, 255, 255, 0.05);
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 12px;
        padding: 10px 16px;
    }
    .badge-green {
        background-color: rgba(16, 185, 129, 0.15);
        color: #10B981;
        border: 1px solid rgba(16, 185, 129, 0.3);
        border-radius: 9999px;
        padding: 3px 10px;
        font-weight: 600;
        font-size: 0.75rem;
        display: inline-block;
    }
    .badge-yellow {
        background-color: rgba(245, 158, 11, 0.15);
        color: #F59E0B;
        border: 1px solid rgba(245, 158, 11, 0.3);
        border-radius: 9999px;
        padding: 3px 10px;
        font-weight: 600;
        font-size: 0.75rem;
        display: inline-block;
    }
    .badge-red {
        background-color: rgba(239, 68, 68, 0.15);
        color: #EF4444;
        border: 1px solid rgba(239, 68, 68, 0.3);
        border-radius: 9999px;
        padding: 3px 10px;
        font-weight: 600;
        font-size: 0.75rem;
        display: inline-block;
    }
    .badge-gray {
        background-color: rgba(156, 163, 175, 0.15);
        color: #9CA3AF;
        border: 1px solid rgba(156, 163, 175, 0.2);
        border-radius: 9999px;
        padding: 3px 10px;
        font-size: 0.75rem;
        display: inline-block;
    }
    .slot-pill {
        display: inline-block;
        padding: 4px 8px;
        border-radius: 8px;
        font-family: monospace;
        font-size: 0.78rem;
        font-weight: 600;
        text-align: center;
        margin: 2px;
    }
    .slot-green { background-color: #10B981; color: white; }
    .slot-yellow { background-color: #F59E0B; color: white; }
    .slot-red { background-color: #EF4444; color: white; }
    .slot-gray { background-color: rgba(156, 163, 175, 0.25); color: #888; }
    .slot-awaiting { background-color: rgba(100, 116, 139, 0.2); color: #94A3B8; border: 1px dashed rgba(100, 116, 139, 0.4); }
    </style>
    """,
    unsafe_allow_html=True,
)

# -----------------------------------------------------------------------------
# State Management & Helpers
# -----------------------------------------------------------------------------
def load_stations_config() -> List[Dict[str, Any]]:
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("stations", [])
        except Exception:
            pass
    return []

def save_stations_config(stations: List[Dict[str, Any]]) -> None:
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump({"stations": stations}, f, indent=2)

if "stations_config" not in st.session_state:
    st.session_state["stations_config"] = load_stations_config()

if "parsed_data" not in st.session_state:
    st.session_state["parsed_data"] = {"synops_by_station": {}, "activity_by_station": {}, "total_bulletins": 0}

if "last_fetch_time" not in st.session_state:
    st.session_state["last_fetch_time"] = None

if "last_fetch_source" not in st.session_state:
    st.session_state["last_fetch_source"] = "None"

def perform_data_fetch() -> tuple[bool, str]:
    fetcher = AMSSFetcher()
    raw_text = None
    source = "AMSS Delhi Live"

    try:
        raw_text = fetcher.fetch_live_data()
    except Exception as e:
        # Fallback to local dump
        if os.path.exists(DUMP_PATH):
            with open(DUMP_PATH, "r", encoding="utf-8", errors="ignore") as f:
                raw_text = f.read()
            source = "Local GTS Dump (AMSS Backup)"
        else:
            return False, f"Failed to fetch live feed: {e}"

    if raw_text:
        parsed = GTSParser.parse_bulletin_stream(raw_text)
        st.session_state["parsed_data"] = parsed
        st.session_state["last_fetch_time"] = datetime.now(timezone.utc)
        st.session_state["last_fetch_source"] = source
        return True, f"Successfully loaded from {source} ({parsed['total_bulletins']} bulletins parsed)."
    return False, "Empty feed received."

# Initial load if unpopulated
if not st.session_state["last_fetch_time"]:
    perform_data_fetch()

# -----------------------------------------------------------------------------
# Header Bar with Live UTC / IST Clocks & Dynamic Window
# -----------------------------------------------------------------------------
now_utc = datetime.now(timezone.utc)
now_ist = now_utc + timedelta(hours=5, minutes=30)
window_status = get_synoptic_window_status(now_utc)

col_title, col_status = st.columns([2.5, 1.5])

with col_title:
    st.title("🌤️ IMD SYNOP SLA & Sanity Monitor")
    st.caption("Live GTS bulletin ingestion from AMSS Delhi • WMO FM-12 Code Standard • Two-Tier NNNN Deduplication")

with col_status:
    st.markdown(
        f"""
        <div style="text-align: right; margin-top: 8px;">
            <span style="font-family: monospace; font-size: 1rem; font-weight: 600;">
                {now_utc.strftime('%H:%M:%S')} UTC &nbsp;•&nbsp; {now_ist.strftime('%H:%M:%S')} IST
            </span><br/>
            <span class="{'badge-green' if window_status['is_active'] else 'badge-gray'}" style="margin-top: 4px;">
                {window_status['status_text']}
            </span>
            <div style="font-size: 0.75rem; color: #888; margin-top: 4px;">
                Source: <strong>{st.session_state['last_fetch_source']}</strong> ({st.session_state['last_fetch_time'].strftime('%H:%M:%S UTC') if st.session_state['last_fetch_time'] else 'Pending'})
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

# -----------------------------------------------------------------------------
# Evaluate All Stations
# -----------------------------------------------------------------------------
synops_by_station = st.session_state["parsed_data"].get("synops_by_station", {})
evaluated_stations = []

for stn_cfg in st.session_state["stations_config"]:
    stn_id = stn_cfg["id"]
    reps = synops_by_station.get(stn_id, [])
    eval_res = SLAEngine.evaluate_station_timeliness(
        station_config=stn_cfg,
        received_synops=reps,
        current_utc=now_utc,
    )
    evaluated_stations.append(eval_res)

# Compute Top Level KPI Counts
total_monitored = len(evaluated_stations)
total_red = sum(1 for s in evaluated_stations if s["overall_severity"] == "red")
total_yellow = sum(1 for s in evaluated_stations if s["overall_severity"] == "yellow")
total_green = sum(1 for s in evaluated_stations if s["overall_severity"] == "green")
total_on_time_slots = sum(s["counts"]["on_time"] for s in evaluated_stations)
total_missing_slots = sum(s["counts"]["missing"] for s in evaluated_stations)
total_late_slots = sum(s["counts"]["late"] for s in evaluated_stations)

# -----------------------------------------------------------------------------
# Metric Cards
# -----------------------------------------------------------------------------
m_col1, m_col2, m_col3, m_col4 = st.columns(4)

with m_col1:
    st.metric(
        label="Monitored Stations",
        value=f"{total_monitored}",
        help="Configured active weather stations in the observation watchlist.",
    )

with m_col2:
    st.metric(
        label="All Normal (On Time)",
        value=f"{total_green}",
        delta=f"{total_on_time_slots} On-Time Slots",
        delta_color="normal",
    )

with m_col3:
    st.metric(
        label="Extreme Alerts",
        value=f"{total_red}",
        delta=f"-{total_missing_slots + total_late_slots} Delays/Missing" if (total_missing_slots + total_late_slots) > 0 else "None",
        delta_color="inverse",
    )

with m_col4:
    st.metric(
        label="Active Window Polling",
        value=f"Every {window_status['target_poll_seconds'] // 60}m",
        delta="Rapid Active" if window_status["is_active"] else "Resting",
        delta_color="normal" if window_status["is_active"] else "off",
    )

st.divider()

# -----------------------------------------------------------------------------
# Filter and Search Bar
# -----------------------------------------------------------------------------
f_col1, f_col2, f_col3, f_col4 = st.columns([1.5, 1.2, 2.0, 0.8])

with f_col1:
    status_tab = st.selectbox(
        "Filter by Status",
        options=["All Stations", "🚨 Needs Attention Only", "✅ All Normal Only", "⚡ Early Only"],
        index=0,
    )

with f_col2:
    available_regions = ["All Regions"] + sorted(list(set(s.get("region", "") for s in evaluated_stations if s.get("region"))))
    selected_region = st.selectbox("Region", options=available_regions, index=0)

with f_col3:
    search_query = st.text_input("Search Station ID or Name", placeholder="e.g. 42027 or Srinagar").strip().lower()

with f_col4:
    st.write("")
    st.write("")
    if st.button("🔄 Fetch Now", use_container_width=True):
        with st.spinner("Fetching AMSS Delhi feed..."):
            ok, msg = perform_data_fetch()
            if ok:
                st.success(msg)
                st.rerun()
            else:
                st.error(msg)

# Apply Filters
filtered_stations = evaluated_stations

if status_tab == "🚨 Needs Attention Only":
    filtered_stations = [s for s in filtered_stations if s["overall_severity"] == "red"]
elif status_tab == "✅ All Normal Only":
    filtered_stations = [s for s in filtered_stations if s["overall_severity"] == "green"]
elif status_tab == "⚡ Early Only":
    filtered_stations = [s for s in filtered_stations if s["overall_severity"] == "yellow"]

if selected_region != "All Regions":
    filtered_stations = [s for s in filtered_stations if s.get("region") == selected_region]

if search_query:
    filtered_stations = [
        s for s in filtered_stations
        if search_query in s["station_id"].lower() or search_query in s["station_name"].lower()
    ]

# Sort so stations needing attention appear at the very top
filtered_stations.sort(key=lambda s: 0 if s["overall_severity"] == "red" else (1 if s["overall_severity"] == "yellow" else 2))

st.markdown(f"**Showing {len(filtered_stations)} of {total_monitored} Stations**")

# -----------------------------------------------------------------------------
# Station Cards & Observation Timeline
# -----------------------------------------------------------------------------
if not filtered_stations:
    st.info("No stations matched the selected filter.")

for stn in filtered_stations:
    stn_id = stn["station_id"]
    stn_name = stn["station_name"]
    state_reg = f"{stn.get('state', '')} • {stn.get('region', '')}".strip(" •")
    req_count = len(stn.get("required_hours", SYNOPTIC_HOURS))
    severity = stn["overall_severity"]

    # Border color matching severity
    border_color = "#10B981" if severity == "green" else ("#F59E0B" if severity == "yellow" else "#EF4444")
    badge_html = (
        '<span class="badge-green">ALL NORMAL</span>' if severity == "green"
        else ('<span class="badge-yellow">EARLY ONLY</span>' if severity == "yellow"
        else f'<span class="badge-red">EXTREME ALERT ({stn["status_desc"]})</span>')
    )

    with st.container():
        card_col_info, card_col_timeline = st.columns([1.5, 2.5])

        with card_col_info:
            st.markdown(
                f"""
                <div style="padding-top: 4px;">
                    <span style="font-family: monospace; font-size: 1.15rem; font-weight: 700; color: #0284C7;">{stn_id}</span>
                    <span style="font-size: 1.15rem; font-weight: 700; margin-left: 8px;">{stn_name}</span>
                    <div style="font-size: 0.8rem; color: #888; margin-top: 2px;">{state_reg} • {req_count} synops/day</div>
                    <div style="margin-top: 6px;">{badge_html}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        with card_col_timeline:
            # Build 8-slot horizontal pill track
            pills_html = []
            for h in SYNOPTIC_HOURS:
                slot = stn["slots"].get(h, {})
                label = f"{h[:2]}Z"
                status = slot.get("status", "NOT_SCHEDULED")

                if status == "NOT_SCHEDULED":
                    cls = "slot-gray"
                    tooltip = "Not Scheduled"
                elif status in ("ON_TIME", "EARLY"):
                    cls = "slot-green" if status == "ON_TIME" else "slot-yellow"
                    delta = f"{slot.get('delta_minutes', 0):+.0f}m"
                    dup = f" ({slot.get('duplicate_badge')})" if slot.get("duplicate_count", 0) > 0 else ""
                    tooltip = f"{slot.get('badge_text')} {delta}{dup}"
                elif status in ("LATE", "VERY_LATE", "MISSING", "LATE_OVERDUE"):
                    cls = "slot-red"
                    tooltip = slot.get("badge_text", "Late")
                else:
                    cls = "slot-awaiting"
                    tooltip = "Awaiting"

                pills_html.append(f'<span class="slot-pill {cls}" title="{tooltip}">{label}</span>')

            st.markdown(
                f"""
                <div style="margin-top: 10px;">
                    {" ".join(pills_html)}
                    <div style="font-size: 0.72rem; color: #888; margin-top: 4px;">
                        Timeline: 00:00 UTC to 21:00 UTC Observation Cycles
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        # Expandable Drawer for detailed report audit & duplicate inspector
        with st.expander(f"Inspect Station {stn_id} Details & Audit Trail"):
            tab_synop, tab_activity = st.tabs(["Surface SYNOP Reports (AAXX)", "All GTS Bulletins & Remarks"])

            with tab_synop:
                for h in SYNOPTIC_HOURS:
                    slot = stn["slots"].get(h, {})
                    if not slot.get("received") and slot.get("status") == "NOT_SCHEDULED":
                        continue

                    hour_label = f"{slot.get('utc_label')} ({slot.get('ist_label')})"
                    st.markdown(f"**Observation Hour:** `{hour_label}` — Status: **{slot.get('badge_text')}**")

                    if slot.get("received") and slot.get("primary_report"):
                        prep = slot["primary_report"]
                        meta_text = f"Origin: `{prep.get('originating_center')}` • Bulletin: `{prep.get('bulletin_id')}` • Seq: `{prep.get('seq_num')}` • Timestamp: `{prep.get('header_timestamp')}`"
                        st.caption(meta_text)

                        # Highlight duplicate badge and description if multiple transmissions were reconciled
                        if slot.get("duplicate_count", 0) > 0:
                            st.info(f"ℹ️ **{slot.get('duplicate_badge')}**: {slot.get('duplicate_description')} *(SLA scored on earliest Seq {slot.get('earliest_report', {}).get('seq_num')})*")

                        st.code(prep.get("raw_text", ""), language="text")

                        # If duplicates exist, show the full audit trail
                        if slot.get("duplicate_count", 0) > 0 and slot.get("reports"):
                            with st.expander(f"View All {slot['transmission_count']} Transmissions (Audit Trail)"):
                                for r in slot["reports"]:
                                    tag = " (Authoritative Display)" if r.get("is_primary") else ""
                                    coll_tag = " [Collective]" if r.get("is_collective") else " [Individual]"
                                    st.markdown(f"**Transmission #{r.get('transmission_index')}**{tag}{coll_tag} — Bulletin `{r.get('bulletin_id')}` (Seq `{r.get('seq_num')}`) via `{r.get('originating_center')}`")
                                    st.code(r.get("raw_text", ""), language="text")
                    else:
                        st.caption(f"No synop received. ({slot.get('status')})")
                    st.divider()

            with tab_activity:
                act_list = st.session_state["parsed_data"].get("activity_by_station", {}).get(stn_id, [])
                if act_list:
                    st.markdown(f"Found **{len(act_list)}** related bulletin items for `{stn_id}`:")
                    for a in act_list:
                        st.markdown(f"• **{a.get('type')}** | Bulletin `{a.get('bulletin_id')}` (Seq `{a.get('seq_num')}`) via `{a.get('originating_center')}`")
                        st.code(a.get("raw_text", ""), language="text")
                else:
                    st.caption("No non-AAXX activity recorded in this bulletin stream.")

    st.markdown("<hr style='margin: 8px 0; border: none; border-top: 1px solid rgba(255,255,255,0.08);'/>", unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# Sidebar: Watchlist Configuration & Settings
# -----------------------------------------------------------------------------
with st.sidebar:
    st.header("⚙️ Station Watchlist")
    st.caption("Manage monitored IMD stations and customized synoptic observation schedules.")

    with st.expander("➕ Add New Station", expanded=False):
        new_id = st.text_input("5-Digit WMO ID", max_chars=5, placeholder="e.g. 42165").strip()
        new_name = st.text_input("Station Name", placeholder="e.g. New Delhi").strip()
        new_state = st.text_input("State / UT", placeholder="e.g. Delhi").strip()
        new_region = st.selectbox("Region", options=["North", "Northwest", "Central", "East", "Northeast", "South", "West", "Island"])

        st.markdown("**Required Observation Hours:**")
        req_opts = st.multiselect(
            "Select active synoptic cycles",
            options=SYNOPTIC_HOURS,
            default=SYNOPTIC_HOURS,
            format_func=lambda x: f"{x[:2]}:00 UTC",
        )

        if st.button("Add to Watchlist", use_container_width=True):
            if not new_id or not re.match(r"^\d{5}$", new_id):
                st.error("Please enter a valid 5-digit station code.")
            elif any(s["id"] == new_id for s in st.session_state["stations_config"]):
                st.error("Station code already exists in watchlist.")
            else:
                new_stn = {
                    "id": new_id,
                    "name": new_name or f"Station {new_id}",
                    "state": new_state,
                    "region": new_region,
                    "required_hours": req_opts or SYNOPTIC_HOURS,
                }
                st.session_state["stations_config"].append(new_stn)
                save_stations_config(st.session_state["stations_config"])
                st.success(f"Added {new_name} ({new_id}) successfully!")
                st.rerun()

    with st.expander("📋 Manage Existing Stations", expanded=False):
        for idx, s in enumerate(st.session_state["stations_config"]):
            col_s_name, col_s_del = st.columns([3, 1])
            with col_s_name:
                st.write(f"**{s['name']}** (`{s['id']}`)")
                st.caption(f"{len(s.get('required_hours', SYNOPTIC_HOURS))} synops/day")
            with col_s_del:
                if st.button("🗑️", key=f"del_{s['id']}"):
                    st.session_state["stations_config"].pop(idx)
                    save_stations_config(st.session_state["stations_config"])
                    st.rerun()

    st.divider()

    st.subheader("🌐 Ingestion Settings")
    st.write(f"**Dynamic Window:** `{'Enabled' if window_status['is_active'] else 'Idle'}`")
    st.caption("Active windows (HH-1:45 to HH:30 UTC) trigger rapid 1-minute checks; resting periods check every 30m.")

    # Offline file upload fallback
    st.markdown("**Manual Bulletin Upload:**")
    uploaded_file = st.file_uploader("Upload GTS `sendata.txt` or bulletin dump", type=["txt"])
    if uploaded_file is not None:
        try:
            content = uploaded_file.read().decode("utf-8", errors="ignore")
            parsed = GTSParser.parse_bulletin_stream(content)
            st.session_state["parsed_data"] = parsed
            st.session_state["last_fetch_time"] = datetime.now(timezone.utc)
            st.session_state["last_fetch_source"] = f"Uploaded ({uploaded_file.name})"
            st.success("Uploaded file parsed successfully!")
            st.rerun()
        except Exception as e:
            st.error(f"Error parsing uploaded file: {e}")
