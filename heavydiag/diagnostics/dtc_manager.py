# DTC lookup and management
"""
dtc_manager.py
--------------
Manages Diagnostic Trouble Codes (DTCs) received from the CAN interface.

Responsibilities:
  - Receive DTC updates from CANInterface and maintain an active/historical log
  - Look up component info and procedure IDs from the DTC database
  - Notify the UI when DTCs change (new fault, fault cleared)
  - Persist DTC history for the session report
"""

import json
import os
import threading
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Callable, Optional

from heavydiag.simulation.j1939_encoder import DTCFrame
from heavydiag.comms.can_interface import DTCUpdate


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

class DTCSeverity(Enum):
    CRITICAL = "critical"
    WARNING  = "warning"
    INFO     = "info"

    @property
    def color(self) -> str:
        return {"critical": "#FF4444", "warning": "#FFA500", "info": "#4488FF"}[self.value]

    @property
    def icon(self) -> str:
        return {"critical": "🔴", "warning": "🟡", "info": "🔵"}[self.value]


@dataclass
class ManagedDTC:
    """A fully resolved DTC entry with database metadata."""
    dtc_code: str           # e.g. "SPN0110-FMI00"
    spn: int
    fmi: int
    occurrence_count: int
    first_seen: float       # Unix timestamp
    last_seen: float
    active: bool

    # From DTC database
    component_name: str     = "Unknown Component"
    subsystem: str          = "Unknown"
    fmi_cause: str          = "Unknown"
    root_cause_hint: str    = ""
    procedure_id: str       = ""
    severity: DTCSeverity   = DTCSeverity.WARNING

    # Steps taken during guided diagnosis
    diagnosis_log: list[str] = field(default_factory=list)
    resolution: str          = ""   # "resolved", "escalate", or ""

    def fmi_description(self) -> str:
        return DTCFrame(spn=self.spn, fmi=self.fmi, oc=1, active=True).fmi_description()

    def age_str(self) -> str:
        elapsed = time.time() - self.first_seen
        if elapsed < 60:
            return f"{int(elapsed)}s ago"
        elif elapsed < 3600:
            return f"{int(elapsed/60)}m ago"
        else:
            return f"{elapsed/3600:.1f}h ago"

    def to_dict(self) -> dict:
        return {
            "dtc_code":        self.dtc_code,
            "spn":             self.spn,
            "fmi":             self.fmi,
            "occurrence_count": self.occurrence_count,
            "first_seen":      self.first_seen,
            "last_seen":       self.last_seen,
            "active":          self.active,
            "component_name":  self.component_name,
            "subsystem":       self.subsystem,
            "fmi_cause":       self.fmi_cause,
            "root_cause_hint": self.root_cause_hint,
            "severity":        self.severity.value,
            "diagnosis_log":   self.diagnosis_log,
            "resolution":      self.resolution,
        }


# ---------------------------------------------------------------------------
# DTC Manager
# ---------------------------------------------------------------------------

