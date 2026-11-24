# MASTER BLUEPRINT: SYNOP Sanity Checker

**Document Version:** 0.1.0  
**Status:** Discovery & Requirements Gathering  
**Last Updated:** 2026-11-23  

---

## 1. Executive Summary & Project Objective
* **Goal:** Ingest live/batch GTS weather data from IMD AMSS Delhi (`sendata.txt`), filter and monitor SYNOP (`AAXX`) messages for designated weather stations, track receipt timeliness (detecting missing or delayed station reports), and perform comprehensive sanity/quality checks on the received SYNOP reports.
* **Target Audience / End Users:** Weather station observers, meteorological forecasters, and data quality monitoring teams.
* **Core Problem Statement:** In high-volume bulletin feeds (like AMSS Delhi with hundreds of mixed GTS bulletins including AAXX, METAR, PILOT), identifying whether specific regional/assigned stations submitted their required synoptic observation on time and whether those reports contain formatting or physical sanity errors requires automated, real-time tracking and validation.

---

## 2. Scope & Boundaries
### In Scope
- Automatic/scheduled or on-demand fetching of `https://amssdelhi.gov.in/sendata/sendata.txt` (with legacy SSL cipher support `DEFAULT@SECLEVEL=1`).
- Manual upload / paste fallback for testing or offline bulletins.
* **Station Configuration & Schedule Customization:**
  - Configurable station watchlist where users can add/remove stations by 5-digit WMO ID (e.g. `42165`) and Station Name (e.g. `New Delhi / Safdarjung`).
  - Predefined station groups (State/Region presets: North, Northwest, etc.).
  - **Station-Specific Observation Schedule**: Support per-station schedule configuration:
    - 24/7 Full Synoptic Stations: all 8 main & intermediate synoptic hours per day (00, 03, 06, 09, 12, 15, 18, 21 UTC).
    - Part-Time / Selected Hours Stations: custom subset of synoptic hours (e.g. daylight hours only: 03, 06, 09, 12 UTC, or any custom selection).
    - Missing/late detection evaluates only against the specific configured required hours for that station.
* **Timeliness & SLA Classification Engine:**
  - Standard Synoptic Observation Hours: `00:00, 03:00, 06:00, 09:00, 12:00, 15:00, 18:00, 21:00 UTC` (every day).
  - SLA Status & Visual Alert Levels for an observation hour `HH:00 UTC`:
    - **Before `HH:00 UTC`**: **Early (Yellow Alert - Still OK)**
    - **`HH:00` to `HH:15 UTC`**: **On Time (Green Alert - Normal / OK)**
    - **`HH:16` to `HH:30 UTC`**: **Late (Extreme Red Alert)**
    - **Beyond `HH:30 UTC` / Not Received**: **Very Very Late / Missing (Extreme Red Alert)**
  - Tracked against each station's configured schedule (whether all 8 synops or specific selected hours).
- SYNOP Sanity & Validation Engine:
  - WMO FM-12 decoding for Section 1 (mandatory groups `iRixhVV`, `Nddff`, `1snTTT`, `2snTdTdTd`, `3P0P0P0P0`, `4PPPP`, `5appp`, `6RRRtR`, `7wwW1W2`, `8NhCLCMCH`), Section 3 (`333` regional groups, e.g. `58xxx` pressure tendency, max/min temps, rainfall).
  - Physical & logical checks (bounds checking, $T_d \le T$, pressure consistency, wind speed, etc.).
- Interactive Dashboard UI (Apple Design System inspired, high visual fidelity, fluid feedback, responsive).

### Out of Scope
- Direct upstream modification of the AMSS server.
- Processing non-SYNOP bulletins (e.g. raw rawinsonde TEMP/PILOT) beyond extracting station presence if needed.

---

## 3. Domain & Specification Details
* **Domain Definition:** Meteorological weather reports (WMO FM-12 SYNOP surface synoptic observations, including AAXX / BBXX code groups).
* **Live Feed Source:** `https://amssdelhi.gov.in/sendata/sendata.txt` (WMO GTS bulletin format: `ZCZC ... TTAAii CCCC YYGGgg AAXX YYGGiw ... NNNN`).
* **Standard / Specification Reference:** WMO Manual on Codes (WMO-No. 306, Volume I.1, Part A - Code form FM 12-XIV Ext. SYNOP) & IMD National Guidelines for Surface Observations.
* **Sample Data Sets:** Live verified stream from AMSS Delhi (contains ~300KB+ multi-bulletin text stream per cycle).

---

