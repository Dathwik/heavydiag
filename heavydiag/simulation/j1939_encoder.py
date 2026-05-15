# Encodes J1939 CAN frames from signal values
"""
j1939_encoder.py
----------------
Encodes and decodes SAE J1939 messages.

QUICK PRIMER — what is J1939?
  J1939 is the communication protocol used on virtually every heavy-duty
  commercial vehicle (trucks, buses, construction equipment). It runs over
  CAN (Controller Area Network) and defines a standard way for ECUs (Engine
  Control Unit, Transmission, Brakes, etc.) to talk to each other.

  A J1939 CAN frame has a 29-bit identifier broken into:
    [Priority 3 bits][Reserved 1 bit][Data Page 1 bit]
    [PDU Format 8 bits][PDU Specific 8 bits][Source Address 8 bits]

  The PGN (Parameter Group Number) identifies WHAT data is in the frame.
  Example PGNs used in this project:
    61444  (0xF004) - Engine speed, torque  (EEC1)
    65262  (0xFEEE) - Engine temperatures   (ET1)
    65263  (0xFEEF) - Oil/fuel pressure     (EFL/P1)
    65271  (0xFEF7) - Battery voltage       (VEP1)
    65226  (0xFECA) - Active DTCs           (DM1)

  Each parameter inside a PGN is called an SPN (Suspect Parameter Number).
  When a fault occurs, the ECU sends an SPN + FMI (Failure Mode Identifier)
  pair — that combination IS the Diagnostic Trouble Code (DTC).
"""

import struct
from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class J1939Frame:
    """Represents one decoded J1939 CAN frame."""
    pgn: int               # Parameter Group Number
    source_address: int    # Which ECU sent this (0=engine, 1=trans, etc.)
    priority: int          # 0–7, lower = higher priority
    data: bytes            # Up to 8 bytes of payload
    raw_id: int = 0        # The raw 29-bit CAN identifier

    def __repr__(self) -> str:
        hex_data = self.data.hex().upper()
        return (f"J1939Frame(PGN=0x{self.pgn:04X}/{self.pgn}, "
                f"SA=0x{self.source_address:02X}, "
                f"Priority={self.priority}, "
                f"Data={hex_data})")


@dataclass
class DTCFrame:
    """A decoded Diagnostic Trouble Code from a DM1 message."""
    spn: int          # Suspect Parameter Number — identifies the component
    fmi: int          # Failure Mode Identifier — identifies type of failure
    oc: int           # Occurrence count
    active: bool      # True = currently active fault

    # Human-readable FMI descriptions (SAE J1939 standard)
    FMI_DESCRIPTIONS = {
        0:  "Data valid but above normal operational range",
        1:  "Data valid but below normal operational range",
        2:  "Data erratic, intermittent or incorrect",
        3:  "Voltage above normal or shorted to high source",
        4:  "Voltage below normal or shorted to low source",
        5:  "Current below normal or open circuit",
        6:  "Current above normal or grounded circuit",
        7:  "Mechanical system not responding or out of adjustment",
        8:  "Abnormal frequency or pulse width or period",
        9:  "Abnormal update rate",
        10: "Abnormal rate of change",
        11: "Root cause not known",
        12: "Bad intelligent device or component",
        13: "Out of calibration",
        14: "Special instructions",
        15: "Data valid but above normal operating range",
        16: "Data valid but below normal operating range",
        17: "Data erratic, intermittent or incorrect",
        18: "Received network data in error",
        19: "Condition exists",
        31: "Not available or condition exists",
    }

    def fmi_description(self) -> str:
        return self.FMI_DESCRIPTIONS.get(self.fmi, f"Unknown FMI ({self.fmi})")

    def dtc_code(self) -> str:
        """Returns a human-friendly DTC code string like 'SPN1234-FMI04'."""
        return f"SPN{self.spn:04d}-FMI{self.fmi:02d}"

    def __repr__(self) -> str:
        return (f"DTC({self.dtc_code()}, OC={self.oc}, "
                f"Active={self.active}, FMI='{self.fmi_description()}')")


# ---------------------------------------------------------------------------
# Encoder / Decoder
# ---------------------------------------------------------------------------