class DTCManager:
    """
    Central store for all DTCs seen during a diagnostic session.

    Thread-safe: the CAN interface calls on_dtc_update() from its
    background thread; the UI reads DTCs from the main thread.
    """

    DB_PATH = os.path.join(os.path.dirname(__file__), "dtc_database.json")

    def __init__(self):
        self._lock     = threading.Lock()
        self._active:  dict[str, ManagedDTC] = {}   # key = dtc_code
        self._history: list[ManagedDTC]      = []

        self._change_listeners: list[Callable[[list[ManagedDTC]], None]] = []

        # Load DTC database
        self._db = self._load_database()

    # ------------------------------------------------------------------
    # Listener registration
    # ------------------------------------------------------------------

    def on_change(self, callback: Callable[[list[ManagedDTC]], None]):
        """Register a callback invoked whenever the active DTC list changes."""
        self._change_listeners.append(callback)

    # ------------------------------------------------------------------
    # Called by CANInterface listener
    # ------------------------------------------------------------------

    def on_dtc_update(self, update: DTCUpdate):
        """Process incoming DTC broadcast from CAN bus."""
        changed = False
        with self._lock:
            # Mark codes currently active from this source
            seen_codes = set()
            for dtc_frame in update.dtcs:
                code = f"SPN{dtc_frame.spn:04d}-FMI{dtc_frame.fmi:02d}"
                seen_codes.add(code)
                if code in self._active:
                    # Update existing entry
                    entry = self._active[code]
                    entry.last_seen = update.timestamp
                    entry.occurrence_count = max(entry.occurrence_count,
                                                  dtc_frame.oc)
                    entry.active = True
                else:
                    # New DTC
                    entry = self._build_managed_dtc(dtc_frame, update.timestamp)
                    self._active[code] = entry
                    self._history.append(entry)
                    changed = True

        if changed:
            self._notify_listeners()

    def clear_all_active(self):
        """Simulate an ECM 'clear DTCs' command."""
        with self._lock:
            for entry in self._active.values():
                entry.active   = False
                entry.resolution = "cleared"
            self._active.clear()
        self._notify_listeners()

    # ------------------------------------------------------------------
    # Data access
    # ------------------------------------------------------------------

    def get_active_dtcs(self) -> list[ManagedDTC]:
        with self._lock:
            return list(self._active.values())

    def get_history(self) -> list[ManagedDTC]:
        with self._lock:
            return list(self._history)

    def get_dtc(self, dtc_code: str) -> Optional[ManagedDTC]:
        with self._lock:
            return self._active.get(dtc_code) or next(
                (d for d in self._history if d.dtc_code == dtc_code), None
            )

    def log_diagnosis_step(self, dtc_code: str, step_text: str):
        """Record a technician step taken during guided diagnosis."""
        with self._lock:
            entry = self._active.get(dtc_code)
            if entry:
                entry.diagnosis_log.append(
                    f"[{time.strftime('%H:%M:%S')}] {step_text}"
                )

    def set_resolution(self, dtc_code: str, outcome: str):
        """Mark a DTC as resolved or escalated."""
        with self._lock:
            entry = self._active.get(dtc_code)
            if entry:
                entry.resolution = outcome
                if outcome == "resolved":
                    entry.active = False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_managed_dtc(self, dtc_frame: DTCFrame, timestamp: float) -> ManagedDTC:
        """Create a ManagedDTC by enriching raw frame data from the database."""
        code     = f"SPN{dtc_frame.spn:04d}-FMI{dtc_frame.fmi:02d}"
        spn_str  = str(dtc_frame.spn)
        fmi_str  = str(dtc_frame.fmi)

        spn_info = self._db.get("spns", {}).get(spn_str, {})
        fmi_info = spn_info.get("fmi_details", {}).get(fmi_str, {})

        # Determine severity from known critical SPNs
        critical_spns = {100, 110}   # Oil pressure, coolant temp
        severity = (DTCSeverity.CRITICAL if dtc_frame.spn in critical_spns
                    else DTCSeverity.WARNING)

        return ManagedDTC(
            dtc_code       = code,
            spn            = dtc_frame.spn,
            fmi            = dtc_frame.fmi,
            occurrence_count = dtc_frame.oc,
            first_seen     = timestamp,
            last_seen      = timestamp,
            active         = dtc_frame.active,
            component_name = spn_info.get("name", f"SPN {dtc_frame.spn}"),
            subsystem      = spn_info.get("subsystem", "Unknown"),
            fmi_cause      = fmi_info.get("cause", dtc_frame.fmi_description()),
            root_cause_hint = fmi_info.get("likely_root_cause", ""),
            procedure_id   = fmi_info.get("procedure_id", ""),
            severity       = severity,
        )

    def _load_database(self) -> dict:
        try:
            with open(self.DB_PATH, "r") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {"spns": {}}

    def _notify_listeners(self):
        active = self.get_active_dtcs()
        for cb in self._change_listeners:
            cb(active)