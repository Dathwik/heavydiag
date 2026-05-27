"""
test_guided_procedure.py
------------------------
Unit tests for the guided diagnostic procedure state machine.

Tests verify:
  - ProcedureLibrary loads all 8 expected procedures
  - GuidedProcedure initialises at the START step (action type)
  - advance() moves past action steps; choose() branches decision steps
  - Back navigation restores previous state
  - Terminal steps mark the procedure completed
  - Progress counter increments correctly
  - Step-change callback fires on every transition
  - All 8 procedures can be instantiated without error
  - Edge cases: invalid choice, back from START, restart
"""

import pytest
from heavydiag.diagnostics.guided_procedure import (
    GuidedProcedure, ProcedureLibrary, ProcedureStep
)

# All 8 procedures defined in procedures.json
ALL_PROCEDURES = [
    ("PROC_HIGH_COOLANT_TEMP",    "SPN0110-FMI00"),
    ("PROC_LOW_OIL_PRESSURE",     "SPN0100-FMI01"),
    ("PROC_LOW_BATTERY_VOLTAGE",  "SPN0168-FMI01"),
    ("PROC_LOW_FUEL_PRESSURE",    "SPN0094-FMI01"),
    ("PROC_CTS_SHORT_HIGH",       "SPN0110-FMI03"),
    ("PROC_CTS_SHORT_LOW",        "SPN0110-FMI04"),
    ("PROC_OIL_SENSOR_SHORT",     "SPN0100-FMI03"),
    ("PROC_HIGH_BATTERY_VOLTAGE", "SPN0168-FMI00"),
]


# ===========================================================================
# ProcedureLibrary
# ===========================================================================

class TestProcedureLibrary:

    def test_library_loads_without_error(self, procedure_library):
        """ProcedureLibrary instantiates and loads procedures.json."""
        assert procedure_library is not None

    def test_expected_procedures_present(self, procedure_library):
        """All eight required procedures are in the library."""
        procs = procedure_library.list_procedures()
        for proc_id, _ in ALL_PROCEDURES:
            assert proc_id in procs

    def test_procedure_count(self, procedure_library):
        """Library contains exactly 8 procedures."""
        assert len(procedure_library.list_procedures()) == 8

    def test_get_procedure_returns_dict(self, procedure_library):
        """get_procedure() returns a dict for a known ID."""
        proc = procedure_library.get_procedure("PROC_LOW_OIL_PRESSURE")
        assert isinstance(proc, dict)

    def test_get_unknown_procedure_returns_none(self, procedure_library):
        """get_procedure() returns None for an unrecognised ID."""
        assert procedure_library.get_procedure("PROC_DOES_NOT_EXIST") is None

    def test_invalid_procedure_id_raises(self, procedure_library):
        """GuidedProcedure raises ValueError for an unknown procedure ID."""
        with pytest.raises(ValueError, match="not found"):
            GuidedProcedure(procedure_library, "PROC_FAKE", "SPN0000-FMI00")


# ===========================================================================
# Initialisation
# ===========================================================================

class TestInitialisation:

    def test_starts_at_start_step(self, procedure_library):
        """GuidedProcedure begins at the 'START' step."""
        proc = GuidedProcedure(procedure_library, "PROC_LOW_OIL_PRESSURE", "SPN0100-FMI01")
        assert proc.current_step().step_id == "START"

    def test_start_step_is_action_type(self, procedure_library):
        """The START step of every procedure is an action step (safety instruction)."""
        for proc_id, _ in ALL_PROCEDURES:
            proc = GuidedProcedure(procedure_library, proc_id, "TEST-DTC")
            assert proc.current_step().step_type == "action", (
                f"{proc_id}: expected START to be 'action', "
                f"got '{proc.current_step().step_type}'"
            )

    def test_first_decision_reached_after_advance(self, procedure_library):
        """advance() from the START action step lands on a decision step."""
        proc = GuidedProcedure(procedure_library, "PROC_LOW_OIL_PRESSURE", "SPN0100-FMI01")
        next_step = proc.advance()
        assert next_step is not None
        assert next_step.step_type == "decision"

    def test_title_is_populated(self, procedure_library):
        """Procedure title is a non-empty string."""
        proc = GuidedProcedure(procedure_library, "PROC_HIGH_COOLANT_TEMP", "SPN0110-FMI00")
        assert len(proc.title) > 0

    def test_severity_is_populated(self, procedure_library):
        """Procedure severity is a non-empty string."""
        proc = GuidedProcedure(procedure_library, "PROC_HIGH_COOLANT_TEMP", "SPN0110-FMI00")
        assert proc.severity in ("critical", "warning", "info")

    def test_not_completed_at_start(self, procedure_library):
        """Procedure is not completed immediately after creation."""
        proc = GuidedProcedure(procedure_library, "PROC_LOW_OIL_PRESSURE", "SPN0100-FMI01")
        assert proc.state.completed is False

    def test_progress_starts_at_zero(self, procedure_library):
        """Progress counter is (0, N) at the start."""
        proc = GuidedProcedure(procedure_library, "PROC_LOW_OIL_PRESSURE", "SPN0100-FMI01")
        taken, total = proc.progress()
        assert taken == 0
        assert total > 0

    def test_cannot_go_back_at_start(self, procedure_library):
        """can_go_back() returns False at the first step."""
        proc = GuidedProcedure(procedure_library, "PROC_LOW_OIL_PRESSURE", "SPN0100-FMI01")
        assert proc.can_go_back() is False


