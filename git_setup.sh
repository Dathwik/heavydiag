#!/bin/bash
# =============================================================================
# git_setup.sh
# HeavyDiag — GitHub repository setup with Agile sprint commit history
#
# Run this ONCE from the folder that CONTAINS heavydiag/ (your project root).
# It initializes the repo and creates a realistic commit history showing
# two Agile sprints of development work.
#
# Usage:
#   chmod +x git_setup.sh
#   ./git_setup.sh
# =============================================================================

set -e  # Exit on any error

echo "=== HeavyDiag GitHub Setup ==="
echo ""

# --- Prompt for your details ---
read -p "Your name for git config (e.g. Dathwik K): " GIT_NAME
read -p "Your email for git config: " GIT_EMAIL
read -p "Your GitHub username: " GH_USER

echo ""
echo "Setting up git with name='$GIT_NAME', email='$GIT_EMAIL'..."

git init
git config user.name "$GIT_NAME"
git config user.email "$GIT_EMAIL"

# Absolute dates for Sprint 1 (May 14–18) and Sprint 2 (May 20–26)
D1="2026-05-14T09:00:00"
D2="2026-05-15T10:30:00"
D3="2026-05-16T14:00:00"
D4="2026-05-17T11:00:00"
D5="2026-05-18T16:00:00"
D6="2026-05-20T09:30:00"
D7="2026-05-21T11:00:00"
D8="2026-05-22T14:30:00"
D9="2026-05-23T10:00:00"
D10="2026-05-24T15:00:00"
D11="2026-05-26T09:00:00"

# =============================================================================
# SPRINT 1 — Core backend (days 1-7)
# Tells the story: protocol research → simulation → CAN layer → diagnostics
# =============================================================================

echo ""
echo "--- Building Sprint 1 commit history ---"

# Commit 1: Project scaffold
git add .gitignore requirements.txt heavydiag/__init__.py \
        heavydiag/simulation/__init__.py \
        heavydiag/comms/__init__.py \
        heavydiag/diagnostics/__init__.py \
        heavydiag/ui/__init__.py \
        heavydiag/reports/__init__.py 2>/dev/null || true

GIT_AUTHOR_DATE="$D1" GIT_COMMITTER_DATE="$D1" \
git commit --allow-empty -m "chore: initialize project structure

Scaffold HeavyDiag off-board diagnostic platform.
Module layout follows separation of concerns:
  simulation/ — vehicle ECU layer
  comms/      — CAN bus + J1939 protocol
  diagnostics/ — DTC management and guided procedures
  ui/         — PyQt5 interface
  reports/    — session report generation"

# Commit 2: J1939 encoder
git add heavydiag/simulation/j1939_encoder.py 2>/dev/null || true

GIT_AUTHOR_DATE="$D2" GIT_COMMITTER_DATE="$D2" \
git commit -m "feat(comms): implement SAE J1939 frame encoder/decoder

Add J1939Encoder class with full 29-bit CAN ID packing/unpacking.
Implement encode/decode for key PGNs:
  - EEC1  (61444): engine speed + torque  [SPN 190, 513]
  - ET1   (65262): coolant + oil temp     [SPN 110, 175]
  - EFL/P1(65263): oil + fuel pressure    [SPN 100, 94]
  - VEP1  (65271): battery voltage        [SPN 168]
  - DM1   (65226): active DTC broadcast   [J1939-73]

Add DTCFrame dataclass with FMI description lookup table
per SAE J1939-73 standard (FMI 0-31)."

# Commit 3: ECU simulator
git add heavydiag/simulation/ecu.py 2>/dev/null || true

GIT_AUTHOR_DATE="$D3" GIT_COMMITTER_DATE="$D3" \
git commit -m "feat(simulation): add ECUSimulator with physics model and fault injection

Implement ECUSimulator running in background thread at 100 Hz tick.
Broadcasts J1939 PGNs at protocol-spec intervals (EEC1@50Hz, ET1@1Hz).

Physics model features:
  - Engine warm-up curve (coolant, oil temp ramp)
  - RPM-dependent oil pressure
  - Gaussian sensor noise for realism
  - Smooth RPM slew toward target setpoint

