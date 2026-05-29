# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the App

```bash
# Activate venv first
source venv/bin/activate

# Run from the project root (not inside heavydiag/)
python -m heavydiag.main
# or
python heavydiag/main.py
```

Dependencies are minimal — only `PyQt5>=5.15.0` (see `requirements.txt`). No build step, no test runner configured yet.

## Architecture Overview

HeavyDiag simulates a heavy-duty vehicle diagnostic tool (similar to PACCAR's ServiceLink/JPRO). The entire stack runs in-process — no real CAN hardware needed.

### Data flow

```
ECUSimulator  →  VirtualCANBus  →  CANInterface  →  DTCManager  →  UI
   (thread)         (queue)          (thread)        (listeners)   (main thread)
```

- `ECUSimulator` runs a background thread broadcasting J1939 frames at real PGN intervals (EEC1 at 50 Hz, temperatures at 1 Hz, etc.).  Faults are injected via `ecu.inject_fault(FaultType.X)`.
- `VirtualCANBus` is a thread-safe `queue.Queue` that stands in for a physical CAN adapter.
- `CANInterface` runs its own thread reading from the bus, decodes frames via `J1939Encoder`, and dispatches to registered callbacks (`on_live_data`, `on_dtc`, `on_raw_frame`).
- `DTCManager` receives `DTCUpdate` objects from `CANInterface`, enriches them from `dtc_database.json`, and notifies UI listeners thread-safely.
- `MainWindow` (`ui/main_window.py`) owns all backend objects, wires the callbacks, and drives UI refresh at 10 Hz via a `QTimer`.

### DTC identity

A DTC is always identified as `SPN{spn:04d}-FMI{fmi:02d}` (e.g. `SPN0110-FMI00`). This string is the key in `DTCManager._active`.

### Guided diagnosis

`ProcedureLibrary` loads `diagnostics/procedures.json` at startup. Each procedure is a decision tree; `GuidedProcedure` acts as a state machine over it. The UI (`GuidedDiagPanel`) calls `proc.choose(label)` for decision steps and `proc.advance()` for action steps. Terminal steps set `state.outcome` to `"resolved"` or `"escalate"`.

### J1939 encoding

`J1939Encoder` in `simulation/j1939_encoder.py` is the single source of truth for frame encode/decode for all five PGNs (EEC1, ET1, EFL/P1, VEP1, DM1). The DM1 decoder in `CANInterface._decode_dm1_data` manually parses the 4-byte DTC layout (SPN packed across 3 bytes + FMI in low 5 bits of byte 3).

## Key Missing Files

These are imported but not yet created — they must exist for the app to start:

| File | Imported by | Purpose |
|---|---|---|
| `heavydiag/ui/styles.py` | `main_window`, `live_data_panel`, `guided_diag_panel` | Color constants + `MAIN_STYLESHEET` |
| `heavydiag/ui/dtc_panel.py` | `main_window` | `DTCPanel` widget with `start_diagnosis_requested` signal |
| `heavydiag/diagnostics/procedures.json` | `guided_procedure.py` (`ProcedureLibrary`) | Decision tree definitions for each `PROC_*` procedure ID |
| `heavydiag/__init__.py` | Python package machinery | Required for `python -m heavydiag.main` |

`styles.py` must export: `MAIN_STYLESHEET`, `COLOR_BG_DARK`, `COLOR_BG_PANEL`, `COLOR_BG_CARD`, `COLOR_BORDER`, `COLOR_TEXT_PRIMARY`, `COLOR_TEXT_SECONDARY`, `COLOR_TEXT_MUTED`, `COLOR_ACCENT`, `COLOR_PACCAR_BLUE`, `COLOR_SUCCESS`, `COLOR_WARNING`, `COLOR_DANGER`.

`procedures.json` maps procedure IDs (e.g. `PROC_HIGH_COOLANT_TEMP`) to a dict with keys: `title`, `severity`, `warning` (optional), `tools_required` (list), and `steps` (dict of step objects). Each step has `type` (`"decision"`, `"action"`, or `"terminal"`), `instruction`, and either `choices` (dict label→next\_step\_id), `next` (str), or `outcome` (`"resolved"`/`"escalate"`). The first step must be keyed `"START"`.

## Threading Model

- **ECUSimulator thread** — writes to `VirtualCANBus` only.
- **CANInterface thread** — reads bus, calls listener callbacks directly (runs in its own thread).
- **DTCManager** — thread-safe via `threading.Lock`. Its `_notify_listeners` calls happen on the CANInterface thread. The UI `_on_dtcs_changed` slot must be safe to call from a non-main thread — in PyQt5 this works because Qt queues cross-thread signal/slot calls automatically when the signal crosses threads via `pyqtSlot`.
- **Main thread** — `QTimer` at 10 Hz polls `CANInterface.get_latest_signals()` (lock-protected) and pushes values into `LiveDataPanel`.