## 4. Input & Ingestion Pipeline
* **Input Sources & Refresh Mechanism:**
  1. **Dynamic Synoptic Window Polling:**
     - **Active Synoptic Window (High Frequency):** From `HH-1:45 UTC` (15 minutes prior to observation cycle) to `HH:30 UTC` (30 minutes after observation cycle), polls **every 1 minute** (e.g. for `03:00 UTC`, polls every 1 min from `02:45 UTC` to `03:30 UTC`).
     - **Quiet / Idle Window:** Outside the 45-minute active window, relaxes polling to **every 30 minutes** to conserve network bandwidth and respect server load (once a station is extremely late or window passes, frequent scanning is unnecessary).
     - **Live Window Countdown:** The header prominently displays whether the system is in an Active Window or Idle Window, with a live countdown to the next active observation window.
  2. **Manual Instant Refresh:** Dedicated "Fetch Latest Now" action button.
  3. **Backend Proxy Pipeline:** Python/Node backend handles fetching with SSL legacy cipher compatibility (`DEFAULT@SECLEVEL=1`), preventing browser CORS and DH-key handshake failures.
  4. **Fallback / Manual Testing:** Tab to paste raw GTS/SYNOP text or upload saved `.txt` files.
* **Ingestion, Classification & Filtering Pipeline:**
  1. **Full Message Extraction & Classification:**
     - For each monitored station, the parser extracts **all** incoming transmissions across the bulletin feed.
     - Each message is categorized with a strict type badge:
       - `SYNOP (Surface AAXX)`: Surface synoptic observations.
       - `TEMP (Upper Air Sounding)`: `TTAA`, `TTBB`, `TTCC`, `TTDD`.
       - `PILOT (Wind Ascent)`: `PPBB`, `PPAA`.
       - `METAR (Aviation)`: Airport aviation reports.
       - `REMARKS / AUX`: Regional auxiliary reports (`SXIN`, RH/RF remarks).
  2. **Intelligent Routing & Filtering:**
     - `SYNOP (Surface AAXX)` messages are routed to the **Timeliness & Missing Check Engine** to evaluate against the station's required observation schedule and deduplicate redundant collective messages.
     - In the Station Drawer, an **Activity Log** displays all messages received for that station with filter toggles (e.g. `[x] Show Only SYNOP`, `[ ] Show Upper Air`, `[ ] Show Pilot/Remarks`), providing 100% transparency into everything the station transmitted.

---

## 5. Validation Rules & Sanity Logic Engine
* **Current Phase Focus (MVP):** SYNOP Receipt & Timeliness Verification ("Has the SYNOP been sent on time or not?").
* **SLA Timeliness Rules:**
  - For each required synoptic hour `HH:00 UTC`:
    - **Before `HH:00 UTC`**: Early (Yellow Alert - Still OK)
    - **`HH:00` to `HH:15 UTC`**: On Time (Green Alert - Normal / OK)
    - **`HH:16` to `HH:30 UTC`**: Late (Extreme Red Alert)
    - **Beyond `HH:30 UTC` or Missing**: Very Very Late / Missing (Extreme Red Alert)
* **Deferred to Future Phases:**
  - Meteorological field-by-field value sanity checks (temperatures, pressure, dew point, rainfall, wind consistency). Designed modularly to plug in easily when requested.

---

## 6. System Architecture & Tech Stack
* **Architecture Type:** Full-Stack Desktop & Web Application (Native Desktop Window via `pywebview` / WebView2 + Python FastAPI Backend + React Frontend).
* **Desktop App Delivery:**
  - `desktop_app.py`: Launches backend server in background and opens standalone native desktop window with no browser address bars.
  - `Launch-SYNOP-App.bat` and `Launch-SYNOP-Silent.vbs`: One-click Windows desktop launchers.
  - **Critical Alert Alarm on Launch:** Automatically checks for late/missing stations immediately on startup and sounds the multi-tone emergency alert chime, with an instant "Silence Alarm" toggle.
* **UI Design System (Humanised Apple Design):**
  - **Top-Center Settings Hub:** Centralized settings button in the top center of the header for managing Watchlist, Ingestion fallback, and Dynamic Polling rules.
  - **Apple Dark Mode Support:** Seamless toggle between Light and Dark themes, using Apple OLED deep blacks (`#000000`, `#1C1C1E`), translucent glass cards, luminous status badges, and SF Pro typography.
  - **Attention-First Visual Hierarchy:** Stations needing attention (Late or Missing synops) are automatically prioritized at the very top of the dashboard.
  - **Calm, Human Hero Section:** Replaces dense, cluttered metric cards with a calm conversational status statement (e.g. *"2 stations need attention right now"* or *"All 16 stations are running smoothly"*).
  - **Sleek 8-Pill Timeline:** Replaces heavy, repetitive 8-box grids on every card with a clean, minimalist horizontal observation track (`00Z` to `21Z`) using refined status pips and interactive tooltips.
  - **Clean Header:** Streamlined navigation with dual UTC/IST live clocks, audio alert toggle, and dynamic window indicators.
  - **Typography & Motion:** San Francisco inspired typography, generous whitespace, subtle translucent glassmorphism (`backdrop-blur`), and fluid spring transitions.