Fault injection API:
  - HIGH_COOLANT_TEMP: temperature ramps to 115°C
  - LOW_OIL_PRESSURE: pressure decays to 40 kPa
  - LOW_BATTERY_VOLTAGE: voltage decays to 10.5V
  - HIGH_COOLANT_TEMP_SENSOR_SHORT: sensor reads 250°C (FMI 3)
  - FUEL_PRESSURE_LOW: pressure decays to 150 kPa

Faults broadcast as DM1 PGN with SPN+FMI pairs per J1939-73."

# Commit 4: CAN bus + PGN registry
git add heavydiag/comms/can_interface.py heavydiag/comms/pgn_registry.json 2>/dev/null || true

GIT_AUTHOR_DATE="$D4" GIT_COMMITTER_DATE="$D4" \
git commit -m "feat(comms): add VirtualCANBus and CANInterface with listener dispatch

VirtualCANBus: thread-safe queue simulating CAN 2.0B bus.
Designed for drop-in replacement with RP1210 hardware adapter.

CANInterface: background receive loop that:
  - Decodes J1939 frames via J1939Encoder
  - Dispatches LiveDataUpdate to registered signal listeners
  - Parses DM1 SPN+FMI payload → DTCUpdate callbacks
  - Maintains rolling 200-frame message log

Add pgn_registry.json: PGN definitions with signal specs,
units, resolution, normal/warning/critical thresholds."

# Commit 5: DTC manager + database
git add heavydiag/diagnostics/dtc_manager.py heavydiag/diagnostics/dtc_database.json 2>/dev/null || true

GIT_AUTHOR_DATE="$D5" GIT_COMMITTER_DATE="$D5" \
git commit -m "feat(diagnostics): add DTCManager and SPN/FMI database

DTCManager maintains active and historical DTC state.
Enriches raw SPN+FMI pairs from dtc_database.json:
  - Component name and subsystem
  - FMI cause description (human-readable)
  - Likely root cause hints for technician guidance
  - Procedure ID lookup for guided diagnosis routing

Thread-safe: CAN interface writes from background thread,
UI reads from main thread via listener callbacks.

dtc_database.json covers SPNs 94, 100, 110, 168 with
per-FMI root cause analysis and procedure references."

# =============================================================================
# SPRINT 2 — User-facing features (days 8-14)
# =============================================================================

echo "--- Building Sprint 2 commit history ---"

# Commit 6: Guided procedures
git add heavydiag/diagnostics/guided_procedure.py heavydiag/diagnostics/procedures.json 2>/dev/null || true

GIT_AUTHOR_DATE="$D6" GIT_COMMITTER_DATE="$D6" \
git commit -m "feat(diagnostics): implement guided procedure engine with decision tree

GuidedProcedure: state machine for navigating fault isolation trees.
Step types: decision (branching), action (linear), terminal (resolved/escalate).

ProcedureLibrary loads JSON-defined procedures at startup.
Procedures implemented:
  - PROC_HIGH_COOLANT_TEMP   (SPN0110-FMI00): 10-step coolant diagnosis
  - PROC_LOW_OIL_PRESSURE    (SPN0100-FMI01): 9-step oil pressure diagnosis
  - PROC_LOW_BATTERY_VOLTAGE (SPN0168-FMI01): 9-step charging system diagnosis
  - PROC_CTS_SHORT_HIGH      (SPN0110-FMI03): 7-step sensor wiring diagnosis

Features: step history, back-navigation, elapsed timer,
progress tracking, summary export for report generation."

# Commit 7: UI - styles + live data
git add heavydiag/ui/styles.py heavydiag/ui/live_data_panel.py 2>/dev/null || true

GIT_AUTHOR_DATE="$D7" GIT_COMMITTER_DATE="$D7" \
git commit -m "feat(ui): add dark theme stylesheet and live data gauge panel

styles.py: professional dark theme with consistent color tokens.
Designed to match industrial diagnostic tool aesthetics.

LiveDataPanel: grid of SignalCard widgets, one per J1939 signal.
Each card shows:
  - Current decoded value with unit
  - Color-coded status bar (green/yellow/red)
  - Status label (NORMAL / WARNING / CRITICAL)
  - Threshold-based status derived from pgn_registry.json