# ===========================================================================
# Action step navigation
# ===========================================================================

class TestActionNavigation:

    def test_advance_on_action_step_moves_forward(self, procedure_library):
        """advance() on the START action step moves to the next step."""
        proc = GuidedProcedure(procedure_library, "PROC_LOW_OIL_PRESSURE", "SPN0100-FMI01")
        assert proc.current_step().step_type == "action"
        next_step = proc.advance()
        assert next_step is not None
        assert next_step.step_id != "START"

    def test_advance_on_decision_step_returns_none(self, procedure_library):
        """advance() on a decision step returns None (wrong method)."""
        proc = GuidedProcedure(procedure_library, "PROC_LOW_OIL_PRESSURE", "SPN0100-FMI01")
        proc.advance()  # Past START → CHECK_OIL_LEVEL (decision)
        assert proc.current_step().step_type == "decision"
        result = proc.advance()
        assert result is None

    def test_advance_records_history(self, procedure_library):
        """advance() records 'completed' in the step history."""
        proc = GuidedProcedure(procedure_library, "PROC_LOW_OIL_PRESSURE", "SPN0100-FMI01")
        proc.advance()  # START (action) → CHECK_OIL_LEVEL
        _, choice = proc.state.step_history[-1]
        assert choice == "completed"

    def test_advance_on_intermediate_action_step(self, procedure_library):
        """advance() also works on action steps mid-procedure (e.g. RECHECK_PRESSURE)."""
        proc = GuidedProcedure(procedure_library, "PROC_LOW_OIL_PRESSURE", "SPN0100-FMI01")
        proc.advance()                               # START → CHECK_OIL_LEVEL
        proc.choose("Yes — oil level is OK")         # → CHECK_OIL_QUALITY
        proc.choose("Yes — oil looks normal")        # → RECHECK_PRESSURE (action)
        assert proc.current_step().step_type == "action"
        next_step = proc.advance()                   # → PRESSURE_OK
        assert next_step is not None
        assert next_step.step_id == "PRESSURE_OK"


# ===========================================================================
# Decision step navigation
# ===========================================================================

