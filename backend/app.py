import json
import os
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any, Optional
from fastapi import FastAPI, HTTPException, BackgroundTasks, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

from gts_parser import GTSParser
from sla_engine import SLAEngine, SYNOPTIC_HOURS, HOUR_LABELS, get_synoptic_window_status
from fetcher import AMSSFetcher

app = FastAPI(
    title="IMD SYNOP Sanity & Timeliness Tracker API",
    description="Real-time monitoring and SLA validation for IMD surface synoptic weather observations.",
    version="1.0.0"
)

# Enable CORS for Vite frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "stations_config.json")
fetcher = AMSSFetcher()

# Global state
state = {
    "parsed_data": {"synops_by_station": {}, "activity_by_station": {}, "total_bulletins": 0},
    "evaluated_stations": [],
    "stations_config": [],
    "poll_interval_seconds": 60,
    "use_dynamic_polling": True,
    "is_polling": True,
    "last_eval_time": None
}

def load_stations_config():
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            state["stations_config"] = data.get("stations", [])
    else:
        state["stations_config"] = []

def save_stations_config():
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump({"stations": state["stations_config"]}, f, indent=2)

def evaluate_all_stations():
    load_stations_config()
    synops_by_station = state["parsed_data"].get("synops_by_station", {})
    now_utc = datetime.now(timezone.utc)
    evaluated = []

    for stn_cfg in state["stations_config"]:
        stn_id = stn_cfg["id"]
        stn_synops = synops_by_station.get(stn_id, [])
        eval_result = SLAEngine.evaluate_station_timeliness(
            station_config=stn_cfg,
            received_synops=stn_synops,
            current_utc=now_utc
        )
        evaluated.append(eval_result)

    state["evaluated_stations"] = evaluated
    state["last_eval_time"] = now_utc

def perform_fetch_and_eval():
    try:
        raw_text = fetcher.fetch_live_data()
        parsed = GTSParser.parse_bulletin_stream(raw_text)
        state["parsed_data"] = parsed
        evaluate_all_stations()
        return True, "Successfully fetched and evaluated."
    except Exception as e:
        # If fetch fails, try evaluating against last cached raw text or local dump if available
        if not state["parsed_data"]["synops_by_station"]:
            dump_file = os.path.join(os.path.dirname(__file__), "..", "sendata_dump.txt")
            if os.path.exists(dump_file):
                with open(dump_file, "r", encoding="utf-8") as f:
                    raw_text = f.read()
                parsed = GTSParser.parse_bulletin_stream(raw_text)
                state["parsed_data"] = parsed
                evaluate_all_stations()
        return False, str(e)

# Background Polling Loop
async def background_poller():
    while True:
        sleep_secs = state["poll_interval_seconds"]
        if state["use_dynamic_polling"]:
            window_info = get_synoptic_window_status()
            sleep_secs = window_info["target_poll_seconds"]

        if state["is_polling"]:
            try:
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, perform_fetch_and_eval)
            except Exception as e:
                pass
        await asyncio.sleep(sleep_secs)

@app.on_event("startup")
async def startup_event():
    load_stations_config()
    # Initial fetch
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, perform_fetch_and_eval)
    # Start poller
    asyncio.create_task(background_poller())

@app.get("/api/status")
def get_status():
    now_utc = datetime.now(timezone.utc)
    now_ist = now_utc + timedelta(hours=5, minutes=30)
    window_info = get_synoptic_window_status(now_utc)
    
    # Summary counters
    total_stns = len(state["evaluated_stations"])
    red_alerts = sum(1 for s in state["evaluated_stations"] if s["overall_severity"] == "red")
    yellow_alerts = sum(1 for s in state["evaluated_stations"] if s["overall_severity"] == "yellow")
    green_all = sum(1 for s in state["evaluated_stations"] if s["overall_severity"] == "green")

    total_missing_slots = sum(s["counts"]["missing"] for s in state["evaluated_stations"])
    total_late_slots = sum(s["counts"]["late"] for s in state["evaluated_stations"])
    total_on_time_slots = sum(s["counts"]["on_time"] for s in state["evaluated_stations"])

    current_poll_rate = window_info["target_poll_seconds"] if state["use_dynamic_polling"] else state["poll_interval_seconds"]

    return {
        "status": fetcher.last_fetch_status,
        "last_fetch_time": fetcher.last_fetch_time.isoformat() if fetcher.last_fetch_time else None,
        "last_fetch_error": fetcher.last_fetch_error,
        "total_bytes": fetcher.total_bytes,
        "total_bulletins": state["parsed_data"].get("total_bulletins", 0),
        "total_stations_monitored": total_stns,
        "red_alert_stations": red_alerts,
        "yellow_alert_stations": yellow_alerts,
        "green_stations": green_all,
        "total_missing_slots": total_missing_slots,
        "total_late_slots": total_late_slots,
        "total_on_time_slots": total_on_time_slots,
        "server_time_utc": now_utc.strftime("%Y-%m-%d %H:%M:%S UTC"),
        "server_time_ist": now_ist.strftime("%Y-%m-%d %H:%M:%S IST"),
        "poll_interval_seconds": current_poll_rate,
        "use_dynamic_polling": state["use_dynamic_polling"],
        "dynamic_window": window_info,
        "is_polling": state["is_polling"]
    }

