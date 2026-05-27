"""
test_ecu_simulator.py
---------------------
Unit tests for the ECUSimulator.

Tests verify:
  - Simulator starts and stops cleanly
  - Messages are broadcast onto the CAN bus
  - Live data snapshot reflects current state
  - Fault injection changes physical values
  - Fault clearing removes active faults
  - Multiple simultaneous faults are tracked independently
"""

import time
import pytest

from heavydiag.simulation.ecu import ECUSimulator, FaultType, ActiveFault
from heavydiag.comms.can_interface import VirtualCANBus
from heavydiag.simulation.j1939_encoder import J1939Encoder


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def live_ecu():
    """An ECUSimulator running against a VirtualCANBus. Stopped after test."""
    bus = VirtualCANBus()
    ecu = ECUSimulator(on_message=bus.send)
    ecu.start()
    time.sleep(0.15)   # Let a few ticks run
    yield ecu, bus
    ecu.stop()


# ===========================================================================
# Start / Stop
# ===========================================================================

class TestECULifecycle:

    def test_start_and_stop_do_not_raise(self):
        """ECU starts and stops without throwing any exceptions."""
        bus = VirtualCANBus()
        ecu = ECUSimulator(on_message=bus.send)
        ecu.start()
        time.sleep(0.05)
        ecu.stop()   # Should not raise

    def test_stop_is_idempotent(self):
        """Calling stop() twice does not raise."""
        bus = VirtualCANBus()
        ecu = ECUSimulator(on_message=bus.send)
        ecu.start()
        ecu.stop()
        ecu.stop()   # Second call — must not raise

    def test_messages_are_sent_to_bus(self, live_ecu):
        """After starting, the ECU must put at least one frame on the bus."""
        ecu, bus = live_ecu
        # EEC1 broadcasts at 50 Hz — after 150ms we must have received several
        frame = bus.receive(timeout=0.2)
        assert frame is not None, "No frames received from ECU after 200ms"


# ===========================================================================
# Live data snapshot
# ===========================================================================

class TestLiveData:

    def test_get_live_data_returns_all_keys(self, live_ecu):
        """get_live_data() snapshot contains all expected signal keys."""
        ecu, _ = live_ecu
        data = ecu.get_live_data()
        expected_keys = {
            "engine_rpm", "coolant_temp_c", "oil_temp_c",
            "oil_pressure_kpa", "fuel_pressure_kpa",
            "battery_voltage", "engine_torque_pct",
        }
        assert expected_keys.issubset(data.keys())

    def test_live_data_values_are_numeric(self, live_ecu):
        """All values in get_live_data() are numbers."""
        ecu, _ = live_ecu
        data = ecu.get_live_data()
        for key, value in data.items():
            assert isinstance(value, (int, float)), f"{key} is not numeric"

    def test_initial_rpm_near_idle(self, live_ecu):
        """ECU starts near idle RPM (800) before any setpoint change."""
        ecu, _ = live_ecu
        data = ecu.get_live_data()
        assert 500 <= data["engine_rpm"] <= 1200, (
            f"Initial RPM {data['engine_rpm']} is far from idle"
        )

    def test_set_engine_rpm_clamps_to_max(self, live_ecu):
        """set_engine_rpm() clamps values above 2200 to 2200."""
        ecu, _ = live_ecu
        ecu.set_engine_rpm(9999)
        time.sleep(0.05)
        # Target is clamped — actual may still be slewing, check target via live data
        # after enough time the rpm should not exceed 2200 + noise
        data = ecu.get_live_data()
        assert data["engine_rpm"] <= 2300   # Allow brief physics overshoot

    def test_set_engine_rpm_clamps_to_zero(self, live_ecu):
        """set_engine_rpm() clamps negative values to 0."""
        ecu, _ = live_ecu
        ecu.set_engine_rpm(-500)
        time.sleep(0.15)
        data = ecu.get_live_data()
        assert data["engine_rpm"] >= 0


# ===========================================================================
# Fault injection
# ===========================================================================

