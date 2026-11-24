import re
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any, Optional

SYNOPTIC_HOURS = ["0000", "0300", "0600", "0900", "1200", "1500", "1800", "2100"]

# Hour to standard labels
HOUR_LABELS = {
    "0000": {"utc": "00:00 UTC", "ist": "05:30 IST", "display": "00:00 UTC / 05:30 IST"},
    "0300": {"utc": "03:00 UTC", "ist": "08:30 IST", "display": "03:00 UTC / 08:30 IST"},
    "0600": {"utc": "06:00 UTC", "ist": "11:30 IST", "display": "06:00 UTC / 11:30 IST"},
    "0900": {"utc": "09:00 UTC", "ist": "14:30 IST", "display": "09:00 UTC / 14:30 IST"},
    "1200": {"utc": "12:00 UTC", "ist": "17:30 IST", "display": "12:00 UTC / 17:30 IST"},
    "1500": {"utc": "15:00 UTC", "ist": "20:30 IST", "display": "15:00 UTC / 20:30 IST"},
    "1800": {"utc": "18:00 UTC", "ist": "23:30 IST", "display": "18:00 UTC / 23:30 IST"},
    "2100": {"utc": "21:00 UTC", "ist": "02:30 IST (+1d)", "display": "21:00 UTC / 02:30 IST (+1d)"},
}

def get_synoptic_window_status(now_utc: Optional[datetime] = None) -> Dict[str, Any]:
    """
    Calculates whether current UTC time is inside the 45-minute Active Synoptic Window
    (from HH-1:45 UTC to HH:30 UTC for all 8 synoptic observation hours).
    - Inside Window: 1-minute high-frequency polling.
    - Outside Window: relaxed polling (30 minutes) with countdown to next active window.
    """
    if now_utc is None:
        now_utc = datetime.now(timezone.utc)

    synoptic_hours = [0, 3, 6, 9, 12, 15, 18, 21]
    candidates = []
    for day_offset in [-1, 0, 1]:
        base_date = (now_utc + timedelta(days=day_offset)).date()
        for h in synoptic_hours:
            obs_dt = datetime(base_date.year, base_date.month, base_date.day, h, 0, tzinfo=timezone.utc)
            w_start = obs_dt - timedelta(minutes=15)
            w_end = obs_dt + timedelta(minutes=30)
            candidates.append((obs_dt, w_start, w_end, f"{h:02d}:00 UTC"))

    # Check if currently inside active window
    for obs_dt, w_start, w_end, cycle_name in candidates:
        if w_start <= now_utc <= w_end:
            mins_left = max(0, int((w_end - now_utc).total_seconds() / 60))
            end_str = w_end.strftime("%H:%M UTC")
            return {
                "is_active": True,
                "cycle": cycle_name,
                "target_poll_seconds": 60,
                "status_text": f"Active Window ({cycle_name})",
                "description": f"Polling every 1m until {end_str} ({mins_left}m remaining)",
                "minutes_remaining": mins_left
            }

    # Outside active window -> find next upcoming window
    future_windows = [c for c in candidates if c[1] > now_utc]
    if future_windows:
        obs_dt, next_start, _, next_cycle = min(future_windows, key=lambda x: x[1])
        mins_until = max(0, int((next_start - now_utc).total_seconds() / 60))
        start_str = next_start.strftime("%H:%M UTC")
        return {
            "is_active": False,
            "cycle": next_cycle,
            "target_poll_seconds": 1800,
            "status_text": f"Idle Window (Next: {next_cycle})",
            "description": f"Polling relaxed (30m). Next 1m active window in {mins_until}m ({start_str})",
            "minutes_until_next": mins_until
        }

    return {
        "is_active": False,
        "cycle": "00:00 UTC",
        "target_poll_seconds": 1800,
        "status_text": "Normal Polling",
        "description": "Standard polling active (30m)",
        "minutes_until_next": 0
    }


def normalize_synop_text(text: str) -> str:
    """Normalize raw SYNOP string by stripping leading AAXX header, collapsing spaces, and stripping trailing '='."""
    t = re.sub(r'^\s*AAXX\s+\d{5}\s*', '', text)
    t = re.sub(r'\s+', ' ', t).strip().rstrip('=').strip()
    return t


