# CAN/J1939 message parser and decoder
"""
can_interface.py
----------------
Virtual CAN bus — the message backbone of HeavyDiag.

In a real off-board diagnostic tool (like PACCAR's ServiceLink or JPRO),
this layer would wrap a physical CAN adapter (e.g., RP1210 API on Windows,
or a USB-CAN dongle). Here we simulate it with Python queues so you can
run the whole stack without hardware.

Architecture:
    ECUSimulator  →  VirtualCANBus  →  CANInterface  →  UI / DTC Manager

The CANInterface:
  - Reads frames off the bus queue
  - Decodes them using J1939Encoder
  - Dispatches decoded data to registered listeners
  - Maintains a rolling message log
"""

import queue
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Callable, Optional

from heavydiag.simulation.j1939_encoder import J1939Encoder, J1939Frame, DTCFrame


# ---------------------------------------------------------------------------
# Message types the interface dispatches to listeners
# ---------------------------------------------------------------------------

@dataclass
class LiveDataUpdate:
    """Decoded signal values from a PGN frame (RPM, temp, pressure…)."""
    pgn: int
    source_address: int
    signals: dict          # e.g. {"engine_rpm": 1450.0, ...}
    timestamp: float = field(default_factory=time.time)


@dataclass
class DTCUpdate:
    """One or more active DTCs received from a DM1 broadcast."""
    dtcs: list             # list of DTCFrame objects
    source_address: int
    timestamp: float = field(default_factory=time.time)


@dataclass
class RawFrameLog:
    """Raw frame entry for the message log display."""
    timestamp: float
    pgn: int
    source_address: int
    data_hex: str
    decoded_label: str     # Human-readable PGN name


# PGN → human label mapping (for display)
PGN_LABELS = {
    61444:  "EEC1  — Engine Speed/Torque",
    65262:  "ET1   — Engine Temperatures",
    65263:  "EFL/P1 — Oil/Fuel Pressure",
    65271:  "VEP1  — Battery Voltage",
    65226:  "DM1   — Active DTCs",
}


# ---------------------------------------------------------------------------
# Virtual CAN Bus
# ---------------------------------------------------------------------------

class VirtualCANBus:
    """
    Thread-safe queue that acts as the CAN bus.
    The ECU puts frames onto the bus; the CANInterface reads from it.
    """

    def __init__(self, maxsize: int = 500):
        self._queue: queue.Queue[J1939Frame] = queue.Queue(maxsize=maxsize)

    def send(self, frame: J1939Frame):
        """Called by the ECU to put a frame on the bus (non-blocking)."""
        try:
            self._queue.put_nowait(frame)
        except queue.Full:
            pass  # Drop oldest — real CAN hardware does this under overload

    def receive(self, timeout: float = 0.05) -> Optional[J1939Frame]:
        """Called by the CANInterface to read the next frame."""
        try:
            return self._queue.get(timeout=timeout)
        except queue.Empty:
            return None


# ---------------------------------------------------------------------------
# CAN Interface — the diagnostic tool's connection to the bus
# ---------------------------------------------------------------------------