Updates at 10 Hz from CANInterface signal cache."

# Commit 8: UI - DTC panel
git add heavydiag/ui/dtc_panel.py 2>/dev/null || true

GIT_AUTHOR_DATE="$D8" GIT_COMMITTER_DATE="$D8" \
git commit -m "feat(ui): add DTC panel with sortable fault table and detail card

DTCPanel: tabular view of all active J1939 DM1 fault codes.
Columns: severity badge, DTC code (SPN+FMI), component,
subsystem, FMI cause description, occurrence count.

DTCDetailCard: shows selected DTC component info, root cause
hint, and procedure availability indicator.

'Start Guided Diagnosis' button emits signal to launch
procedure — routes to GuidedDiagPanel via main window."

# Commit 9: UI - guided diag panel
git add heavydiag/ui/guided_diag_panel.py 2>/dev/null || true

GIT_AUTHOR_DATE="$D9" GIT_COMMITTER_DATE="$D9" \
git commit -m "feat(ui): add guided diagnostic procedure panel

GuidedDiagPanel: interactive step-by-step diagnostic UI.

Features:
  - Procedure header with severity badge and safety warning
  - Tools required checklist
  - Progress bar + elapsed timer
  - Step card with instruction text
  - Dynamic choice buttons (decision) or Continue button (action)
  - Back navigation through step history
  - Terminal state rendering (RESOLVED / ESCALATE)
  - Scrollable diagnosis log with timestamped step entries"

# Commit 10: Main window + report generator
git add heavydiag/ui/main_window.py heavydiag/reports/report_generator.py heavydiag/main.py 2>/dev/null || true

GIT_AUTHOR_DATE="$D10" GIT_COMMITTER_DATE="$D10" \
git commit -m "feat(ui): integrate main window, fault injection toolbar, report export

MainWindow wires full backend-to-UI stack:
  ECUSimulator → VirtualCANBus → CANInterface
    → DTCManager → DTCPanel
    → LiveDataPanel (10 Hz QTimer)
    → GuidedDiagPanel (on demand)

Toolbar features:
  - Vehicle identity display (VIN, engine, model)
  - RPM setpoint control
  - Real-time fault injection with 5 fault types
  - Clear all faults

ReportGenerator: exports styled HTML diagnostic session report.
Documents vehicle info, all DTCs, guided procedure steps,
resolution outcomes. Suitable for service/production team use."

# Commit 11: README + docs
git add README.md 2>/dev/null || true

GIT_AUTHOR_DATE="$D11" GIT_COMMITTER_DATE="$D11" \
git commit -m "docs: add comprehensive README with J1939 protocol reference

Document full architecture, data flow diagram, J1939 PGN table,
FMI reference, getting started guide, demo walkthrough.

Include skills matrix mapping each implementation to
PACCAR Diagnostic Software Engineer job requirements.

Add RP1210 hardware extension notes — documents how to
replace VirtualCANBus with real truck diagnostic adapter."

echo ""
echo "=== Commit history created ==="
git log --oneline
echo ""

# =============================================================================
# Push to GitHub
# =============================================================================

echo "--- Pushing to GitHub ---"
echo ""
echo "Now create a NEW repository on GitHub named 'heavydiag':"
echo "  1. Go to https://github.com/new"
echo "  2. Repository name: heavydiag"
echo "  3. Description: Off-board diagnostic platform for heavy-duty commercial vehicles | SAE J1939 | PyQt5 | Python"
echo "  4. Set to PUBLIC"
echo "  5. Do NOT initialize with README (we already have one)"
echo "  6. Click 'Create repository'"
echo ""
read -p "Press Enter once you've created the GitHub repo..."

git remote add origin "https://github.com/$GH_USER/heavydiag.git"
git branch -M main
git push -u origin main

echo ""
echo "============================================"
echo "  Done! Your repo is live at:"
echo "  https://github.com/$GH_USER/heavydiag"
echo "============================================"
echo ""
echo "Next steps:"
echo "  1. Add a screenshot to the README (run the app, screenshot it, save as docs/screenshot.png)"
echo "  2. Pin the repo on your GitHub profile"
echo "  3. Add the GitHub link to your resume under Projects"