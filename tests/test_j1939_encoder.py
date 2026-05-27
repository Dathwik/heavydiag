"""
test_j1939_encoder.py
---------------------
Unit tests for the SAE J1939 frame encoder/decoder.

Tests verify:
  - 29-bit CAN ID packing and unpacking
  - Encode → decode round-trips for all PGNs (EEC1, ET1, EFL/P1, VEP1)
  - Signal resolution and offset accuracy per J1939 spec
  - DM1 encoding with multiple DTCs
  - DTCFrame FMI description lookup
  - Edge cases: zero values, maximum values, boundary conditions
"""

import pytest
from heavydiag.simulation.j1939_encoder import J1939Encoder, J1939Frame, DTCFrame


# ===========================================================================
# CAN ID packing / unpacking
# ===========================================================================

class TestCANIdPacking:
    """Verify 29-bit CAN ID encode/decode round-trips correctly."""

    def test_build_and_parse_round_trip(self, encoder):
        """Priority + PGN + source address survive a pack/unpack cycle."""
        priority = 3
        pgn      = J1939Encoder.PGN_EEC1   # 61444
        src      = J1939Encoder.SA_ENGINE   # 0x00

        can_id = encoder.build_can_id(priority, pgn, src)
        parsed_priority, parsed_pgn, parsed_src = encoder.parse_can_id(can_id)

        assert parsed_priority == priority
        assert parsed_pgn      == pgn
        assert parsed_src      == src

    def test_different_source_addresses(self, encoder):
        """Source address is correctly isolated in the lower 8 bits."""
        for sa in [0x00, 0x03, 0x0B, 0x23, 0xFF]:
            can_id = encoder.build_can_id(6, J1939Encoder.PGN_ET1, sa)
            _, _, parsed_sa = encoder.parse_can_id(can_id)
            assert parsed_sa == sa, f"SA mismatch for 0x{sa:02X}"

    def test_priority_range(self, encoder):
        """Priority field is 3 bits — values 0–7 must round-trip cleanly."""
        for p in range(8):
            can_id = encoder.build_can_id(p, J1939Encoder.PGN_VEP1, 0x23)
            parsed_p, _, _ = encoder.parse_can_id(can_id)
            assert parsed_p == p, f"Priority {p} did not round-trip"

    def test_all_pgns_round_trip(self, encoder):
        """All five PGNs used in HeavyDiag pack/unpack without losing bits."""
        pgns = [
            J1939Encoder.PGN_EEC1,
            J1939Encoder.PGN_ET1,
            J1939Encoder.PGN_EFLP1,
            J1939Encoder.PGN_VEP1,
            J1939Encoder.PGN_DM1,
        ]
        for pgn in pgns:
            can_id = encoder.build_can_id(6, pgn, 0x00)
            _, parsed_pgn, _ = encoder.parse_can_id(can_id)
            assert parsed_pgn == pgn, f"PGN 0x{pgn:04X} did not round-trip"


# ===========================================================================
# EEC1 — Engine Speed and Torque (PGN 61444)
# ===========================================================================