class SLAEngine:
    """
    Evaluates timeliness and SLA status for each synoptic hour per station.
    Features 2-Tier Inter-Bulletin Reconciliation:
      - Uses EARLIEST transmission for Timeliness SLA score (giving observer on-time credit).
      - Uses LATEST / AMENDED transmission for primary weather data display.
      - Flags Relay Echoes, Collective Confirmations, and Corrected (COR) revisions.
    """

    @classmethod
    def evaluate_station_timeliness(
        cls,
        station_config: Dict[str, Any],
        received_synops: List[Dict[str, Any]],
        current_utc: Optional[datetime] = None
    ) -> Dict[str, Any]:
        if current_utc is None:
            current_utc = datetime.now(timezone.utc)

        required_hours = set(station_config.get("required_hours", SYNOPTIC_HOURS))

        # Group received synops by observation_hour
        synops_by_hour: Dict[str, List[Dict[str, Any]]] = {}
        for s in received_synops:
            h = s.get("observation_hour", "0000")
            if h not in synops_by_hour:
                synops_by_hour[h] = []
            synops_by_hour[h].append(s)

        slot_evaluations: Dict[str, Any] = {}
        counts = {
            "on_time": 0,
            "early": 0,
            "late": 0,
            "missing": 0,
            "awaiting": 0,
            "not_scheduled": 0
        }

        for hour in SYNOPTIC_HOURS:
            label_info = HOUR_LABELS.get(hour, {"utc": hour, "ist": "", "display": hour})
            is_required = hour in required_hours

            if not is_required:
                slot_evaluations[hour] = {
                    "hour": hour,
                    "label": label_info["display"],
                    "utc_label": label_info["utc"],
                    "ist_label": label_info["ist"],
                    "status": "NOT_SCHEDULED",
                    "severity": "muted",
                    "badge_text": "Not Scheduled",
                    "received": False,
                    "transmission_count": 0,
                    "duplicate_count": 0,
                    "duplicate_type": "NONE",
                    "duplicate_badge": "",
                    "duplicate_description": "",
                    "has_discrepancy": False,
                    "reports": []
                }
                counts["not_scheduled"] += 1
                continue

            reports = synops_by_hour.get(hour, [])
            trans_count = len(reports)

            # Slot time on current day
            hour_int = int(hour[:2])
            slot_time = current_utc.replace(hour=hour_int, minute=0, second=0, microsecond=0)

            if trans_count > 0:
                # -------------------------------------------------------------
                # Tier 2 Inter-Bulletin Deduplication & Reconciliation
                # -------------------------------------------------------------
                earliest_report = reports[0]
                latest_report = reports[-1]

                # Check weather group text equivalence across transmissions
                base_norm = normalize_synop_text(earliest_report.get("raw_text", ""))
                all_identical = all(
                    normalize_synop_text(r.get("raw_text", "")) == base_norm
                    for r in reports
                )

                if trans_count == 1:
                    duplicate_type = "NONE"
                    duplicate_badge = "Single Transmission"
                    duplicate_description = "Single clean observation received."
                    has_discrepancy = False
                    primary_report = earliest_report
                elif all_identical:
                    has_collective = any(r.get("is_collective") for r in reports)
                    has_individual = any(not r.get("is_collective") for r in reports)
                    if has_collective and has_individual:
                        duplicate_type = "ECHO"
                        duplicate_badge = "Collective Echo"
                        duplicate_description = f"{trans_count} transmissions: Verified identical across individual and regional collective bulletins."
                    else:
                        duplicate_type = "ECHO"
                        duplicate_badge = "Relay Echo"
                        duplicate_description = f"{trans_count} identical transmissions relayed over GTS."
                    has_discrepancy = False
                    primary_report = latest_report
                else:
                    # Content differed between transmissions!
                    has_cor = any(r.get("is_correction") for r in reports) or any("COR" in r.get("raw_text", "") for r in reports)
                    if has_cor:
                        duplicate_type = "CORRECTION"
                        duplicate_badge = "Amended (COR)"
                        duplicate_description = f"Station observation corrected in subsequent bulletin (Seq {latest_report.get('seq_num')})."
                    else:
                        duplicate_type = "REVISED"
                        duplicate_badge = "Data Discrepancy"
                        duplicate_description = f"Weather values differ between transmission Seq {earliest_report.get('seq_num', '1')} and Seq {latest_report.get('seq_num', '2')}."
                    has_discrepancy = True
                    primary_report = latest_report  # Display latest corrected data

                # -------------------------------------------------------------
                # SLA Timeliness: Evaluated on EARLIEST received transmission!
                # -------------------------------------------------------------
                ht = earliest_report.get("header_timestamp", "")
                if len(ht) >= 6:
                    t_day = int(ht[:2])
                    t_hour = int(ht[2:4])
                    t_min = int(ht[4:6])
                    try:
                        receipt_time = current_utc.replace(day=t_day, hour=t_hour, minute=t_min, second=0, microsecond=0)
                    except ValueError:
                        receipt_time = slot_time
                else:
                    receipt_time = slot_time

                delta_minutes = (receipt_time - slot_time).total_seconds() / 60.0

                if delta_minutes < 0:
                    status = "EARLY"
                    severity = "yellow"
                    badge_text = "Early (Still OK)"
                    counts["early"] += 1
                elif 0 <= delta_minutes <= 15:
                    status = "ON_TIME"
                    severity = "green"
                    badge_text = "On Time"
                    counts["on_time"] += 1
                elif 15 < delta_minutes <= 30:
                    status = "LATE"
                    severity = "red"
                    badge_text = "Late (Extreme Red)"
                    counts["late"] += 1
                else:
                    status = "VERY_LATE"
                    severity = "red"
                    badge_text = f"Very Late (+{int(delta_minutes)}m)"
                    counts["late"] += 1

                # Enrich reports with index labels for UI inspection
                enriched_reports = []
                for idx, r in enumerate(reports):
                    enriched_r = dict(r)
                    enriched_r["is_primary"] = (r == primary_report)
                    enriched_r["transmission_index"] = idx + 1
                    enriched_reports.append(enriched_r)

                slot_evaluations[hour] = {
                    "hour": hour,
                    "label": label_info["display"],
                    "utc_label": label_info["utc"],
                    "ist_label": label_info["ist"],
                    "status": status,
                    "severity": severity,
                    "badge_text": badge_text,
                    "received": True,
                    "transmission_count": trans_count,
                    "delta_minutes": round(delta_minutes, 1),
                    "primary_report": primary_report,
                    "earliest_report": earliest_report,
                    "latest_report": latest_report,
                    "duplicate_count": max(0, trans_count - 1),
                    "duplicate_type": duplicate_type,
                    "duplicate_badge": duplicate_badge,
                    "duplicate_description": duplicate_description,
                    "has_discrepancy": has_discrepancy,
                    "reports": enriched_reports
                }
            else:
                # No report received for this required slot
                cutoff_time = slot_time + timedelta(minutes=30)
                if current_utc > cutoff_time:
                    status = "MISSING"
                    severity = "red"
                    badge_text = "Missing / Very Late"
                    counts["missing"] += 1
                elif current_utc >= slot_time:
                    mins_past = int((current_utc - slot_time).total_seconds() / 60.0)
                    if mins_past <= 15:
                        status = "PENDING_GRACE"
                        severity = "yellow"
                        badge_text = f"Pending ({mins_past}m into window)"
                    else:
                        status = "LATE_OVERDUE"
                        severity = "red"
                        badge_text = f"Overdue (+{mins_past}m)"
                        counts["late"] += 1
                else:
                    status = "AWAITING"
                    severity = "neutral"
                    badge_text = "Awaiting"
                    counts["awaiting"] += 1

                slot_evaluations[hour] = {
                    "hour": hour,
                    "label": label_info["display"],
                    "utc_label": label_info["utc"],
                    "ist_label": label_info["ist"],
                    "status": status,
                    "severity": severity,
                    "badge_text": badge_text,
                    "received": False,
                    "transmission_count": 0,
                    "delta_minutes": None,
                    "duplicate_count": 0,
                    "duplicate_type": "NONE",
                    "duplicate_badge": "",
                    "duplicate_description": "",
                    "has_discrepancy": False,
                    "reports": []
                }

        # Overall station status:
        # If any required past slot is missing or late -> RED ALERT
        # Else if early -> YELLOW
        # Else -> GREEN
        if counts["missing"] > 0 or counts["late"] > 0:
            overall_severity = "red"
            overall_status = "EXTREME_RED_ALERT"
            status_desc = f"{counts['missing']} Missing, {counts['late']} Late"
        elif counts["early"] > 0 and counts["on_time"] == 0:
            overall_severity = "yellow"
            overall_status = "YELLOW_ALERT"
            status_desc = f"{counts['early']} Early"
        else:
            overall_severity = "green"
            overall_status = "ALL_NORMAL"
            status_desc = f"{counts['on_time']} On Time"

        return {
            "station_id": station_config["id"],
            "station_name": station_config["name"],
            "state": station_config.get("state", ""),
            "region": station_config.get("region", ""),
            "required_hours": station_config.get("required_hours", SYNOPTIC_HOURS),
            "slots": slot_evaluations,
            "counts": counts,
            "overall_status": overall_status,
            "overall_severity": overall_severity,
            "status_desc": status_desc
        }