class CANInterface:
    """
    Reads J1939 frames off the VirtualCANBus, decodes them, and
    dispatches updates to registered callback listeners.

    Listener registration:
        interface.on_live_data(lambda update: ...)
        interface.on_dtc(lambda update: ...)
    """

    LOG_CAPACITY = 200  # Rolling message log size

    def __init__(self, bus: VirtualCANBus):
        self._bus      = bus
        self._encoder  = J1939Encoder()
        self._running  = False
        self._thread: Optional[threading.Thread] = None

        # Listener lists
        self._live_data_listeners: list[Callable[[LiveDataUpdate], None]] = []
        self._dtc_listeners:       list[Callable[[DTCUpdate], None]]      = []
        self._raw_log_listeners:   list[Callable[[RawFrameLog], None]]    = []

        # Rolling message log (for the raw traffic panel)
        self._message_log: deque[RawFrameLog] = deque(maxlen=self.LOG_CAPACITY)

        # Latest decoded values cache (so UI can poll without waiting for next frame)
        self._latest_signals: dict[str, float] = {}
        self._signals_lock = threading.Lock()

    # ------------------------------------------------------------------
    # Listener registration
    # ------------------------------------------------------------------

    def on_live_data(self, callback: Callable[[LiveDataUpdate], None]):
        """Register a callback for decoded signal updates (RPM, temp, etc.)."""
        self._live_data_listeners.append(callback)

    def on_dtc(self, callback: Callable[[DTCUpdate], None]):
        """Register a callback for DTC (fault) broadcasts."""
        self._dtc_listeners.append(callback)

    def on_raw_frame(self, callback: Callable[[RawFrameLog], None]):
        """Register a callback for raw frame log entries."""
        self._raw_log_listeners.append(callback)

    # ------------------------------------------------------------------
    # Start / Stop
    # ------------------------------------------------------------------

    def start(self):
        """Start the receive loop in a background thread."""
        self._running = True
        self._thread  = threading.Thread(target=self._receive_loop,
                                          name="CANInterface", daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)

    # ------------------------------------------------------------------
    # Data access
    # ------------------------------------------------------------------

    def get_latest_signals(self) -> dict:
        """Returns the most recent decoded value for every known signal."""
        with self._signals_lock:
            return dict(self._latest_signals)

    def get_message_log(self) -> list[RawFrameLog]:
        return list(self._message_log)

    # ------------------------------------------------------------------
    # Receive loop
    # ------------------------------------------------------------------

    def _receive_loop(self):
        """Continuously reads frames from the bus and dispatches them."""
        while self._running:
            frame = self._bus.receive(timeout=0.05)
            if frame is None:
                continue
            self._process_frame(frame)

    def _process_frame(self, frame: J1939Frame):
        """Decode a frame and notify all relevant listeners."""
        now   = time.time()
        label = PGN_LABELS.get(frame.pgn, f"PGN 0x{frame.pgn:04X}")

        # --- Raw log ---
        log_entry = RawFrameLog(
            timestamp=now,
            pgn=frame.pgn,
            source_address=frame.source_address,
            data_hex=frame.data.hex().upper(),
            decoded_label=label,
        )
        self._message_log.append(log_entry)
        for cb in self._raw_log_listeners:
            cb(log_entry)

        # --- DM1 (fault broadcast) ---
        if frame.pgn == J1939Encoder.PGN_DM1:
            dtcs = self._decode_dm1_data(frame)
            if dtcs:
                update = DTCUpdate(dtcs=dtcs,
                                    source_address=frame.source_address,
                                    timestamp=now)
                for cb in self._dtc_listeners:
                    cb(update)
            return

        # --- Signal decode ---
        signals = self._encoder.decode(frame)
        if signals:
            with self._signals_lock:
                self._latest_signals.update(signals)
            update = LiveDataUpdate(pgn=frame.pgn,
                                    source_address=frame.source_address,
                                    signals=signals,
                                    timestamp=now)
            for cb in self._live_data_listeners:
                cb(update)

    def _decode_dm1_data(self, frame: J1939Frame) -> list[DTCFrame]:
        """
        Parse DM1 payload — each DTC is 4 bytes starting at byte 2.
        Returns list of decoded DTCFrame objects.
        """
        data = frame.data
        dtcs = []
        offset = 2  # First 2 bytes are lamp status
        while offset + 3 < len(data):
            b0 = data[offset]
            b1 = data[offset + 1]
            b2 = data[offset + 2]
            b3 = data[offset + 3]
            if b0 == 0xFF and b1 == 0xFF:
                break  # Padding — no more DTCs
            spn = b0 | (b1 << 8) | (((b2 >> 5) & 0x07) << 16)
            fmi = b2 & 0x1F
            oc  = b3 & 0x7F
            active = bool(b3 & 0x80)
            dtcs.append(DTCFrame(spn=spn, fmi=fmi, oc=oc, active=active))
            offset += 4
        return dtcs