class TestEEC1:
    """Tests for engine speed and torque encoding/decoding."""

    def test_idle_rpm_round_trip(self, encoder):
        """Idle RPM (800) encodes and decodes within J1939 resolution (0.125 rpm/bit)."""
        frame = encoder.encode_eec1(engine_rpm=800.0, engine_torque_pct=0.0)
        decoded = encoder.decode_eec1(frame)
        assert abs(decoded["engine_rpm"] - 800.0) < 0.2

    def test_rated_rpm_round_trip(self, encoder):
        """Rated RPM (1800) encodes and decodes accurately."""
        frame = encoder.encode_eec1(engine_rpm=1800.0, engine_torque_pct=100.0)
        decoded = encoder.decode_eec1(frame)
        assert abs(decoded["engine_rpm"] - 1800.0) < 0.2

    def test_torque_positive(self, encoder):
        """Positive torque percentage round-trips correctly."""
        frame = encoder.encode_eec1(engine_rpm=1450.0, engine_torque_pct=75.0)
        decoded = encoder.decode_eec1(frame)
        assert abs(decoded["engine_torque_pct"] - 75.0) < 1.5

    def test_torque_zero(self, encoder):
        """Zero torque (engine braking / idle) encodes correctly."""
        frame = encoder.encode_eec1(engine_rpm=800.0, engine_torque_pct=0.0)
        decoded = encoder.decode_eec1(frame)
        assert abs(decoded["engine_torque_pct"] - 0.0) < 1.5

    def test_zero_rpm(self, encoder):
        """Engine off (0 RPM) is encodable without error."""
        frame = encoder.encode_eec1(engine_rpm=0.0, engine_torque_pct=0.0)
        decoded = encoder.decode_eec1(frame)
        assert decoded["engine_rpm"] == 0.0

    def test_frame_has_correct_pgn(self, encoder):
        """Encoded EEC1 frame carries PGN 61444."""
        frame = encoder.encode_eec1(1200.0, 50.0)
        assert frame.pgn == J1939Encoder.PGN_EEC1

    def test_frame_data_is_8_bytes(self, encoder):
        """J1939 CAN frames are always 8 bytes."""
        frame = encoder.encode_eec1(1200.0, 50.0)
        assert len(frame.data) == 8

    def test_source_address_is_engine(self, encoder):
        """EEC1 is broadcast by the engine ECU (SA 0x00)."""
        frame = encoder.encode_eec1(1200.0, 50.0)
        assert frame.source_address == J1939Encoder.SA_ENGINE

    def test_auto_dispatch_decode(self, encoder, eec1_frame):
        """encoder.decode() auto-dispatches to decode_eec1 for PGN 61444."""
        result = encoder.decode(eec1_frame)
        assert result is not None
        assert "engine_rpm" in result


# ===========================================================================
# ET1 — Engine Temperature (PGN 65262)
# ===========================================================================

class TestET1:
    """Tests for engine temperature encoding/decoding."""

    def test_normal_coolant_temp(self, encoder):
        """Normal operating coolant temp (88°C) round-trips accurately."""
        frame = encoder.encode_et1(coolant_temp_c=88.0, oil_temp_c=95.0)
        decoded = encoder.decode_et1(frame)
        assert abs(decoded["coolant_temp_c"] - 88.0) < 1.5

    def test_cold_start_temp(self, encoder):
        """Cold start temperature (25°C) is encodable."""
        frame = encoder.encode_et1(coolant_temp_c=25.0, oil_temp_c=25.0)
        decoded = encoder.decode_et1(frame)
        assert abs(decoded["coolant_temp_c"] - 25.0) < 1.5

    def test_overtemp_condition(self, encoder):
        """Overtemp condition (108°C) encodes without overflow."""
        frame = encoder.encode_et1(coolant_temp_c=108.0, oil_temp_c=130.0)
        decoded = encoder.decode_et1(frame)
        assert abs(decoded["coolant_temp_c"] - 108.0) < 1.5

    def test_oil_temp_round_trip(self, encoder):
        """Oil temperature encodes and decodes within 0.5°C."""
        frame = encoder.encode_et1(coolant_temp_c=88.0, oil_temp_c=95.0)
        decoded = encoder.decode_et1(frame)
        assert abs(decoded["oil_temp_c"] - 95.0) < 0.5

    def test_frame_pgn(self, encoder):
        """ET1 frame carries PGN 65262."""
        frame = encoder.encode_et1(88.0, 95.0)
        assert frame.pgn == J1939Encoder.PGN_ET1

    def test_auto_dispatch_decode(self, encoder, et1_frame):
        """encoder.decode() handles ET1 frames."""
        result = encoder.decode(et1_frame)
        assert result is not None
        assert "coolant_temp_c" in result
        assert "oil_temp_c" in result


