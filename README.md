# 🌤️ IMD SYNOP Sanity & SLA Monitor

A real-time meteorological GTS bulletin parser, timeliness verifier, and WMO deduplication engine for India Meteorological Department (IMD) synoptic observations (`AAXX`).

[![Streamlit App](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://streamlit.io/)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

---

## 🚀 Key Features

- **8-Slot Observation Timeline Bar (`00Z` – `21Z`)**: Visual representation of all synoptic transmission windows with color-coded status badges:
  - 🟢 **On-Time (SLA Met)**: Received within standard grace period (T+15 / T+45).
  - 🟡 **Delayed (Late SLA)**: Received after grace period before cutoff.
  - 🔵 **Early Transmission**: Received before the nominal observation hour.
  - 🔴 **Missing**: Overdue report past the transmission cutoff window.
  - ⚪ **Upcoming**: Pending future observation window.
- **Two-Tier WMO `NNNN` Deduplication Engine**:
  - **Tier 1 (Parser)**: Splits GTS text on standard `NNNN` bulletin terminators, enforcing **at most 1 report per station ID per `NNNN` block**. Eliminates false-positive trailing remark leakage (`SXIN90`, plain text comments).
  - **Tier 2 (SLA Reconciliation)**: Reconciles multiple `NNNN` transmissions across collectives. Evaluates SLA timeliness against the **earliest transmission** (so on-time field observers are never penalized) while providing the **latest authoritative report** for meteorological analysis.
- **Duplicate Transmission Inspector & Audit Trail**:
  - Categorizes duplicates into:
    - `Collective Echo`: Identical report re-broadcasted across regional bulletin collectives.
    - `Relay Echo`: Repeated transmission across different GTS communication channels.
    - `Amended (COR)`: Official corrected report superseding initial transmission.
    - `Data Discrepancy`: Mismatched weather parameters requiring audit.
- **Multi-Platform Support**:
  - 🎈 **Streamlit Cloud & Web App**: 1-click cloud deployable interactive dashboard (`streamlit_app.py`).
  - ⚡ **FastAPI + Vite React**: High-performance asynchronous backend and Apple Design-inspired client dashboard.
  - 🖥️ **Desktop Native App**: Lightweight standalone desktop window powered by `pywebview`.
- **Live UTC & IST Dual Clocks**: Continuous synchronization with current GTS synoptic windows and dynamic polling schedules.

---

## 📦 Quick Start (Streamlit Web App)

### 1. Clone & Install Dependencies
```bash
git clone https://github.com/Aman6390/synop-sanity-checker.git
cd synop-sanity-checker
pip install -r requirements.txt
```

### 2. Launch the Streamlit App
```bash
streamlit run streamlit_app.py
```
Open your browser at `http://localhost:8501`.

---

## 🌐 Deploy to Streamlit Community Cloud (Free)

1. Fork or clone this repository to your GitHub account (`https://github.com/Aman6390/synop-sanity-checker`).
2. Log into [share.streamlit.io](https://share.streamlit.io/).
3. Click **"New app"** and select:
   - **Repository:** `Aman6390/synop-sanity-checker` (or your fork)
   - **Branch:** `main`
   - **Main file path:** `streamlit_app.py`
4. Click **"Deploy!"** — Your live synoptic monitor will be publicly accessible worldwide.

---

## 🖥️ Alternative: Running the Full FastAPI + React Desktop Suite

### Full Development Stack (FastAPI + React)
```bash
python run.py
```
- Backend API: `http://127.0.0.1:8000`
- Interactive Swagger Docs: `http://127.0.0.1:8000/docs`
- React Frontend: `http://localhost:5173`

### Desktop Native App
```bash
python desktop_app.py
# Or on Windows, double-click:
Launch-SYNOP-App.bat
```

---

## 🛠️ Architecture

```
synop-sanity-checker/
├── streamlit_app.py          # Complete Streamlit cloud & local web app
├── requirements.txt          # Python dependencies
├── backend/
│   ├── app.py                # FastAPI REST API & APScheduler background daemon
│   ├── fetcher.py            # AMSS HTTP bulletin scraper
│   ├── gts_parser.py         # WMO GTS Bulletin & NNNN parser
│   ├── sla_engine.py         # SLA timeliness, grace periods, & duplicate reconciler
│   └── stations_config.json  # Regional station metadata & required hours
├── frontend/                 # Vite + React + Tailwind CSS dashboard
├── desktop_app.py            # PyWebView standalone desktop wrapper
├── run.py                    # Unified backend + frontend orchestrator
└── sendata_dump.txt          # Offline bulletin sample dataset for testing
```

---

## 📄 License
This project is licensed under the MIT License.