@app.get("/api/stations")
def get_stations(region: Optional[str] = None, severity: Optional[str] = None):
    results = state["evaluated_stations"]
    if region and region != "ALL":
        results = [s for s in results if s.get("region") == region or s.get("state") == region]
    if severity and severity != "ALL":
        results = [s for s in results if s.get("overall_severity") == severity]
    return {
        "stations": results,
        "hours_meta": HOUR_LABELS,
        "synoptic_hours": SYNOPTIC_HOURS
    }

@app.post("/api/fetch-now")
def trigger_fetch():
    success, msg = perform_fetch_and_eval()
    return {"success": success, "message": msg, "timestamp": datetime.now(timezone.utc).isoformat()}

@app.get("/api/station/{station_id}/activity")
def get_station_activity(station_id: str, message_type: Optional[str] = None):
    activity_log = state["parsed_data"].get("activity_by_station", {}).get(station_id, [])
    if message_type and message_type != "ALL":
        activity_log = [a for a in activity_log if a.get("type") == message_type]

    # Look up station config
    stn_meta = next((s for s in state["stations_config"] if s["id"] == station_id), None)

    return {
        "station_id": station_id,
        "station_name": stn_meta["name"] if stn_meta else f"Station {station_id}",
        "total_records": len(activity_log),
        "records": activity_log
    }

class StationModel(BaseModel):
    id: str
    name: str
    state: str = ""
    region: str = "North"
    required_hours: List[str] = SYNOPTIC_HOURS

@app.post("/api/stations/config")
def update_stations_config(station: StationModel):
    # Check if exists
    for i, s in enumerate(state["stations_config"]):
        if s["id"] == station.id:
            state["stations_config"][i] = station.dict()
            save_stations_config()
            evaluate_all_stations()
            return {"success": True, "action": "updated", "station": station.dict()}
    
    state["stations_config"].append(station.dict())
    save_stations_config()
    evaluate_all_stations()
    return {"success": True, "action": "added", "station": station.dict()}

@app.delete("/api/stations/config/{station_id}")
def delete_station(station_id: str):
    initial_len = len(state["stations_config"])
    state["stations_config"] = [s for s in state["stations_config"] if s["id"] != station_id]
    if len(state["stations_config"]) == initial_len:
        raise HTTPException(status_code=404, detail="Station not found")
    save_stations_config()
    evaluate_all_stations()
    return {"success": True, "station_id": station_id}

@app.post("/api/upload-bulletin")
def upload_bulletin_data(payload: Dict[str, str] = Body(...)):
    raw_content = payload.get("content", "")
    if not raw_content:
        raise HTTPException(status_code=400, detail="Empty content provided")
    parsed = GTSParser.parse_bulletin_stream(raw_content)
    state["parsed_data"] = parsed
    evaluate_all_stations()
    return {
        "success": True,
        "total_bulletins": parsed["total_bulletins"],
        "stations_found": len(parsed["synops_by_station"])
    }

@app.post("/api/poll-settings")
def update_poll_settings(payload: Dict[str, Any] = Body(...)):
    if "interval" in payload:
        val = int(payload["interval"])
        if val in [60, 120, 180, 300]:
            state["poll_interval_seconds"] = val
    if "is_polling" in payload:
        state["is_polling"] = bool(payload["is_polling"])
    if "use_dynamic_polling" in payload:
        state["use_dynamic_polling"] = bool(payload["use_dynamic_polling"])

    window_info = get_synoptic_window_status()
    current_poll_rate = window_info["target_poll_seconds"] if state["use_dynamic_polling"] else state["poll_interval_seconds"]

    return {
        "poll_interval_seconds": current_poll_rate,
        "is_polling": state["is_polling"],
        "use_dynamic_polling": state["use_dynamic_polling"],
        "dynamic_window": window_info
    }

# Mount static files from frontend/dist if built
DIST_PATH = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")
if os.path.exists(DIST_PATH):
    app.mount("/assets", StaticFiles(directory=os.path.join(DIST_PATH, "assets")), name="assets")

    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        # Don't intercept API routes
        if full_path.startswith("api"):
            raise HTTPException(status_code=404, detail="Not Found")
        target_file = os.path.join(DIST_PATH, full_path)
        if os.path.exists(target_file) and os.path.isfile(target_file):
            return FileResponse(target_file)
        return FileResponse(os.path.join(DIST_PATH, "index.html"))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=True)