class TestDecisionNavigation:

    @pytest.fixture
    def oil_proc(self, procedure_library):
        """PROC_LOW_OIL_PRESSURE advanced past the START action step."""
        proc = GuidedProcedure(procedure_library, "PROC_LOW_OIL_PRESSURE", "SPN0100-FMI01")
        proc.advance()  # START (action) → CHECK_OIL_LEVEL (decision)
        return proc

    def test_choose_first_option_advances(self, oil_proc):
        """Choosing the first option moves to a different step."""
        step = oil_proc.current_step()
        first_choice = list(step.choices.keys())[0]
        next_step = oil_proc.choose(first_choice)
        assert next_step is not None
        assert next_step.step_id != "CHECK_OIL_LEVEL"

    def test_choose_second_option_advances(self, oil_proc):
        """Choosing the second option also advances (different branch)."""
        step = oil_proc.current_step()
        choices = list(step.choices.keys())
        if len(choices) >= 2:
            next_step = oil_proc.choose(choices[1])
            assert next_step is not None
            assert next_step.step_id != "CHECK_OIL_LEVEL"

    def test_invalid_choice_returns_none(self, oil_proc):
        """choose() with an invalid label returns None and does not advance."""
        result = oil_proc.choose("this choice does not exist")
        assert result is None
        assert oil_proc.current_step().step_id == "CHECK_OIL_LEVEL"

    def test_progress_increments_after_choice(self, oil_proc):
        """Progress taken-count increments after each decision (advance already counted 1)."""
        step = oil_proc.current_step()
        first_choice = list(step.choices.keys())[0]
        oil_proc.choose(first_choice)
        taken, _ = oil_proc.progress()
        assert taken == 2  # 1 from advance() in fixture + 1 from choose()

    def test_step_history_records_choice(self, oil_proc):
        """Step history stores (step_id, choice_label) tuples for decision steps."""
        step = oil_proc.current_step()
        choice = list(step.choices.keys())[0]
        oil_proc.choose(choice)
        # fixture's advance() already added one entry; this choose() adds another
        assert len(oil_proc.state.step_history) == 2
        step_id, recorded_choice = oil_proc.state.step_history[-1]
        assert step_id == "CHECK_OIL_LEVEL"
        assert recorded_choice == choice

    def test_choose_on_action_step_returns_none(self, oil_proc):
        """choose() on an action step returns None (wrong method)."""
        oil_proc.choose("No — oil level is low")  # → ADD_OIL (action)
        step = oil_proc.current_step()
        if step.step_type == "action":
            result = oil_proc.choose("anything")
            assert result is None

    def test_choose_yes_oil_ok_reaches_quality_check(self, oil_proc):
        """'Yes — oil level is OK' navigates to the oil quality check step."""
        next_step = oil_proc.choose("Yes — oil level is OK")
        assert next_step is not None
        assert next_step.step_id == "CHECK_OIL_QUALITY"

    def test_choose_low_oil_reaches_add_oil(self, oil_proc):
        """'No — oil level is low' navigates to the add-oil action step."""
        next_step = oil_proc.choose("No — oil level is low")
        assert next_step is not None
        assert next_step.step_id == "ADD_OIL"


# ===========================================================================
# Back navigation
# ===========================================================================

class TestBackNavigation:

    def test_go_back_restores_previous_step(self, procedure_library):
        """go_back() returns to the previous step."""
        proc = GuidedProcedure(procedure_library, "PROC_LOW_OIL_PRESSURE", "SPN0100-FMI01")
        proc.advance()  # START (action) → CHECK_OIL_LEVEL
        assert proc.current_step().step_id != "START"
        proc.go_back()
        assert proc.current_step().step_id == "START"

    def test_can_go_back_after_one_step(self, procedure_library):
        """can_go_back() returns True after the first navigation."""
        proc = GuidedProcedure(procedure_library, "PROC_LOW_OIL_PRESSURE", "SPN0100-FMI01")
        proc.advance()  # START → CHECK_OIL_LEVEL
        assert proc.can_go_back() is True

    def test_go_back_from_start_returns_none(self, procedure_library):
        """go_back() at the START step returns None without raising."""
        proc = GuidedProcedure(procedure_library, "PROC_LOW_OIL_PRESSURE", "SPN0100-FMI01")
        result = proc.go_back()
        assert result is None

    def test_go_back_clears_completed_flag(self, procedure_library):
        """go_back() from a terminal step clears the completed flag."""
        proc = GuidedProcedure(procedure_library, "PROC_LOW_OIL_PRESSURE", "SPN0100-FMI01")
        # Navigate to RESOLVED (terminal):
        # START → CHECK_OIL_LEVEL → CHECK_OIL_QUALITY → RECHECK_PRESSURE → PRESSURE_OK → RESOLVED
        proc.advance()                              # START → CHECK_OIL_LEVEL
        proc.choose("Yes — oil level is OK")        # → CHECK_OIL_QUALITY
        proc.choose("Yes — oil looks normal")       # → RECHECK_PRESSURE (action)
        proc.advance()                              # → PRESSURE_OK
        proc.choose("Yes — pressure is normal")     # → RESOLVED (terminal)
        assert proc.state.completed is True
        proc.go_back()
        assert proc.state.completed is False

    def test_go_back_after_decision_returns_to_decision(self, procedure_library):
        """go_back() from a mid-procedure decision returns to the previous decision."""
        proc = GuidedProcedure(procedure_library, "PROC_LOW_OIL_PRESSURE", "SPN0100-FMI01")
        proc.advance()                              # START → CHECK_OIL_LEVEL
        proc.choose("Yes — oil level is OK")        # → CHECK_OIL_QUALITY
        proc.go_back()
        assert proc.current_step().step_id == "CHECK_OIL_LEVEL"


