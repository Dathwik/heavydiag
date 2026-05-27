"""
test_dtc_manager.py
-------------------
Unit tests for the DTCManager.

Tests verify:
  - DTCs are created correctly from raw J1939 DTCUpdate events
  - Database enrichment (component name, subsystem, FMI cause, procedure ID)
  - Severity classification (critical vs warning)
  - Occurrence count tracking across repeated broadcasts
  - Multiple simultaneous active DTCs
  - clear_all_active() empties the active list
  - History is preserved after clearing
  - Diagnosis step logging
  - Resolution setting (resolved / escalate)
  - Change listener callbacks fire on new DTCs
"""

import time
import pytest

from heavydiag.diagnostics.dtc_manager import DTCManager, DTCSeverity, ManagedDTC
from heavydiag.simulation.j1939_encoder import DTCFrame
from heavydiag.comms.can_interface import DTCUpdate


# ===========================================================================
# DTC creation and database enrichment
# ===========================================================================

class TestDTCCreation:

    def test_coolant_dtc_created(self, dtc_manager, coolant_dtc_update):
        """A coolant temp DTC (SPN 110, FMI 0) is created as an active entry."""
        dtc_manager.on_dtc_update(coolant_dtc_update)
        active = dtc_manager.get_active_dtcs()
        assert len(active) == 1
        assert active[0].dtc_code == "SPN0110-FMI00"

    def test_dtc_component_name_enriched(self, dtc_manager, coolant_dtc_update):
        """DTCManager enriches the raw SPN with its component name from the database."""
        dtc_manager.on_dtc_update(coolant_dtc_update)
        dtc = dtc_manager.get_active_dtcs()[0]
        assert "Coolant" in dtc.component_name or "Temperature" in dtc.component_name

    def test_dtc_subsystem_enriched(self, dtc_manager, coolant_dtc_update):
        """DTCManager populates the subsystem field from the database."""
        dtc_manager.on_dtc_update(coolant_dtc_update)
        dtc = dtc_manager.get_active_dtcs()[0]
        assert len(dtc.subsystem) > 0
        assert dtc.subsystem != "Unknown"

    def test_dtc_fmi_cause_enriched(self, dtc_manager, coolant_dtc_update):
        """DTCManager populates fmi_cause with a human-readable description."""
        dtc_manager.on_dtc_update(coolant_dtc_update)
        dtc = dtc_manager.get_active_dtcs()[0]
        assert len(dtc.fmi_cause) > 0

    def test_dtc_procedure_id_assigned(self, dtc_manager, coolant_dtc_update):
        """Known DTC (SPN 110 FMI 0) maps to a procedure ID."""
        dtc_manager.on_dtc_update(coolant_dtc_update)
        dtc = dtc_manager.get_active_dtcs()[0]
        assert dtc.procedure_id == "PROC_HIGH_COOLANT_TEMP"

    def test_oil_pressure_procedure_id(self, dtc_manager, oil_pressure_dtc_update):
        """Oil pressure DTC (SPN 100 FMI 1) maps to PROC_LOW_OIL_PRESSURE."""
        dtc_manager.on_dtc_update(oil_pressure_dtc_update)
        dtc = dtc_manager.get_active_dtcs()[0]
        assert dtc.procedure_id == "PROC_LOW_OIL_PRESSURE"

    def test_battery_procedure_id(self, dtc_manager, battery_dtc_update):
        """Battery DTC (SPN 168 FMI 1) maps to PROC_LOW_BATTERY_VOLTAGE."""
        dtc_manager.on_dtc_update(battery_dtc_update)
        dtc = dtc_manager.get_active_dtcs()[0]
        assert dtc.procedure_id == "PROC_LOW_BATTERY_VOLTAGE"

    def test_dtc_is_active_on_creation(self, dtc_manager, coolant_dtc_update):
        """Newly received DTC is marked active=True."""
        dtc_manager.on_dtc_update(coolant_dtc_update)
        dtc = dtc_manager.get_active_dtcs()[0]
        assert dtc.active is True

    def test_dtc_timestamps_set(self, dtc_manager, coolant_dtc_update):
        """first_seen and last_seen timestamps are populated."""
        before = time.time()
        dtc_manager.on_dtc_update(coolant_dtc_update)
        after = time.time()
        dtc = dtc_manager.get_active_dtcs()[0]
        assert before - 0.1 <= dtc.first_seen <= after + 0.1
        assert before - 0.1 <= dtc.last_seen  <= after + 0.1


# ===========================================================================
# Severity classification
# ===========================================================================

