# HeavyDiag — Off-Board Diagnostic Platform

![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python)
![PyQt5](https://img.shields.io/badge/GUI-PyQt5-41CD52?logo=qt)
![Protocol](https://img.shields.io/badge/Protocol-SAE%20J1939-orange)
![Architecture](https://img.shields.io/badge/Architecture-CAN%202.0B-lightgrey)
![Methodology](https://img.shields.io/badge/Methodology-Agile-6A5ACD)

A Python-based **off-board diagnostic platform** for heavy-duty commercial vehicle electronic systems, built to demonstrate competency in the design and development of guided diagnostic procedures, J1939 communication networks, object-oriented software architecture, and technical documentation — aligned with the responsibilities of a Diagnostic Software Engineer at PACCAR Global Electronics.

---

## Overview

HeavyDiag simulates a full off-board diagnostic session for a heavy-duty commercial vehicle (Kenworth T680 / PACCAR MX-13 engine). It implements the complete pipeline from raw CAN bus communication through J1939 message decoding, real-time signal monitoring, Diagnostic Trouble Code (DTC) management, and guided step-by-step fault resolution procedures — all without requiring physical hardware.

The platform directly mirrors the architecture of production diagnostic tools used in commercial vehicle service and manufacturing environments.

---

## Features

### Live J1939 Signal Monitoring
- Decodes real SAE J1939 PGNs: EEC1 (61444), ET1 (65262), EFL/P1 (65263), VEP1 (65271)
- Real-time display of engine speed (SPN 190), coolant temperature (SPN 110), oil pressure (SPN 100), fuel delivery pressure (SPN 94), and battery voltage (SPN 168)
- Color-coded status indicators: normal / warning / critical thresholds per J1939 spec
- Simulated ECU physics model — warm-up curves, RPM-dependent pressure, sensor noise

### Diagnostic Trouble Code (DTC) Management
- Decodes DM1 (PGN 65226) Active DTC broadcasts from the CAN bus
- Parses SPN + FMI pairs per SAE J1939-73 specification
- Enriches raw codes with component name, subsystem, FMI cause description, and root cause hints from an internal DTC database
- Severity classification (critical / warning) with occurrence count tracking
- Full session history for report generation

### Guided Diagnostic Procedures
- JSON-defined decision tree procedures — the core of off-board diagnostic tooling
- Technician walks through validated step-by-step fault isolation trees
- Branching logic based on field measurements (voltage checks, pressure readings, visual inspection)
- Elapsed time tracking, step history log, back-navigation support
- Outcome states: **Resolved** or **Escalate to Dealer**

Implemented procedures:
| Procedure ID | DTC | Title |
|---|---|---|
| `PROC_HIGH_COOLANT_TEMP` | SPN0110-FMI00 | Engine Overheating — Coolant Temp Above Normal |
| `PROC_LOW_OIL_PRESSURE` | SPN0100-FMI01 | Engine Oil Pressure Below Normal |
| `PROC_LOW_BATTERY_VOLTAGE` | SPN0168-FMI01 | Battery Voltage Below Normal |
| `PROC_CTS_SHORT_HIGH` | SPN0110-FMI03 | Coolant Temp Sensor — Short to High Voltage |

### Diagnostic Report Generation
- Exports a styled HTML diagnostic session report
- Documents vehicle info, all DTCs encountered, guided procedure steps taken, and resolution outcome
- Designed for use by service and production teams

### Fault Injection Simulator
- Inject real fault conditions at runtime: overheating, low oil pressure, low battery voltage, sensor shorts, fuel pressure faults
- Watch DTCs appear on the CAN bus within 1 second
- Full ECU physics responds — coolant temp rises, pressure drops, voltage decays

---

## Architecture

```
heavydiag/
│
├── simulation/             # Vehicle-side simulation
│   ├── j1939_encoder.py    # SAE J1939 frame encode/decode (PGN, SPN, FMI)
│   └── ecu.py              # ECU simulator — broadcasts J1939 PGNs, injects faults
│
├── comms/                  # Communication layer
│   ├── can_interface.py    # Virtual CAN bus + message dispatcher
│   └── pgn_registry.json   # PGN definitions with signal specs and thresholds
│
├── diagnostics/            # Diagnostic engine
│   ├── dtc_manager.py      # DTC lifecycle management and enrichment
│   ├── dtc_database.json   # SPN/FMI database — component info and root causes
│   ├── guided_procedure.py # Decision tree state machine
│   └── procedures.json     # Guided procedure definitions (JSON logic trees)
│
├── ui/                     # PyQt5 GUI
│   ├── main_window.py      # Top-level window, tab layout, toolbar
│   ├── live_data_panel.py  # Real-time J1939 signal gauge cards
│   ├── dtc_panel.py        # Active DTC table with detail view
│   ├── guided_diag_panel.py# Step-by-step guided procedure UI
│   └── styles.py           # Dark theme stylesheet
│
├── reports/
│   └── report_generator.py # HTML session report generator
│
└── main.py                 # Application entry point
```

### Data Flow

```
ECUSimulator
    │  J1939Frame (encoded bytes)
    ▼
VirtualCANBus  (thread-safe queue)
    │
    ▼
CANInterface  (background thread)
    ├── decode PGN → LiveDataUpdate → LiveDataPanel (10 Hz)
    └── decode DM1 → DTCUpdate → DTCManager → DTCPanel
                                      │
                                      └── GuidedProcedure (on demand)
                                                │
                                                └── ReportGenerator
```

---

## J1939 Protocol Implementation

SAE J1939 is the primary communication standard for heavy-duty commercial vehicle ECUs, running over CAN 2.0B with 29-bit identifiers.

**CAN ID structure (29-bit):**
```
[ Priority 3b ][ Reserved 1b ][ Data Page 1b ][ PDU Format 8b ][ PDU Specific 8b ][ Source Address 8b ]
```

**PGNs implemented:**

| PGN | Hex | Name | Key SPNs |
|-----|-----|------|----------|
| 61444 | 0xF004 | EEC1 — Engine Electronic Controller 1 | SPN 190 (RPM), SPN 513 (Torque) |
| 65262 | 0xFEEE | ET1 — Engine Temperature 1 | SPN 110 (Coolant), SPN 175 (Oil Temp) |
| 65263 | 0xFEEF | EFL/P1 — Engine Fluid Level/Pressure 1 | SPN 100 (Oil Press), SPN 94 (Fuel Press) |
| 65271 | 0xFEF7 | VEP1 — Vehicle Electrical Power 1 | SPN 168 (Battery Voltage) |
| 65226 | 0xFECA | DM1 — Active Diagnostic Trouble Codes | SPN + FMI pairs |

**FMI (Failure Mode Identifier)** follows SAE J1939-73:
- FMI 0: Data valid but above normal range
- FMI 1: Data valid but below normal range
- FMI 3: Voltage above normal / shorted high
- FMI 4: Voltage below normal / shorted low
- FMI 5: Current below normal / open circuit

---

## Getting Started

### Requirements
- Python 3.10+
- PyQt5 5.15+

### Setup

```bash
# Clone the repository
git clone https://github.com/YOUR_USERNAME/heavydiag.git
cd heavydiag

# Create isolated virtual environment
python3.10 -m venv venv
source venv/bin/activate        # macOS / Linux
# venv\Scripts\activate         # Windows

# Install dependencies
pip install -r requirements.txt

# Run
python -m heavydiag.main
```

### Demo Walkthrough

1. **Live Data tab** — observe real-time J1939 signals updating from the simulated ECU
2. **Toolbar → Engine RPM** — change the RPM setpoint and watch oil pressure and torque respond
3. **Toolbar → Inject Fault → "Low Oil Pressure"** — a DTC appears on the CAN bus within 1 second
4. **Fault Codes tab** — select the DTC, review the component info and root cause hint
5. **"Start Guided Diagnosis"** — walk through the validated fault isolation procedure
6. **File → Export Diagnostic Report** — generates an HTML report of the session

---

## Development Methodology

This project was developed following **Agile practices**:

- Work organized into two one-week sprints with defined deliverables
- **Sprint 1:** Core backend — J1939 protocol layer, ECU simulator, virtual CAN bus, DTC management engine
- **Sprint 2:** User-facing features — guided diagnostic procedures, GUI, report generation, documentation
- Continuous integration mindset: each layer tested independently before integration
- Separation of concerns: simulation, communication, diagnostics, and UI are fully decoupled

---

## Skills Demonstrated

| PACCAR Job Requirement | Implementation |
|---|---|
| Off-board diagnostics platform design | Full platform: simulation → CAN → decode → DTC → guided procedure → report |
| Diagnostic algorithms and software components | `dtc_manager.py`, `guided_procedure.py` — OOP state machines |
| Visual logic development environment | `procedures.json` — JSON-defined decision trees rendered as interactive UI |
| J1939 / CAN communication networks | `j1939_encoder.py` — full 29-bit CAN ID encode/decode, all key PGNs |
| Object-oriented software development (Python) | Dataclasses, threading, queue, OOP patterns throughout |
| Agile methodology | Sprint-based development, modular decoupled architecture |
| Technical documentation | Inline docstrings, README, HTML diagnostic reports |
| Cross-functional collaboration | Architecture designed for extension: add real RP1210 adapter, swap simulation layer |

---

## Extending to Real Hardware

The `VirtualCANBus` in `comms/can_interface.py` can be replaced with a real CAN adapter with minimal changes. For PACCAR/TMC tools, this would be an **RP1210-compliant adapter** (standard for heavy-duty truck diagnostics on Windows):

```python
# Replace VirtualCANBus with an RP1210 wrapper — no other code changes needed
from comms.rp1210_interface import RP1210CANBus
bus = RP1210CANBus(adapter_name="NEXIQ-USB-Link", channel=1)
```

The rest of the stack — decoder, DTC manager, guided procedures, UI — is hardware-agnostic by design.

---

## License

MIT License — see `LICENSE` for details.

---

*Built as a portfolio project to demonstrate competency for the Diagnostic Software Engineer role at PACCAR Global Electronics.*