# ===========================================================================
# Terminal steps (resolved / escalate)
# ===========================================================================

class TestTerminalSteps:

    def test_resolved_terminal_marks_completed(self, procedure_library):
        """Reaching a 'resolved' terminal step sets state.completed = True."""
        proc = GuidedProcedure(procedure_library, "PROC_LOW_OIL_PRESSURE", "SPN0100-FMI01")
        proc.advance()                              # START → CHECK_OIL_LEVEL
        proc.choose("Yes — oil level is OK")        # → CHECK_OIL_QUALITY
        proc.choose("Yes — oil looks normal")       # → RECHECK_PRESSURE (action)
        proc.advance()                              # → PRESSURE_OK
        proc.choose("Yes — pressure is normal")     # → RESOLVED (terminal)
        assert proc.state.completed is True
        assert proc.state.outcome == "resolved"

    def test_escalate_terminal_marks_completed(self, procedure_library):
        """Reaching an 'escalate' terminal step also sets state.completed = True."""
        proc = GuidedProcedure(procedure_library, "PROC_LOW_OIL_PRESSURE", "SPN0100-FMI01")
        proc.advance()                              # START → CHECK_OIL_LEVEL
        proc.choose("Yes — oil level is OK")        # → CHECK_OIL_QUALITY
        proc.choose("Yes — oil looks normal")       # → RECHECK_PRESSURE (action)
        proc.advance()                              # → PRESSURE_OK
        proc.choose("No — pressure still low")      # → ESCALATE_PUMP (terminal)
        assert proc.state.completed is True
        assert proc.state.outcome == "escalate"

    def test_contamination_path_escalates(self, procedure_library):
        """Contaminated oil path leads to an escalate terminal step."""
        proc = GuidedProcedure(procedure_library, "PROC_LOW_OIL_PRESSURE", "SPN0100-FMI01")
        proc.advance()                                          # START → CHECK_OIL_LEVEL
        proc.choose("Yes — oil level is OK")                    # → CHECK_OIL_QUALITY
        proc.choose("No — oil appears milky or contaminated")   # → ESCALATE_CONTAMINATION
        assert proc.state.completed is True
        assert proc.state.outcome == "escalate"

    def test_terminal_step_type_is_terminal(self, procedure_library):
        """RESOLVED step has step_type == 'terminal'."""
        proc = GuidedProcedure(procedure_library, "PROC_LOW_OIL_PRESSURE", "SPN0100-FMI01")
        terminal_step = proc._steps.get("RESOLVED")
        assert terminal_step is not None
        assert terminal_step.step_type == "terminal"

    def test_resolved_step_has_resolved_outcome(self, procedure_library):
        """RESOLVED terminal step has outcome == 'resolved'."""
        proc = GuidedProcedure(procedure_library, "PROC_LOW_OIL_PRESSURE", "SPN0100-FMI01")
        resolved = proc._steps.get("RESOLVED")
        assert resolved is not None
        assert resolved.outcome == "resolved"

    def test_escalate_step_has_escalate_outcome(self, procedure_library):
        """ESCALATE_PUMP terminal step has outcome == 'escalate'."""
        proc = GuidedProcedure(procedure_library, "PROC_LOW_OIL_PRESSURE", "SPN0100-FMI01")
        escalate = proc._steps.get("ESCALATE_PUMP")
        assert escalate is not None
        assert escalate.outcome == "escalate"


# ===========================================================================
# Step-change callback
# ===========================================================================