class TestSeverity:

    def test_coolant_temp_is_critical(self, dtc_manager, coolant_dtc_update):
        """Engine Coolant Temp (SPN 110) is classified as CRITICAL."""
        dtc_manager.on_dtc_update(coolant_dtc_update)
        dtc = dtc_manager.get_active_dtcs()[0]
        assert dtc.severity == DTCSeverity.CRITICAL

    def test_oil_pressure_is_critical(self, dtc_manager, oil_pressure_dtc_update):
        """Engine Oil Pressure (SPN 100) is classified as CRITICAL."""
        dtc_manager.on_dtc_update(oil_pressure_dtc_update)
        dtc = dtc_manager.get_active_dtcs()[0]
        assert dtc.severity == DTCSeverity.CRITICAL

    def test_battery_voltage_is_warning(self, dtc_manager, battery_dtc_update):
        """Battery Voltage (SPN 168) is classified as WARNING."""
        dtc_manager.on_dtc_update(battery_dtc_update)
        dtc = dtc_manager.get_active_dtcs()[0]
        assert dtc.severity == DTCSeverity.WARNING

    def test_severity_has_color(self, dtc_manager, coolant_dtc_update):
        """Severity enum exposes a non-empty color string."""
        dtc_manager.on_dtc_update(coolant_dtc_update)
        dtc = dtc_manager.get_active_dtcs()[0]
        assert dtc.severity.color.startswith("#")

    def test_severity_has_icon(self, dtc_manager, coolant_dtc_update):
        """Severity enum exposes a non-empty icon string."""
        dtc_manager.on_dtc_update(coolant_dtc_update)
        dtc = dtc_manager.get_active_dtcs()[0]
        assert len(dtc.severity.icon) > 0


# ===========================================================================
# Occurrence count and repeated updates
# ===========================================================================

class TestOccurrenceTracking:

    def test_occurrence_count_from_frame(self, dtc_manager, oil_pressure_dtc_update):
        """Occurrence count from the DTC frame is stored correctly."""
        dtc_manager.on_dtc_update(oil_pressure_dtc_update)
        dtc = dtc_manager.get_active_dtcs()[0]
        assert dtc.occurrence_count == 2   # oil_pressure_dtc_update fixture has oc=2

    def test_repeated_update_does_not_duplicate(self, dtc_manager, coolant_dtc_update):
        """Sending the same DTC twice creates only one active entry."""
        dtc_manager.on_dtc_update(coolant_dtc_update)
        dtc_manager.on_dtc_update(coolant_dtc_update)
        assert len(dtc_manager.get_active_dtcs()) == 1

    def test_repeated_update_refreshes_last_seen(self, dtc_manager):
        """last_seen timestamp is updated on subsequent broadcasts."""
        update1 = DTCUpdate(
            dtcs=[DTCFrame(spn=110, fmi=0, oc=1, active=True)],
            source_address=0x00,
            timestamp=time.time() - 5.0,   # 5 seconds ago
        )
        dtc_manager.on_dtc_update(update1)
        first_seen = dtc_manager.get_active_dtcs()[0].first_seen

        time.sleep(0.05)

        update2 = DTCUpdate(
            dtcs=[DTCFrame(spn=110, fmi=0, oc=2, active=True)],
            source_address=0x00,
            timestamp=time.time(),
        )
        dtc_manager.on_dtc_update(update2)
        dtc = dtc_manager.get_active_dtcs()[0]

        assert dtc.first_seen == first_seen        # first_seen unchanged
        assert dtc.last_seen  >= update2.timestamp - 0.1  # last_seen updated


# ===========================================================================
# Multiple simultaneous DTCs
# ===========================================================================

class TestMultipleDTCs:

    def test_two_dtcs_are_both_active(self, dtc_manager, multi_dtc_update):
        """Two DTCs in one DM1 broadcast both become active entries."""
        dtc_manager.on_dtc_update(multi_dtc_update)
        active = dtc_manager.get_active_dtcs()
        assert len(active) == 2

    def test_dtc_codes_are_distinct(self, dtc_manager, multi_dtc_update):
        """Two different SPNs produce two distinct DTC codes."""
        dtc_manager.on_dtc_update(multi_dtc_update)
        codes = {d.dtc_code for d in dtc_manager.get_active_dtcs()}
        assert "SPN0110-FMI00" in codes
        assert "SPN0100-FMI01" in codes

    def test_separate_updates_accumulate(self, dtc_manager,
                                          coolant_dtc_update, battery_dtc_update):
        """DTCs from separate DM1 broadcasts accumulate in the active list."""
        dtc_manager.on_dtc_update(coolant_dtc_update)
        dtc_manager.on_dtc_update(battery_dtc_update)
        assert len(dtc_manager.get_active_dtcs()) == 2


# ===========================================================================
# Clearing and history
# ===========================================================================

