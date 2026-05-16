# Fake ECU simulator that emits J1939 messages and faults
"""
ecu.py
------
Simulates a heavy-duty vehicle ECU (Engine Control Unit).

Runs in a background thread, producing realistic J1939 messages on a
virtual CAN bus at configurable intervals. Can inject fault conditions
(DTCs) to trigger guided diagnostic workflows in the UI.

Think of this as the "vehicle" side of the off-board diagnostic tool —
in a real PACCAR tool, this data comes from the truck's actual CAN bus
via a diagnostic adapter (like a JPRO or ServiceLink interface).
"""

import math
import random
import threading
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Callable, Optional

from heavydiag.simulation.j1939_encoder import J1939Encoder, J1939Frame, DTCFrame


# ---------------------------------------------------------------------------
# Fault definitions
# ---------------------------------------------------------------------------

class FaultType(Enum):
    """Types of faults the simulator can inject."""
    NONE                  = auto()
    HIGH_COOLANT_TEMP     = auto()
    LOW_OIL_PRESSURE      = auto()
    LOW_BATTERY_VOLTAGE   = auto()
    HIGH_COOLANT_TEMP_SENSOR_SHORT = auto()   # Sensor wiring fault
    FUEL_PRESSURE_LOW     = auto()


@dataclass
class ActiveFault:
    """Tracks a currently injected fault."""
    fault_type: FaultType
    spn: int          # Which SPN (sensor/component) is affected
    fmi: int          # How it failed (open circuit, short, out of range…)
    description: str
    severity: str     # "critical", "warning", "info"
    occurrence_count: int = 1


# Real SAE J1939 SPN numbers for common engine parameters
SPN_ENGINE_COOLANT_TEMP  = 110
SPN_ENGINE_OIL_PRESSURE  = 100
SPN_BATTERY_VOLTAGE      = 168
SPN_FUEL_DELIVERY_PRESS  = 94

# Fault catalog: maps FaultType → (SPN, FMI, description, severity)
FAULT_CATALOG = {
    FaultType.HIGH_COOLANT_TEMP: (
        SPN_ENGINE_COOLANT_TEMP, 0,
        "Engine Coolant Temperature above normal range",
        "critical"
    ),
    FaultType.LOW_OIL_PRESSURE: (
        SPN_ENGINE_OIL_PRESSURE, 1,
        "Engine Oil Pressure below normal operational range",
        "critical"
    ),
    FaultType.LOW_BATTERY_VOLTAGE: (
        SPN_BATTERY_VOLTAGE, 1,
        "Battery Potential (Voltage) below normal operational range",
        "warning"
    ),
    FaultType.HIGH_COOLANT_TEMP_SENSOR_SHORT: (
        SPN_ENGINE_COOLANT_TEMP, 3,
        "Engine Coolant Temp Sensor — voltage above normal (shorted high)",
        "warning"
    ),
    FaultType.FUEL_PRESSURE_LOW: (
        SPN_FUEL_DELIVERY_PRESS, 1,
        "Fuel Delivery Pressure below normal operational range",
        "warning"
    ),
}


# ---------------------------------------------------------------------------
# ECU Simulator
# ---------------------------------------------------------------------------

