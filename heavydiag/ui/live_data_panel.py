# Live CAN data display panel
"""
live_data_panel.py
------------------
Displays real-time decoded J1939 signal values as gauge cards.

Each SignalCard shows:
  - Current value (large)
  - Unit and signal name
  - Visual status bar (green / yellow / red)
  - Normal range indicators
"""

from PyQt5.QtWidgets import (
    QWidget, QGridLayout, QVBoxLayout, QHBoxLayout,
    QLabel, QFrame, QSizePolicy
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QFont, QColor, QPainter, QPen, QBrush

from heavydiag.ui.styles import (
    COLOR_BG_CARD, COLOR_BORDER, COLOR_TEXT_PRIMARY,
    COLOR_TEXT_SECONDARY, COLOR_SUCCESS, COLOR_WARNING,
    COLOR_DANGER, COLOR_TEXT_MUTED, COLOR_BG_PANEL
)


# ---------------------------------------------------------------------------
# Signal card widget
# ---------------------------------------------------------------------------

class SignalCard(QFrame):
    """
    One gauge card for a single J1939 signal (e.g., Engine RPM).
    Shows value, unit, name, and a colored status bar.
    """

    def __init__(self, name: str, unit: str,
                 normal_low: float, normal_high: float,
                 warn_low: float = None, warn_high: float = None,
                 crit_low: float = None, crit_high: float = None,
                 fmt: str = "{:.0f}", parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        self.setMinimumSize(160, 110)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        self._name       = name
        self._unit       = unit
        self._normal_low  = normal_low
        self._normal_high = normal_high
        self._warn_low   = warn_low   if warn_low   is not None else normal_low * 0.9
        self._warn_high  = warn_high  if warn_high  is not None else normal_high * 1.1
        self._crit_low   = crit_low   if crit_low   is not None else normal_low  * 0.7
        self._crit_high  = crit_high  if crit_high  is not None else normal_high * 1.3
        self._fmt        = fmt
        self._value: float = 0.0
        self._status       = "normal"  # "normal", "warning", "critical", "offline"

        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(4)

        # Signal name
        self._lbl_name = QLabel(self._name.upper())
        self._lbl_name.setStyleSheet(
            f"color: {COLOR_TEXT_SECONDARY}; font-size: 10px; "
            f"font-weight: 700; letter-spacing: 0.8px;"
        )
        layout.addWidget(self._lbl_name)

        # Value + unit row
        value_row = QHBoxLayout()
        value_row.setSpacing(4)

        self._lbl_value = QLabel("—")
        self._lbl_value.setStyleSheet(
            f"color: {COLOR_TEXT_PRIMARY}; font-size: 26px; font-weight: 700;"
        )
        value_row.addWidget(self._lbl_value)

        self._lbl_unit = QLabel(self._unit)
        self._lbl_unit.setStyleSheet(
            f"color: {COLOR_TEXT_SECONDARY}; font-size: 12px; "
            f"padding-top: 10px;"
        )
        self._lbl_unit.setAlignment(Qt.AlignBottom)
        value_row.addWidget(self._lbl_unit)
        value_row.addStretch()

        layout.addLayout(value_row)

        # Status bar
        self._status_bar = StatusBar()
        layout.addWidget(self._status_bar)

        # Status label
        self._lbl_status = QLabel("OFFLINE")
        self._lbl_status.setStyleSheet(
            f"color: {COLOR_TEXT_MUTED}; font-size: 10px; font-weight: 600;"
        )
        layout.addWidget(self._lbl_status)

        self._update_style()

    def update_value(self, value: float):
        """Update the displayed value and recalculate status."""
        self._value = value
        self._status = self._calc_status(value)
        self._lbl_value.setText(self._fmt.format(value))
        self._status_bar.set_status(self._status)
        self._lbl_status.setText(self._status.upper())
        self._update_style()

    def set_offline(self):
        self._status = "offline"
        self._lbl_value.setText("—")
        self._lbl_status.setText("NO SIGNAL")
        self._update_style()

    def _calc_status(self, value: float) -> str:
        if value <= self._crit_low or value >= self._crit_high:
            return "critical"
        if value <= self._warn_low or value >= self._warn_high:
            return "warning"
        return "normal"

    def _update_style(self):
        color_map = {
            "normal":   COLOR_SUCCESS,
            "warning":  COLOR_WARNING,
            "critical": COLOR_DANGER,
            "offline":  COLOR_TEXT_MUTED,
        }
        color = color_map.get(self._status, COLOR_TEXT_MUTED)
        self._lbl_status.setStyleSheet(
            f"color: {color}; font-size: 10px; font-weight: 600;"
        )
        border_color = color if self._status != "normal" else COLOR_BORDER
        self.setStyleSheet(
            f"QFrame#card {{ background-color: {COLOR_BG_CARD}; "
            f"border: 1px solid {border_color}; border-radius: 8px; }}"
        )


class StatusBar(QWidget):
    """A thin colored bar showing green/yellow/red status."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(4)
        self._status = "offline"

    def set_status(self, status: str):
        self._status = status
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        color_map = {
            "normal":   QColor(COLOR_SUCCESS),
            "warning":  QColor(COLOR_WARNING),
            "critical": QColor(COLOR_DANGER),
            "offline":  QColor(COLOR_TEXT_MUTED),
        }
        color = color_map.get(self._status, QColor(COLOR_TEXT_MUTED))
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(color))
        painter.drawRoundedRect(0, 0, self.width(), self.height(), 2, 2)


# ---------------------------------------------------------------------------
# Live Data Panel
# ---------------------------------------------------------------------------

class LiveDataPanel(QWidget):
    """
    Grid of SignalCard widgets for all monitored J1939 parameters.
    Updated by the CANInterface via the parent's QTimer.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        # Header
        header = QLabel("LIVE VEHICLE DATA  —  J1939 CAN Bus")
        header.setStyleSheet(
            f"color: {COLOR_TEXT_SECONDARY}; font-size: 11px; "
            f"font-weight: 700; letter-spacing: 1.5px;"
        )
        root.addWidget(header)

        sep = QFrame()
        sep.setObjectName("separator")
        sep.setFrameShape(QFrame.HLine)
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background-color: {COLOR_BORDER};")
        root.addWidget(sep)

        # Card grid
        grid = QGridLayout()
        grid.setSpacing(10)

        # Define all signal cards
        self._cards: dict[str, SignalCard] = {
            "engine_rpm": SignalCard(
                "Engine Speed", "RPM",
                normal_low=600, normal_high=2200,
                warn_low=400, warn_high=2300,
                crit_low=0, crit_high=2500,
                fmt="{:.0f}"
            ),
            "coolant_temp_c": SignalCard(
                "Coolant Temp", "°C",
                normal_low=75, normal_high=98,
                warn_high=102, crit_high=107,
                warn_low=50, crit_low=0,
                fmt="{:.1f}"
            ),
            "oil_temp_c": SignalCard(
                "Oil Temp", "°C",
                normal_low=80, normal_high=120,
                warn_high=128, crit_high=138,
                warn_low=60, crit_low=0,
                fmt="{:.1f}"
            ),
            "oil_pressure_kpa": SignalCard(
                "Oil Pressure", "kPa",
                normal_low=240, normal_high=450,
                warn_low=150, crit_low=80,
                warn_high=500, crit_high=700,
                fmt="{:.0f}"
            ),
            "fuel_pressure_kpa": SignalCard(
                "Fuel Pressure", "kPa",
                normal_low=500, normal_high=700,
                warn_low=300, crit_low=150,
                warn_high=800, crit_high=1000,
                fmt="{:.0f}"
            ),
            "battery_voltage": SignalCard(
                "Battery Voltage", "V",
                normal_low=12.5, normal_high=14.8,
                warn_low=11.5, crit_low=10.5,
                warn_high=15.5, crit_high=16.0,
                fmt="{:.2f}"
            ),
            "engine_torque_pct": SignalCard(
                "Engine Torque", "%",
                normal_low=0, normal_high=100,
                warn_low=-10, crit_low=-50,
                warn_high=105, crit_high=120,
                fmt="{:.0f}"
            ),
        }

        positions = [
            ("engine_rpm",        0, 0),
            ("coolant_temp_c",    0, 1),
            ("oil_temp_c",        0, 2),
            ("oil_pressure_kpa",  1, 0),
            ("fuel_pressure_kpa", 1, 1),
            ("battery_voltage",   1, 2),
            ("engine_torque_pct", 2, 0),
        ]
        for key, row, col in positions:
            grid.addWidget(self._cards[key], row, col)

        root.addLayout(grid)
        root.addStretch()

    def update_signals(self, signals: dict):
        """Called by main window with latest decoded signal dict."""
        for key, card in self._cards.items():
            if key in signals:
                card.update_value(signals[key])