class TestStepChangeCallback:

    def test_callback_fired_on_advance(self, procedure_library):
        """on_step_change callback is invoked when advance() moves forward."""
        proc = GuidedProcedure(procedure_library, "PROC_LOW_OIL_PRESSURE", "SPN0100-FMI01")
        received = []
        proc.on_step_change(lambda step: received.append(step.step_id))
        proc.advance()  # START (action) → CHECK_OIL_LEVEL
        assert len(received) == 1

    def test_callback_fired_on_choose(self, procedure_library):
        """on_step_change callback is invoked when choose() advances the step."""
        proc = GuidedProcedure(procedure_library, "PROC_LOW_OIL_PRESSURE", "SPN0100-FMI01")
        proc.advance()  # Past START action step → CHECK_OIL_LEVEL (decision)
        received = []
        proc.on_step_change(lambda step: received.append(step.step_id))
        choice = list(proc.current_step().choices.keys())[0]
        proc.choose(choice)
        assert len(received) == 1

    def test_callback_fired_on_go_back(self, procedure_library):
        """on_step_change callback is invoked when go_back() is used."""
        proc = GuidedProcedure(procedure_library, "PROC_LOW_OIL_PRESSURE", "SPN0100-FMI01")
        proc.advance()  # START → CHECK_OIL_LEVEL
        received = []
        proc.on_step_change(lambda step: received.append(step.step_id))
        proc.go_back()  # CHECK_OIL_LEVEL → START
        assert len(received) == 1
        assert received[0] == "START"

    def test_callback_receives_step_object(self, procedure_library):
        """Callback receives a ProcedureStep object, not just a string."""
        proc = GuidedProcedure(procedure_library, "PROC_LOW_OIL_PRESSURE", "SPN0100-FMI01")
        received = []
        proc.on_step_change(lambda step: received.append(step))
        proc.advance()
        assert len(received) == 1
        assert hasattr(received[0], "step_id")
        assert hasattr(received[0], "step_type")
        assert hasattr(received[0], "instruction")


# ===========================================================================
# All 8 procedures — smoke tests
# ===========================================================================

class TestAllProcedures:

    @pytest.mark.parametrize("proc_id,dtc_code", ALL_PROCEDURES)
    def test_procedure_instantiates(self, procedure_library, proc_id, dtc_code):
        """Every procedure can be instantiated without error."""
        proc = GuidedProcedure(procedure_library, proc_id, dtc_code)
        assert proc.current_step() is not None

    @pytest.mark.parametrize("proc_id,dtc_code", ALL_PROCEDURES)
    def test_procedure_has_start_step(self, procedure_library, proc_id, dtc_code):
        """Every procedure has a START step."""
        proc = GuidedProcedure(procedure_library, proc_id, dtc_code)
        assert proc._steps.get("START") is not None

    @pytest.mark.parametrize("proc_id,dtc_code", ALL_PROCEDURES)
    def test_start_step_instruction_is_nonempty(self, procedure_library, proc_id, dtc_code):
        """Every START step has a non-empty instruction string."""
        proc = GuidedProcedure(procedure_library, proc_id, dtc_code)
        assert len(proc.current_step().instruction) > 0

    @pytest.mark.parametrize("proc_id,dtc_code", ALL_PROCEDURES)
    def test_advance_then_choose_advances_all_procedures(self, procedure_library, proc_id, dtc_code):
        """advance() past action START, then first choice advances to a new step."""
        proc = GuidedProcedure(procedure_library, proc_id, dtc_code)
        proc.advance()  # START (action) → first decision step
        step = proc.current_step()
        assert step.step_type == "decision", (
            f"{proc_id}: expected decision after START advance, got '{step.step_type}'"
        )
        first_choice = list(step.choices.keys())[0]
        next_step = proc.choose(first_choice)
        assert next_step is not None
        assert next_step.step_id != "START"

    @pytest.mark.parametrize("proc_id,dtc_code", ALL_PROCEDURES)
    def test_build_summary_works(self, procedure_library, proc_id, dtc_code):
        """build_summary() returns a dict with required keys for every procedure."""
        proc = GuidedProcedure(procedure_library, proc_id, dtc_code)
        summary = proc.build_summary()
        assert "procedure_id"    in summary
        assert "procedure_title" in summary
        assert "dtc_code"        in summary
        assert "outcome"         in summary
        assert "steps_taken"     in summary

    @pytest.mark.parametrize("proc_id,dtc_code", ALL_PROCEDURES)
    def test_procedure_has_at_least_one_terminal_step(self, procedure_library, proc_id, dtc_code):
        """Every procedure must contain at least one terminal step."""
        proc = GuidedProcedure(procedure_library, proc_id, dtc_code)
        terminal_steps = [
            s for s in proc._steps.values()
            if s.step_type == "terminal"
        ]
        assert len(terminal_steps) >= 1, (
            f"{proc_id}: no terminal steps found"
        )
