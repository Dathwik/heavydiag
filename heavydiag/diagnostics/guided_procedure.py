# Guided diagnostic procedures
"""
guided_procedure.py
-------------------
Loads and navigates step-by-step diagnostic procedure trees.

A procedure is a decision tree stored in procedures.json where each node is
either:
  - "decision"  — asks the technician a yes/no or multiple-choice question
  - "action"    — tells the technician to perform an action, then advances
  - "terminal"  — end state (resolved or escalate)

The GuidedProcedure class acts as a state machine: it holds the current step
and advances based on the technician's choice.

This is the core of what PACCAR's off-board diagnostic tools do — instead of
a technician guessing, they follow a validated decision tree that leads to the
correct root cause.
"""

import json
import os
import time
from dataclasses import dataclass, field
from typing import Optional, Callable


PROCEDURES_PATH = os.path.join(os.path.dirname(__file__), "procedures.json")


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class ProcedureStep:
    """One node in the diagnostic decision tree."""
    step_id: str
    instruction: str
    step_type: str          # "decision", "action", "terminal"
    choices: dict           # For decision steps: {label: next_step_id}
    next_step_id: str       # For action steps
    outcome: str            # For terminal steps: "resolved" or "escalate"


@dataclass
class ProcedureState:
    """Tracks progress through a procedure for one DTC."""
    procedure_id: str
    dtc_code: str
    current_step_id: str
    step_history: list[tuple[str, str]] = field(default_factory=list)
    # Each entry: (step_id, choice_made)
    completed: bool = False
    outcome: str    = ""     # "resolved", "escalate", or ""
    start_time: float = field(default_factory=time.time)


# ---------------------------------------------------------------------------
# Procedure loader
# ---------------------------------------------------------------------------

class ProcedureLibrary:
    """Loads all procedures from procedures.json into memory."""

    def __init__(self, path: str = PROCEDURES_PATH):
        self._procedures: dict[str, dict] = {}
        self._load(path)

    def _load(self, path: str):
        try:
            with open(path, "r") as f:
                raw = json.load(f)
            for key, val in raw.items():
                if key.startswith("_"):
                    continue
                self._procedures[key] = val
        except (FileNotFoundError, json.JSONDecodeError) as e:
            print(f"Warning: Could not load procedures: {e}")

    def get_procedure(self, procedure_id: str) -> Optional[dict]:
        return self._procedures.get(procedure_id)

    def list_procedures(self) -> list[str]:
        return list(self._procedures.keys())


# ---------------------------------------------------------------------------
# Guided Procedure — state machine
# ---------------------------------------------------------------------------

class GuidedProcedure:
    """
    State machine for navigating one diagnostic procedure.

    Usage:
        proc = GuidedProcedure(library, "PROC_LOW_OIL_PRESSURE", "SPN0100-FMI01")
        step = proc.current_step()        # Get current step info
        proc.choose("Yes — oil level is OK")  # Advance via a decision choice
        proc.advance()                    # Advance an action step
    """

    def __init__(self, library: ProcedureLibrary,
                 procedure_id: str, dtc_code: str):
        self._library = library
        raw = library.get_procedure(procedure_id)
        if not raw:
            raise ValueError(f"Procedure '{procedure_id}' not found in library")

        self._raw        = raw
        self._steps: dict[str, ProcedureStep] = self._parse_steps(raw)
        self.state       = ProcedureState(procedure_id=procedure_id,
                                           dtc_code=dtc_code,
                                           current_step_id="START")

        # Metadata
        self.title        = raw.get("title", procedure_id)
        self.severity     = raw.get("severity", "warning")
        self.warning      = raw.get("warning", "")
        self.tools_needed = raw.get("tools_required", [])

        # Step-change callback
        self._on_step_change: Optional[Callable[[ProcedureStep], None]] = None

    def on_step_change(self, callback: Callable[[ProcedureStep], None]):
        """Register callback invoked when the current step changes."""
        self._on_step_change = callback

    def current_step(self) -> Optional[ProcedureStep]:
        return self._steps.get(self.state.current_step_id)

    def choose(self, choice_label: str) -> Optional[ProcedureStep]:
        """
        For decision steps: advance to the next step based on the technician's choice.
        Returns the new current step, or None if invalid.
        """
        step = self.current_step()
        if not step or step.step_type != "decision":
            return None
        next_id = step.choices.get(choice_label)
        if not next_id:
            return None
        self.state.step_history.append((step.step_id, choice_label))
        self._advance_to(next_id)
        return self.current_step()

    def advance(self) -> Optional[ProcedureStep]:
        """
        For action steps: advance to the next step (no choice needed).
        Returns the new current step.
        """
        step = self.current_step()
        if not step or step.step_type != "action":
            return None
        self.state.step_history.append((step.step_id, "completed"))
        self._advance_to(step.next_step_id)
        return self.current_step()

    def can_go_back(self) -> bool:
        return len(self.state.step_history) > 0

    def go_back(self) -> Optional[ProcedureStep]:
        """Navigate back one step in the history."""
        if not self.state.step_history:
            return None
        prev_step_id, _ = self.state.step_history.pop()
        self.state.current_step_id = prev_step_id
        self.state.completed       = False
        self.state.outcome         = ""
        if self._on_step_change:
            self._on_step_change(self.current_step())
        return self.current_step()

    def progress(self) -> tuple[int, int]:
        """Returns (steps_taken, estimated_total) for a progress indicator."""
        taken   = len(self.state.step_history)
        total   = max(len(self._steps), taken + 1)
        return taken, total

    def elapsed_time_str(self) -> str:
        elapsed = time.time() - self.state.start_time
        mins, secs = divmod(int(elapsed), 60)
        return f"{mins:02d}:{secs:02d}"

    def build_summary(self) -> dict:
        """Returns a summary dict suitable for the report generator."""
        return {
            "procedure_id":   self.state.procedure_id,
            "procedure_title": self.title,
            "dtc_code":       self.state.dtc_code,
            "outcome":        self.state.outcome,
            "steps_taken":    len(self.state.step_history),
            "elapsed":        self.elapsed_time_str(),
            "step_history": [
                {"step": sid, "choice": choice}
                for sid, choice in self.state.step_history
            ],
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _advance_to(self, step_id: str):
        self.state.current_step_id = step_id
        step = self._steps.get(step_id)
        if step and step.step_type == "terminal":
            self.state.completed = True
            self.state.outcome   = step.outcome
        if self._on_step_change and step:
            self._on_step_change(step)

    def _parse_steps(self, raw: dict) -> dict[str, ProcedureStep]:
        steps = {}
        for step_id, step_data in raw.get("steps", {}).items():
            steps[step_id] = ProcedureStep(
                step_id      = step_id,
                instruction  = step_data.get("instruction", ""),
                step_type    = step_data.get("type", "action"),
                choices      = step_data.get("choices", {}),
                next_step_id = step_data.get("next", ""),
                outcome      = step_data.get("outcome", ""),
            )
        return steps