class J1939Encoder:
    """
    Encodes Python values into J1939 CAN frames and decodes frames back.

    Key J1939 PGNs we care about:
      EEC1  (61444) — Engine Electronic Controller 1
      ET1   (65262) — Engine Temperature 1
      EFLP1 (65263) — Engine Fluid Level/Pressure 1
      VEP1  (65271) — Vehicle Electrical Power 1
      DM1   (65226) — Active Diagnostic Trouble Codes
    """

    # Source address constants (which ECU is talking)
    SA_ENGINE       = 0x00
    SA_TRANSMISSION = 0x03
    SA_BRAKES       = 0x0B
    SA_INSTRUMENT   = 0x23
    SA_BODY         = 0x27

    # PGN constants
    PGN_EEC1  = 61444   # Engine speed, torque
    PGN_ET1   = 65262   # Engine temps
    PGN_EFLP1 = 65263   # Oil/fuel pressure
    PGN_VEP1  = 65271   # Battery voltage
    PGN_DM1   = 65226   # Active DTCs

    def build_can_id(self, priority: int, pgn: int, src: int) -> int:
        """
        Packs priority + PGN + source address into a 29-bit CAN identifier.
        Layout: [P P P R DP PF PS SA] where each field has defined bit width.
        """
        # Extract PDU Format (bits 15-8 of PGN) and PDU Specific (bits 7-0)
        dp  = (pgn >> 16) & 0x01
        pf  = (pgn >> 8)  & 0xFF
        ps  = pgn         & 0xFF
        can_id = ((priority & 0x07) << 26) | (dp << 24) | (pf << 16) | (ps << 8) | (src & 0xFF)
        return can_id

    def parse_can_id(self, can_id: int) -> tuple[int, int, int]:
        """Returns (priority, pgn, source_address) from a 29-bit CAN ID."""
        priority = (can_id >> 26) & 0x07
        dp       = (can_id >> 24) & 0x01
        pf       = (can_id >> 16) & 0xFF
        ps       = (can_id >> 8)  & 0xFF
        src      = can_id         & 0xFF
        # PGN includes DP + PF; if PF >= 240 it's a broadcast (PS is part of PGN)
        if pf >= 0xF0:
            pgn = (dp << 16) | (pf << 8) | ps
        else:
            pgn = (dp << 16) | (pf << 8)
        return priority, pgn, src

    # ------------------------------------------------------------------
    # Encoders — pack signal values into J1939 data bytes
    # ------------------------------------------------------------------

    def encode_eec1(self, engine_rpm: float, engine_torque_pct: float) -> J1939Frame:
        """
        PGN 61444 — EEC1
        Byte 4-5: Engine Speed (0.125 rpm/bit, range 0–8031.875 rpm)
        Byte 3:   Actual Engine Torque (1%/bit offset -125%, range -125–125%)
        """
        rpm_raw    = int(engine_rpm / 0.125) & 0xFFFF
        torque_raw = int(engine_torque_pct + 125) & 0xFF
        data = bytearray(8)
        data[0] = 0xFF  # Engine torque mode (not used)
        data[1] = 0xFF  # Driver demand (not used)
        data[2] = torque_raw
        data[3] = rpm_raw & 0xFF
        data[4] = (rpm_raw >> 8) & 0xFF
        data[5] = 0xFF
        data[6] = 0xFF
        data[7] = 0xFF
        can_id = self.build_can_id(3, self.PGN_EEC1, self.SA_ENGINE)
        return J1939Frame(pgn=self.PGN_EEC1, source_address=self.SA_ENGINE,
                          priority=3, data=bytes(data), raw_id=can_id)

    def encode_et1(self, coolant_temp_c: float, oil_temp_c: float) -> J1939Frame:
        """
        PGN 65262 — ET1
        Byte 1: Engine Coolant Temp (1°C/bit, offset -40°C)
        Byte 3-4: Engine Oil Temp   (0.03125°C/bit, offset -273°C)
        """
        coolant_raw = int(coolant_temp_c + 40) & 0xFF
        oil_raw     = int((oil_temp_c + 273) / 0.03125) & 0xFFFF
        data = bytearray(8)
        data[0] = coolant_raw
        data[1] = 0xFF
        data[2] = oil_raw & 0xFF
        data[3] = (oil_raw >> 8) & 0xFF
        data[4] = 0xFF
        data[5] = 0xFF
        data[6] = 0xFF
        data[7] = 0xFF
        can_id = self.build_can_id(6, self.PGN_ET1, self.SA_ENGINE)
        return J1939Frame(pgn=self.PGN_ET1, source_address=self.SA_ENGINE,
                          priority=6, data=bytes(data), raw_id=can_id)

    def encode_eflp1(self, oil_pressure_kpa: float, fuel_pressure_kpa: float) -> J1939Frame:
        """
        PGN 65263 — EFL/P1
        Byte 4: Engine Oil Pressure  (4 kPa/bit, range 0–1000 kPa)
        Byte 1: Engine Fuel Pressure (4 kPa/bit, range 0–1000 kPa)
        """
        oil_raw  = int(oil_pressure_kpa  / 4) & 0xFF
        fuel_raw = int(fuel_pressure_kpa / 4) & 0xFF
        data = bytearray(8)
        data[0] = fuel_raw
        data[1] = 0xFF
        data[2] = 0xFF
        data[3] = oil_raw
        data[4] = 0xFF
        data[5] = 0xFF
        data[6] = 0xFF
        data[7] = 0xFF
        can_id = self.build_can_id(6, self.PGN_EFLP1, self.SA_ENGINE)
        return J1939Frame(pgn=self.PGN_EFLP1, source_address=self.SA_ENGINE,
                          priority=6, data=bytes(data), raw_id=can_id)

    def encode_vep1(self, battery_voltage: float) -> J1939Frame:
        """
        PGN 65271 — VEP1
        Byte 5-6: Battery Potential (0.05 V/bit, range 0–3212.75 V)
        """
        voltage_raw = int(battery_voltage / 0.05) & 0xFFFF
        data = bytearray(8)
        data[0] = 0xFF
        data[1] = 0xFF
        data[2] = 0xFF
        data[3] = 0xFF
        data[4] = voltage_raw & 0xFF
        data[5] = (voltage_raw >> 8) & 0xFF
        data[6] = 0xFF
        data[7] = 0xFF
        can_id = self.build_can_id(6, self.PGN_VEP1, self.SA_INSTRUMENT)
        return J1939Frame(pgn=self.PGN_VEP1, source_address=self.SA_INSTRUMENT,
                          priority=6, data=bytes(data), raw_id=can_id)

    def encode_dm1(self, dtcs: list[DTCFrame]) -> J1939Frame:
        """
        PGN 65226 — DM1 (Active Diagnostic Trouble Codes)
        Each DTC takes 4 bytes: [SPN low][SPN mid][SPN high | FMI][OC]
        First 2 bytes are lamp status (we simplify to amber warning).
        """
        data = bytearray()
        # Lamp status byte: bit layout for amber warning lamp ON
        lamp_status = 0b00101010  # Amber warning lamp active
        data.append(lamp_status)
        data.append(0xFF)         # Flash indicator (not used)
        for dtc in dtcs[:3]:      # J1939 DM1 can hold multiple DTCs
            spn_low  =  dtc.spn        & 0xFF
            spn_mid  = (dtc.spn >>  8) & 0xFF
            spn_fmi  = ((dtc.spn >> 16) & 0x07) << 5 | (dtc.fmi & 0x1F)
            oc_byte  = (dtc.oc & 0x7F) | (0x80 if dtc.active else 0x00)
            data.extend([spn_low, spn_mid, spn_fmi, oc_byte])
        # Pad to at least 8 bytes
        while len(data) < 8:
            data.append(0xFF)
        can_id = self.build_can_id(6, self.PGN_DM1, self.SA_ENGINE)
        return J1939Frame(pgn=self.PGN_DM1, source_address=self.SA_ENGINE,
                          priority=6, data=bytes(data[:8]), raw_id=can_id)

    # ------------------------------------------------------------------
    # Decoders — unpack J1939 data bytes back into signal values
    # ------------------------------------------------------------------

    def decode_eec1(self, frame: J1939Frame) -> dict:
        d = frame.data
        rpm_raw    = d[3] | (d[4] << 8)
        torque_raw = d[2]
        return {
            "engine_rpm":        round(rpm_raw * 0.125, 1),
            "engine_torque_pct": torque_raw - 125,
        }

    def decode_et1(self, frame: J1939Frame) -> dict:
        d = frame.data
        coolant_raw = d[0]
        oil_raw     = d[2] | (d[3] << 8)
        return {
            "coolant_temp_c": coolant_raw - 40,
            "oil_temp_c":     round(oil_raw * 0.03125 - 273, 1),
        }

    def decode_eflp1(self, frame: J1939Frame) -> dict:
        d = frame.data
        return {
            "fuel_pressure_kpa": d[0] * 4,
            "oil_pressure_kpa":  d[3] * 4,
        }

    def decode_vep1(self, frame: J1939Frame) -> dict:
        d = frame.data
        voltage_raw = d[4] | (d[5] << 8)
        return {
            "battery_voltage": round(voltage_raw * 0.05, 2),
        }

    def decode(self, frame: J1939Frame) -> Optional[dict]:
        """Auto-dispatch decoder based on PGN."""
        decoders = {
            self.PGN_EEC1:  self.decode_eec1,
            self.PGN_ET1:   self.decode_et1,
            self.PGN_EFLP1: self.decode_eflp1,
            self.PGN_VEP1:  self.decode_vep1,
        }
        decoder = decoders.get(frame.pgn)
        if decoder:
            return decoder(frame)
        return None