class TestClearingAndHistory:

    def test_clear_all_active_empties_active_list(self, dtc_manager, multi_dtc_update):
        """clear_all_active() removes all entries from the active list."""
        dtc_manager.on_dtc_update(multi_dtc_update)
        dtc_manager.clear_all_active()
        assert dtc_manager.get_active_dtcs() == []

    def test_history_preserved_after_clear(self, dtc_manager, coolant_dtc_update):
        """DTCs remain in history after clear_all_active()."""
        dtc_manager.on_dtc_update(coolant_dtc_update)
        dtc_manager.clear_all_active()
        history = dtc_manager.get_history()
        assert len(history) == 1
        assert history[0].dtc_code == "SPN0110-FMI00"

    def test_cleared_dtc_is_marked_inactive(self, dtc_manager, coolant_dtc_update):
        """After clear, the DTC entry in history has active=False."""
        dtc_manager.on_dtc_update(coolant_dtc_update)
        dtc_manager.clear_all_active()
        history = dtc_manager.get_history()
        assert history[0].active is False

    def test_get_dtc_finds_active_entry(self, dtc_manager, coolant_dtc_update):
        """get_dtc() returns an active DTC by code."""
        dtc_manager.on_dtc_update(coolant_dtc_update)
        dtc = dtc_manager.get_dtc("SPN0110-FMI00")
        assert dtc is not None
        assert dtc.dtc_code == "SPN0110-FMI00"

    def test_get_dtc_finds_historical_entry(self, dtc_manager, coolant_dtc_update):
        """get_dtc() finds a DTC that was cleared into history."""
        dtc_manager.on_dtc_update(coolant_dtc_update)
        dtc_manager.clear_all_active()
        dtc = dtc_manager.get_dtc("SPN0110-FMI00")
        assert dtc is not None

    def test_get_dtc_returns_none_for_unknown_code(self, dtc_manager):
        """get_dtc() returns None for a DTC code that was never seen."""
        assert dtc_manager.get_dtc("SPN9999-FMI99") is None


# ===========================================================================
# Diagnosis logging and resolution
# ===========================================================================

class TestDiagnosisWorkflow:

    def test_log_diagnosis_step(self, dtc_manager, coolant_dtc_update):
        """log_diagnosis_step() appends a timestamped entry to the DTC's log."""
        dtc_manager.on_dtc_update(coolant_dtc_update)
        dtc_manager.log_diagnosis_step("SPN0110-FMI00", "Checked coolant level — OK")
        dtc = dtc_manager.get_dtc("SPN0110-FMI00")
        assert len(dtc.diagnosis_log) == 1
        assert "Checked coolant level" in dtc.diagnosis_log[0]

    def test_multiple_steps_logged(self, dtc_manager, coolant_dtc_update):
        """Multiple diagnosis steps accumulate in order."""
        dtc_manager.on_dtc_update(coolant_dtc_update)
        dtc_manager.log_diagnosis_step("SPN0110-FMI00", "Step 1")
        dtc_manager.log_diagnosis_step("SPN0110-FMI00", "Step 2")
        dtc_manager.log_diagnosis_step("SPN0110-FMI00", "Step 3")
        dtc = dtc_manager.get_dtc("SPN0110-FMI00")
        assert len(dtc.diagnosis_log) == 3

    def test_set_resolution_resolved(self, dtc_manager, coolant_dtc_update):
        """set_resolution('resolved') marks the DTC inactive and sets outcome."""
        dtc_manager.on_dtc_update(coolant_dtc_update)
        dtc_manager.set_resolution("SPN0110-FMI00", "resolved")
        dtc = dtc_manager.get_dtc("SPN0110-FMI00")
        assert dtc.resolution == "resolved"
        assert dtc.active is False

    def test_set_resolution_escalate(self, dtc_manager, coolant_dtc_update):
        """set_resolution('escalate') records the outcome without deactivating."""
        dtc_manager.on_dtc_update(coolant_dtc_update)
        dtc_manager.set_resolution("SPN0110-FMI00", "escalate")
        dtc = dtc_manager.get_dtc("SPN0110-FMI00")
        assert dtc.resolution == "escalate"

    def test_log_step_on_unknown_code_is_safe(self, dtc_manager):
        """log_diagnosis_step() on a nonexistent DTC does not raise."""
        dtc_manager.log_diagnosis_step("SPN9999-FMI99", "ghost step")   # Must not raise


# ===========================================================================
# Change listener callback
# ===========================================================================

class TestChangeListener:

    def test_listener_called_on_new_dtc(self, dtc_manager, coolant_dtc_update):
        """on_change() callback fires when a new DTC is added."""
        received = []
        dtc_manager.on_change(lambda dtcs: received.append(dtcs))
        dtc_manager.on_dtc_update(coolant_dtc_update)
        assert len(received) == 1
        assert len(received[0]) == 1

    def test_listener_called_on_clear(self, dtc_manager, coolant_dtc_update):
        """on_change() callback fires when DTCs are cleared."""
        received = []
        dtc_manager.on_change(lambda dtcs: received.append(dtcs))
        dtc_manager.on_dtc_update(coolant_dtc_update)
        dtc_manager.clear_all_active()
        # First call: new DTC. Second call: after clear (empty list).
        assert len(received) == 2
        assert received[-1] == []

    def test_multiple_listeners_all_called(self, dtc_manager, coolant_dtc_update):
        """Multiple registered listeners all receive the update."""
        results = [[], []]
        dtc_manager.on_change(lambda d: results[0].append(len(d)))
        dtc_manager.on_change(lambda d: results[1].append(len(d)))
        dtc_manager.on_dtc_update(coolant_dtc_update)
        assert results[0] == [1]
        assert results[1] == [1]