* **Backend:**
  - Python 3.x with **FastAPI** & **Uvicorn**.
  - Custom GTS / WMO Bulletin Parser (separates `ZCZC` to `NNNN`, extracts headers `SMIN`, `SIIN`, `AAXX`).
  - SSL Legacy Adapter (`DEFAULT@SECLEVEL=1`) to reliably fetch `https://amssdelhi.gov.in/sendata/sendata.txt`.
  - In-memory cache & background polling worker (1-3 min intervals).
  - Deduplication and Station SLA Evaluation Engine.
* **Verification:**
  - Autonomous visual and functional verification via **Playwright MCP**.

---

## 7. Output & Reporting
* **Interactive Web Dashboard:** Live status overview, station cards, time-slot matrix, alert banners, filter by status (All, Late, Missing, On-Time).
* **Detailed Station Drawer:** Drill-down into raw SYNOP text, bulletin sequence number, originating center, and transmission timestamp.
* **Export Capability:** Export current status summary to CSV or JSON report.

---

## 8. Milestone & Execution Roadmap
- [x] Phase 1: Requirements Gathering & Schema Definition *(Completed)*
- [x] Phase 2: Architecture & Data Model Finalization *(Completed)*
- [x] Phase 3: Core Validation & Sanity Checking Engine Implementation *(Completed)*
- [x] Phase 4: Interface & Dashboard Pipeline Development (FastAPI + React) *(Completed)*
- [x] Phase 5: Verification, Edge-case Testing & Visual Verification (Playwright MCP) *(Completed)*
- [x] Phase 6: Final Review & Handover *(Completed)*

---

## 9. Clarifications & Decisions Log
| Date | Question / Topic | Clarification / Decision | Status |
| :--- | :--- | :--- | :--- |
| 2026-11-23 | Domain Definition | Confirmed: WMO FM-12 SYNOP surface weather observations (AAXX/BBXX). | Decided |
| 2026-11-23 | Interface / Form Factor | Confirmed: Web Application with interactive visual dashboard. | Decided |
| 2026-11-23 | Input Data Source | Confirmed: Live feed from https://amssdelhi.gov.in/sendata/sendata.txt + manual fallback. | Decided |
| 2026-11-23 | Core Features | Filter specific stations, monitor receipt timeliness/missing synops, sanity check data. | Decided |
| 2026-11-23 | Station List Specification | Confirmed: Configurable watchlist + custom per-station observation schedules (e.g., 8 synops/day vs selected hours). | Decided |
| 2026-11-23 | Timeliness & Delay Window | Confirmed: <00 Early (Yellow), 00-15 On Time (Green), 16-30 Late (Extreme Red), >30 / Missing Very Very Late (Extreme Red). | Decided |
| 2026-11-23 | Sanity & Quality Checks | Confirmed: Scope focused on SYNOP Receipt & Timeliness Verification for now; field-value sanity deferred. | Decided |
| 2026-11-23 | Data Ingestion & Refresh Mode | Confirmed: Automatic live refresh polling every 1-3 minutes + manual fetch button. | Decided |
| 2026-11-23 | Initial Target Station List | Confirmed: Pre-loaded customizable list of key IMD stations + watchlist manager. | Decided |
| 2026-11-23 | Deduplication & AAXX Filtering | Identified: Redundant transmissions (individual + collective) & non-SYNOP data (TTAA/PPBB/SXIN) using station IDs. | Decided |
| 2026-11-23 | Tech Stack Selection | Confirmed: Option 1 (FastAPI Python backend + Modern React/Tailwind frontend). | Decided |
| 2026-11-23 | Timezone & Sound Preferences | Confirmed: Dual display side-by-side everywhere (UTC / IST) + Audio alert toggle. | Decided |
| 2026-11-23 | Ingestion & Multi-Type Filtering | Confirmed: Ingest all station messages, classify by type (SYNOP/TEMP/PILOT/METAR/AUX), route SYNOP to timeliness engine, and offer filterable activity drawer. | Decided |
| 2026-11-24 | Two-Tier NNNN Deduplication & Audit Engine | Enforced user rule: max 1 report per station between NNNN markers (eliminating non-SYNOP leaks). Added inter-bulletin reconciliation (Relay Echo vs Collective Confirmation vs Correction), scoring SLA on earliest transmission while displaying authoritative report in drawer with interactive audit trail. | Decided |
| 2026-11-23 | Implementation Kickoff | Ready for kickoff | Ready |
