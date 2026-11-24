# Workspace Project Rules: SYNOP Sanity Checker

## 1. Strict Project Boundary Enforcement
* **Active Project Workspace:** `E:\projects\synop sanity checker` (**IMD SYNOP Sanity & SLA Monitor**).
* **Cross-Project Alert Protocol:** If the user sends a prompt, question, or instruction that references or belongs to a different project (such as **FreeNetMeter**, **Internet Speed Meter**, or any non-SYNOP code/task):
  1. **Do NOT execute changes** on the outside project.
  2. **Immediately remind the user** that the request belongs to another project rather than the SYNOP Sanity Checker.
  3. Confirm whether they want to stay on the SYNOP Checker or if they intended to switch contexts.

## 2. SYNOP Monitor Status
* **Backend:** FastAPI daemon running at `http://127.0.0.1:8000`.
* **Frontend:** Vite React dashboard running at `http://localhost:5173`.
* **Desktop App:** `desktop_app.py` / `Launch-SYNOP-App.bat`.

## 3. Engineering Standard & Agent Skills Integration
* **Plugin Installed:** `agent-skills` (v0.6.17 by Addy Osmani).
* **Location:** `C:\Users\Dell\.gemini\config\plugins\agent-skills`.
* **Operating Model:** Adhere strictly to the `agent-skills` engineering lifecycle:
  - **Define & Specify:** `spec-driven-development` / `api-and-interface-design`
  - **Plan & Breakdown:** `planning-and-task-breakdown`
  - **Build & Refactor:** `incremental-implementation`, `test-driven-development`, `code-simplification`
  - **Inspect & Debug:** `debugging-and-error-recovery`, `doubt-driven-development`
  - **UI & Accessibility:** `frontend-ui-engineering`, `accessibility-engineering`
  - **Review & Verify:** `code-review-and-quality`, Playwright autonomous verification
  - **Ship:** `shipping-and-launch`

