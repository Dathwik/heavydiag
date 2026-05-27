"""
conftest.py
-----------
Shared pytest fixtures for HeavyDiag test suite.

Fixtures here are automatically available to every test file —
no import needed, pytest discovers them automatically.
"""

import time
import pytest

from heavydiag.simulation.j1939_encoder import J1939Encoder, DTCFrame
from heavydiag.comms.can_interface import VirtualCANBus, CANInterface, DTCUpdate
from heavydiag.diagnostics.dtc_manager import DTCManager
from heavydiag.diagnostics.guided_procedure import ProcedureLibrary


# ---------------------------------------------------------------------------
# Core object fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def encoder():
    """A fresh J1939Encoder instance."""
    return J1939Encoder()


@pytest.fixture
def bus():
    """A fresh VirtualCANBus."""
    return VirtualCANBus()


@pytest.fixture
def interface(bus):
    """A CANInterface wired to the bus fixture, started and stopped around the test."""
    iface = CANInterface(bus)
    iface.start()
    yield iface
    iface.stop()


@pytest.fixture
def dtc_manager():
    """A fresh DTCManager with no active DTCs."""
    return DTCManager()


@pytest.fixture
def procedure_library():
    """The loaded ProcedureLibrary (all 4 procedures)."""
    return ProcedureLibrary()


# ---------------------------------------------------------------------------
# Pre-built frame fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def eec1_frame(encoder):
    """An EEC1 frame encoded at 1450 RPM, 75% torque."""
    return encoder.encode_eec1(engine_rpm=1450.0, engine_torque_pct=75.0)


@pytest.fixture
def et1_frame(encoder):
    """An ET1 frame encoded at 88°C coolant, 95°C oil."""
    return encoder.encode_et1(coolant_temp_c=88.0, oil_temp_c=95.0)


@pytest.fixture
def eflp1_frame(encoder):
    """An EFL/P1 frame at 320 kPa oil, 620 kPa fuel."""
    return encoder.encode_eflp1(oil_pressure_kpa=320.0, fuel_pressure_kpa=620.0)


@pytest.fixture
def vep1_frame(encoder):
    """A VEP1 frame at 14.2V battery."""
    return encoder.encode_vep1(battery_voltage=14.2)


# ---------------------------------------------------------------------------
# DTC fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def coolant_dtc_update():
    """A DTCUpdate simulating a high-coolant-temp DTC (SPN 110, FMI 0)."""
    return DTCUpdate(
        dtcs=[DTCFrame(spn=110, fmi=0, oc=1, active=True)],
        source_address=0x00,
        timestamp=time.time(),
    )


@pytest.fixture
def oil_pressure_dtc_update():
    """A DTCUpdate simulating a low-oil-pressure DTC (SPN 100, FMI 1)."""
    return DTCUpdate(
        dtcs=[DTCFrame(spn=100, fmi=1, oc=2, active=True)],
        source_address=0x00,
        timestamp=time.time(),
    )


@pytest.fixture
def battery_dtc_update():
    """A DTCUpdate simulating a low-battery-voltage DTC (SPN 168, FMI 1)."""
    return DTCUpdate(
        dtcs=[DTCFrame(spn=168, fmi=1, oc=1, active=True)],
        source_address=0x23,
        timestamp=time.time(),
    )


@pytest.fixture
def multi_dtc_update():
    """A DTCUpdate with two simultaneous active faults."""
    return DTCUpdate(
        dtcs=[
            DTCFrame(spn=110, fmi=0, oc=1, active=True),
            DTCFrame(spn=100, fmi=1, oc=1, active=True),
        ],
        source_address=0x00,
        timestamp=time.time(),
    )