# ===========================================================================
# EFL/P1 — Engine Fluid Level / Pressure (PGN 65263)
# ===========================================================================

class TestEFLP1:
    """Tests for engine oil and fuel pressure encoding/decoding."""

    def test_normal_oil_pressure(self, encoder):
        """Normal oil pressure (320 kPa) round-trips within 4 kPa resolution."""
        frame = encoder.encode_eflp1(oil_pressure_kpa=320.0, fuel_pressure_kpa=620.0)
        decoded = encoder.decode_eflp1(frame)
        assert abs(decoded["oil_pressure_kpa"] - 320.0) < 4.5

    def test_low_oil_pressure_fault_value(self, encoder):
        """Low oil pressure fault value (80 kPa) encodes correctly."""
        frame = encoder.encode_eflp1(oil_pressure_kpa=80.0, fuel_pressure_kpa=620.0)
        decoded = encoder.decode_eflp1(frame)
        assert abs(decoded["oil_pressure_kpa"] - 80.0) < 4.5

    def test_fuel_pressure_round_trip(self, encoder):
        """Fuel pressure round-trips within resolution."""
        frame = encoder.encode_eflp1(oil_pressure_kpa=320.0, fuel_pressure_kpa=580.0)
        decoded = encoder.decode_eflp1(frame)
        assert abs(decoded["fuel_pressure_kpa"] - 580.0) < 4.5

    def test_zero_pressure(self, encoder):
        """Zero pressure (engine off) encodes without error."""
        frame = encoder.encode_eflp1(oil_pressure_kpa=0.0, fuel_pressure_kpa=0.0)
        decoded = encoder.decode_eflp1(frame)
        assert decoded["oil_pressure_kpa"]  == 0.0
        assert decoded["fuel_pressure_kpa"] == 0.0

    def test_auto_dispatch_decode(self, encoder, eflp1_frame):
        """encoder.decode() handles EFL/P1 frames."""
        result = encoder.decode(eflp1_frame)
        assert result is not None
        assert "oil_pressure_kpa"  in result
        assert "fuel_pressure_kpa" in result


# ===========================================================================
# VEP1 — Vehicle Electrical Power (PGN 65271)
# ===========================================================================

class TestVEP1:
    """Tests for battery voltage encoding/decoding."""

    def test_normal_charging_voltage(self, encoder):
        """Normal charging voltage (14.2V) round-trips within 0.05V resolution."""
        frame = encoder.encode_vep1(battery_voltage=14.2)
        decoded = encoder.decode_vep1(frame)
        assert abs(decoded["battery_voltage"] - 14.2) < 0.06

    def test_low_battery_fault_value(self, encoder):
        """Low battery fault voltage (11.5V) encodes correctly."""
        frame = encoder.encode_vep1(battery_voltage=11.5)
        decoded = encoder.decode_vep1(frame)
        assert abs(decoded["battery_voltage"] - 11.5) < 0.06

    def test_critical_low_voltage(self, encoder):
        """Critical low voltage (10.5V) encodes without underflow."""
        frame = encoder.encode_vep1(battery_voltage=10.5)
        decoded = encoder.decode_vep1(frame)
        assert abs(decoded["battery_voltage"] - 10.5) < 0.06

    def test_high_voltage_condition(self, encoder):
        """Overcharge voltage (15.8V) encodes correctly."""
        frame = encoder.encode_vep1(battery_voltage=15.8)
        decoded = encoder.decode_vep1(frame)
        assert abs(decoded["battery_voltage"] - 15.8) < 0.06

    def test_source_address_is_instrument(self, encoder):
        """VEP1 is broadcast by the instrument cluster (SA 0x23)."""
        frame = encoder.encode_vep1(14.2)
        assert frame.source_address == J1939Encoder.SA_INSTRUMENT

    def test_auto_dispatch_decode(self, encoder, vep1_frame):
        """encoder.decode() handles VEP1 frames."""
        result = encoder.decode(vep1_frame)
        assert result is not None
        assert "battery_voltage" in result