class TestFaultInjection:

    def test_inject_fault_appears_in_active_faults(self, live_ecu):
        """Injecting a fault adds it to get_active_faults()."""
        ecu, _ = live_ecu
        ecu.inject_fault(FaultType.LOW_OIL_PRESSURE)
        faults = ecu.get_active_faults()
        fault_types = [f.fault_type for f in faults]
        assert FaultType.LOW_OIL_PRESSURE in fault_types

    def test_injected_fault_has_correct_spn(self, live_ecu):
        """Low oil pressure fault carries SPN 100 (Engine Oil Pressure)."""
        ecu, _ = live_ecu
        ecu.inject_fault(FaultType.LOW_OIL_PRESSURE)
        faults = {f.fault_type: f for f in ecu.get_active_faults()}
        assert faults[FaultType.LOW_OIL_PRESSURE].spn == 100

    def test_injected_fault_has_correct_fmi(self, live_ecu):
        """Low oil pressure fault carries FMI 1 (below normal)."""
        ecu, _ = live_ecu
        ecu.inject_fault(FaultType.LOW_OIL_PRESSURE)
        faults = {f.fault_type: f for f in ecu.get_active_faults()}
        assert faults[FaultType.LOW_OIL_PRESSURE].fmi == 1

    def test_inject_same_fault_increments_occurrence_count(self, live_ecu):
        """Injecting the same fault twice increments occurrence_count."""
        ecu, _ = live_ecu
        ecu.inject_fault(FaultType.HIGH_COOLANT_TEMP)
        ecu.inject_fault(FaultType.HIGH_COOLANT_TEMP)
        faults = {f.fault_type: f for f in ecu.get_active_faults()}
        assert faults[FaultType.HIGH_COOLANT_TEMP].occurrence_count == 2

    def test_inject_multiple_different_faults(self, live_ecu):
        """Multiple different faults can be active simultaneously."""
        ecu, _ = live_ecu
        ecu.inject_fault(FaultType.HIGH_COOLANT_TEMP)
        ecu.inject_fault(FaultType.LOW_OIL_PRESSURE)
        ecu.inject_fault(FaultType.LOW_BATTERY_VOLTAGE)
        faults = ecu.get_active_faults()
        assert len(faults) == 3

    def test_clear_specific_fault(self, live_ecu):
        """clear_fault() removes only the specified fault."""
        ecu, _ = live_ecu
        ecu.inject_fault(FaultType.HIGH_COOLANT_TEMP)
        ecu.inject_fault(FaultType.LOW_OIL_PRESSURE)
        ecu.clear_fault(FaultType.HIGH_COOLANT_TEMP)
        fault_types = [f.fault_type for f in ecu.get_active_faults()]
        assert FaultType.HIGH_COOLANT_TEMP not in fault_types
        assert FaultType.LOW_OIL_PRESSURE  in  fault_types

    def test_clear_all_faults(self, live_ecu):
        """clear_all_faults() removes every active fault."""
        ecu, _ = live_ecu
        ecu.inject_fault(FaultType.HIGH_COOLANT_TEMP)
        ecu.inject_fault(FaultType.LOW_OIL_PRESSURE)
        ecu.inject_fault(FaultType.LOW_BATTERY_VOLTAGE)
        ecu.clear_all_faults()
        assert ecu.get_active_faults() == []

    def test_inject_none_fault_is_safe(self, live_ecu):
        """inject_fault(FaultType.NONE) does nothing and does not raise."""
        ecu, _ = live_ecu
        ecu.inject_fault(FaultType.NONE)   # Should not raise
        assert ecu.get_active_faults() == []

    def test_clear_nonexistent_fault_is_safe(self, live_ecu):
        """clear_fault() on a non-active fault type does not raise."""
        ecu, _ = live_ecu
        ecu.clear_fault(FaultType.HIGH_COOLANT_TEMP)   # Nothing active — must not raise


# ===========================================================================
# Fault physics effects
# ===========================================================================

class TestFaultPhysics:

    def test_low_oil_pressure_fault_lowers_pressure(self, live_ecu):
        """LOW_OIL_PRESSURE fault causes oil pressure to decrease over time."""
        ecu, _ = live_ecu
        baseline = ecu.get_live_data()["oil_pressure_kpa"]
        ecu.inject_fault(FaultType.LOW_OIL_PRESSURE)
        time.sleep(0.5)   # Let physics run
        faulted = ecu.get_live_data()["oil_pressure_kpa"]
        assert faulted < baseline, (
            f"Oil pressure did not decrease: baseline={baseline}, faulted={faulted}"
        )

    def test_low_battery_fault_lowers_voltage(self, live_ecu):
        """LOW_BATTERY_VOLTAGE fault causes voltage to decrease over time."""
        ecu, _ = live_ecu
        ecu.inject_fault(FaultType.LOW_BATTERY_VOLTAGE)
        time.sleep(0.5)
        data = ecu.get_live_data()
        # Voltage should be heading down from normal ~14.2V
        assert data["battery_voltage"] < 14.2

    def test_dm1_broadcast_when_fault_active(self, live_ecu):
        """When a fault is active, the ECU broadcasts DM1 frames."""
        ecu, bus = live_ecu
        ecu.inject_fault(FaultType.LOW_OIL_PRESSURE)

        # Drain stale frames, then wait for a DM1
        deadline = time.time() + 2.0
        dm1_found = False
        while time.time() < deadline:
            frame = bus.receive(timeout=0.1)
            if frame and frame.pgn == J1939Encoder.PGN_DM1:
                dm1_found = True
                break

        assert dm1_found, "No DM1 broadcast received after injecting fault"

    def test_no_dm1_without_fault(self):
        """Without any injected faults, the ECU must NOT broadcast DM1."""
        bus = VirtualCANBus()
        ecu = ECUSimulator(on_message=bus.send)
        ecu.start()
        time.sleep(1.2)   # DM1 interval is 1s — wait long enough to catch one
        ecu.stop()

        dm1_found = False
        while True:
            frame = bus.receive(timeout=0.05)
            if frame is None:
                break
            if frame.pgn == J1939Encoder.PGN_DM1:
                dm1_found = True
                break

        assert not dm1_found, "DM1 was broadcast even with no active faults"