class ECUSimulator:
    """
    Simulates a truck's engine ECU broadcasting J1939 messages.

    Usage:
        bus_callback = lambda frame: my_queue.put(frame)
        ecu = ECUSimulator(on_message=bus_callback)
        ecu.start()
        ecu.inject_fault(FaultType.LOW_OIL_PRESSURE)
        ecu.stop()
    """

    # Broadcast intervals (seconds)
    INTERVAL_EEC1  = 0.02   # 50 Hz — engine speed is high priority
    INTERVAL_ET1   = 1.0    # 1 Hz  — temperature
    INTERVAL_EFLP1 = 0.5    # 2 Hz  — pressure
    INTERVAL_VEP1  = 1.0    # 1 Hz  — battery voltage
    INTERVAL_DM1   = 1.0    # 1 Hz  — fault broadcast

    def __init__(self, on_message: Callable[[J1939Frame], None]):
        """
        Args:
            on_message: Callback invoked each time the ECU emits a frame.
                        The caller typically puts the frame on a queue.
        """
        self._on_message = on_message
        self._encoder    = J1939Encoder()
        self._running    = False
        self._thread: Optional[threading.Thread] = None
        self._lock       = threading.Lock()

        # --- Simulated vehicle state ---
        self._time_s          = 0.0     # elapsed simulation seconds
        self._engine_rpm      = 800.0   # idle RPM
        self._target_rpm      = 800.0
        self._coolant_temp    = 25.0    # °C  (cold start)
        self._oil_temp        = 25.0    # °C
        self._oil_pressure    = 310.0   # kPa (normal operating)
        self._fuel_pressure   = 620.0   # kPa
        self._battery_voltage = 14.2    # V   (alternator charging)

        # --- Fault state ---
        self._active_faults: dict[FaultType, ActiveFault] = {}
        self._fault_lock = threading.Lock()

        # Timers for each PGN broadcast
        self._last_eec1  = 0.0
        self._last_et1   = 0.0
        self._last_eflp1 = 0.0
        self._last_vep1  = 0.0
        self._last_dm1   = 0.0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self):
        """Start the simulation thread."""
        self._running = True
        self._thread  = threading.Thread(target=self._run_loop,
                                          name="ECUSimulator", daemon=True)
        self._thread.start()

    def stop(self):
        """Stop the simulation thread cleanly."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)

    def set_engine_rpm(self, rpm: float):
        """Drive the simulated engine to a target RPM (0–2200)."""
        with self._lock:
            self._target_rpm = max(0.0, min(2200.0, rpm))

    def inject_fault(self, fault_type: FaultType):
        """Inject a fault condition — the ECU will start broadcasting a DTC."""
        if fault_type == FaultType.NONE:
            return
        spn, fmi, desc, severity = FAULT_CATALOG[fault_type]
        with self._fault_lock:
            if fault_type in self._active_faults:
                self._active_faults[fault_type].occurrence_count += 1
            else:
                self._active_faults[fault_type] = ActiveFault(
                    fault_type=fault_type, spn=spn, fmi=fmi,
                    description=desc, severity=severity
                )

    def clear_fault(self, fault_type: FaultType):
        """Clear a specific injected fault."""
        with self._fault_lock:
            self._active_faults.pop(fault_type, None)

    def clear_all_faults(self):
        """Clear all active faults."""
        with self._fault_lock:
            self._active_faults.clear()

    def get_active_faults(self) -> list[ActiveFault]:
        with self._fault_lock:
            return list(self._active_faults.values())

    def get_live_data(self) -> dict:
        """Snapshot of current simulated sensor values."""
        with self._lock:
            return {
                "engine_rpm":      round(self._engine_rpm, 1),
                "coolant_temp_c":  round(self._coolant_temp, 1),
                "oil_temp_c":      round(self._oil_temp, 1),
                "oil_pressure_kpa": round(self._oil_pressure, 1),
                "fuel_pressure_kpa": round(self._fuel_pressure, 1),
                "battery_voltage": round(self._battery_voltage, 2),
                "engine_torque_pct": self._calc_torque_pct(),
            }

    # ------------------------------------------------------------------
    # Internal simulation loop
    # ------------------------------------------------------------------

    def _run_loop(self):
        """Main simulation loop — runs at ~100 Hz, broadcasts at PGN intervals."""
        tick = 0.01  # 10 ms tick
        while self._running:
            now = self._time_s
            self._update_physics(tick)

            if now - self._last_eec1 >= self.INTERVAL_EEC1:
                self._broadcast_eec1()
                self._last_eec1 = now

            if now - self._last_et1 >= self.INTERVAL_ET1:
                self._broadcast_et1()
                self._last_et1 = now

            if now - self._last_eflp1 >= self.INTERVAL_EFLP1:
                self._broadcast_eflp1()
                self._last_eflp1 = now

            if now - self._last_vep1 >= self.INTERVAL_VEP1:
                self._broadcast_vep1()
                self._last_vep1 = now

            if now - self._last_dm1 >= self.INTERVAL_DM1:
                self._broadcast_dm1()
                self._last_dm1 = now

            self._time_s += tick
            time.sleep(tick)

    def _update_physics(self, dt: float):
        """
        Simple physics model — makes sensor values change realistically
        rather than jumping instantly. Also applies fault effects.
        """
        with self._lock, self._fault_lock:
            # RPM slew toward target
            rpm_error = self._target_rpm - self._engine_rpm
            self._engine_rpm += rpm_error * min(dt * 2.0, 1.0)
            self._engine_rpm += random.gauss(0, 5)  # sensor noise
            self._engine_rpm = max(0, self._engine_rpm)

            # Warm-up curve — coolant heats up as engine runs
            if self._engine_rpm > 200:
                target_coolant = 88.0  # normal operating temp
                self._coolant_temp += (target_coolant - self._coolant_temp) * dt * 0.005
                target_oil = 95.0
                self._oil_temp += (target_oil - self._oil_temp) * dt * 0.003

            # Apply fault effects on physical values
            if FaultType.HIGH_COOLANT_TEMP in self._active_faults:
                self._coolant_temp = min(self._coolant_temp + dt * 2.0, 115.0)

            if FaultType.HIGH_COOLANT_TEMP_SENSOR_SHORT in self._active_faults:
                # Sensor fault — reports impossibly high value
                self._coolant_temp = 250.0  # way out of range

            if FaultType.LOW_OIL_PRESSURE in self._active_faults:
                self._oil_pressure = max(self._oil_pressure - dt * 10.0, 40.0)
            else:
                # Normal oil pressure varies with RPM
                self._oil_pressure = 280 + (self._engine_rpm / 2200) * 120 \
                                     + random.gauss(0, 3)

            if FaultType.FUEL_PRESSURE_LOW in self._active_faults:
                self._fuel_pressure = max(self._fuel_pressure - dt * 5.0, 150.0)
            else:
                self._fuel_pressure = 580 + random.gauss(0, 10)

            if FaultType.LOW_BATTERY_VOLTAGE in self._active_faults:
                self._battery_voltage = max(self._battery_voltage - dt * 0.01, 10.5)
            else:
                self._battery_voltage = 14.2 + random.gauss(0, 0.05)

    def _calc_torque_pct(self) -> float:
        """Approximate engine torque from RPM (very simplified)."""
        peak_rpm = 1400.0
        return round(max(0, 100 - abs(self._engine_rpm - peak_rpm) / 20), 1)

    # ------------------------------------------------------------------
    # Broadcast helpers
    # ------------------------------------------------------------------

    def _broadcast_eec1(self):
        with self._lock:
            frame = self._encoder.encode_eec1(self._engine_rpm,
                                               self._calc_torque_pct())
        self._on_message(frame)

    def _broadcast_et1(self):
        with self._lock:
            frame = self._encoder.encode_et1(self._coolant_temp, self._oil_temp)
        self._on_message(frame)

    def _broadcast_eflp1(self):
        with self._lock:
            frame = self._encoder.encode_eflp1(self._oil_pressure,
                                                 self._fuel_pressure)
        self._on_message(frame)

    def _broadcast_vep1(self):
        with self._lock:
            frame = self._encoder.encode_vep1(self._battery_voltage)
        self._on_message(frame)

    def _broadcast_dm1(self):
        with self._fault_lock:
            faults = list(self._active_faults.values())
        if not faults:
            return
        dtc_frames = [
            DTCFrame(spn=f.spn, fmi=f.fmi,
                     oc=f.occurrence_count, active=True)
            for f in faults
        ]
        frame = self._encoder.encode_dm1(dtc_frames)
        self._on_message(frame)