# ===========================================================================
# DM1 — Active Diagnostic Trouble Codes (PGN 65226)
# ===========================================================================

class TestDM1:
    """Tests for DTC broadcast frame encoding."""

    def test_single_dtc_encodes(self, encoder):
        """A single DTC encodes into an 8-byte DM1 frame."""
        dtc = DTCFrame(spn=110, fmi=0, oc=1, active=True)
        frame = encoder.encode_dm1([dtc])
        assert frame.pgn == J1939Encoder.PGN_DM1
        assert len(frame.data) == 8

    def test_multiple_dtcs_encode(self, encoder):
        """Multiple DTCs encode without error."""
        dtcs = [
            DTCFrame(spn=110, fmi=0, oc=1, active=True),
            DTCFrame(spn=100, fmi=1, oc=3, active=True),
        ]
        frame = encoder.encode_dm1(dtcs)
        assert frame.pgn == J1939Encoder.PGN_DM1
        assert len(frame.data) == 8

    def test_empty_dtc_list(self, encoder):
        """Empty DTC list still produces a valid frame."""
        frame = encoder.encode_dm1([])
        assert frame.pgn == J1939Encoder.PGN_DM1
        assert len(frame.data) == 8

    def test_unknown_pgn_returns_none(self, encoder):
        """encoder.decode() returns None for unrecognised PGNs."""
        unknown_frame = J1939Frame(
            pgn=99999, source_address=0x00, priority=6,
            data=bytes(8), raw_id=0
        )
        assert encoder.decode(unknown_frame) is None


# ===========================================================================
# DTCFrame — FMI descriptions
# ===========================================================================

class TestDTCFrame:
    """Tests for DTCFrame helper methods."""

    def test_dtc_code_format(self):
        """dtc_code() returns the expected SPN+FMI string format."""
        dtc = DTCFrame(spn=110, fmi=0, oc=1, active=True)
        assert dtc.dtc_code() == "SPN0110-FMI00"

    def test_dtc_code_zero_padded(self):
        """SPN and FMI are zero-padded to 4 and 2 digits respectively."""
        dtc = DTCFrame(spn=94, fmi=1, oc=1, active=True)
        assert dtc.dtc_code() == "SPN0094-FMI01"

    def test_fmi_0_description(self):
        """FMI 0 maps to 'above normal operational range'."""
        dtc = DTCFrame(spn=110, fmi=0, oc=1, active=True)
        assert "above normal" in dtc.fmi_description().lower()

    def test_fmi_1_description(self):
        """FMI 1 maps to 'below normal operational range'."""
        dtc = DTCFrame(spn=100, fmi=1, oc=1, active=True)
        assert "below normal" in dtc.fmi_description().lower()

    def test_fmi_3_description(self):
        """FMI 3 maps to 'voltage above normal or shorted to high source'."""
        dtc = DTCFrame(spn=110, fmi=3, oc=1, active=True)
        desc = dtc.fmi_description().lower()
        assert "voltage" in desc or "shorted" in desc

    def test_fmi_4_description(self):
        """FMI 4 maps to 'voltage below normal or shorted to low source'."""
        dtc = DTCFrame(spn=110, fmi=4, oc=1, active=True)
        desc = dtc.fmi_description().lower()
        assert "voltage" in desc or "shorted" in desc

    def test_unknown_fmi_returns_fallback(self):
        """Unknown FMI returns a fallback string rather than raising."""
        dtc = DTCFrame(spn=110, fmi=99, oc=1, active=True)
        desc = dtc.fmi_description()
        assert "99" in desc   # Contains the unknown value

    @pytest.mark.parametrize("fmi", [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13])
    def test_all_standard_fmi_have_descriptions(self, fmi):
        """Every standard FMI (0–13) has a non-empty description."""
        dtc = DTCFrame(spn=110, fmi=fmi, oc=1, active=True)
        assert len(dtc.fmi_description()) > 0
