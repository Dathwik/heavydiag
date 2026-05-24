# Main PyQt5 dashboard window
"""
main_window.py
--------------
Top-level application window for HeavyDiag.

Wires together:
  - ECUSimulator  (vehicle simulation)
  - VirtualCANBus (message transport)
  - CANInterface  (message decoder + dispatcher)
  - DTCManager    (fault tracking)
  - ProcedureLibrary (guided procedure definitions)
  - LiveDataPanel, DTCPanel, GuidedDiagPanel (UI tabs)

A QTimer polls the CANInterface for live signal data at 10 Hz to keep
the UI smooth without blocking the main thread.
"""

import time
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTabWidget, QLabel, QPushButton, QFrame,
    QComboBox, QStatusBar, QSplitter, QAction, QApplication
)
from PyQt5.QtCore import Qt, QTimer, pyqtSlot
from PyQt5.QtGui import QFont, QColor

from heavydiag.simulation.ecu import ECUSimulator, FaultType
from heavydiag.comms.can_interface import VirtualCANBus, CANInterface
from heavydiag.diagnostics.dtc_manager import DTCManager
from heavydiag.diagnostics.guided_procedure import ProcedureLibrary
from heavydiag.ui.live_data_panel import LiveDataPanel
from heavydiag.ui.dtc_panel import DTCPanel
from heavydiag.ui.guided_diag_panel import GuidedDiagPanel
from heavydiag.ui.styles import (
    MAIN_STYLESHEET, COLOR_BG_DARK, COLOR_BG_PANEL, COLOR_BG_CARD,
    COLOR_BORDER, COLOR_TEXT_PRIMARY, COLOR_TEXT_SECONDARY,
    COLOR_ACCENT, COLOR_DANGER, COLOR_WARNING, COLOR_SUCCESS,
    COLOR_TEXT_MUTED, COLOR_PACCAR_BLUE
)
from heavydiag.reports.report_generator import ReportGenerator


class MainWindow(QMainWindow):
    """HeavyDiag main application window."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("HeavyDiag — Off-Board Diagnostic Platform")
        self.setMinimumSize(1100, 720)
        self.setStyleSheet(MAIN_STYLESHEET)

        # --- Backend stack ---
        self._bus       = VirtualCANBus()
        self._ecu       = ECUSimulator(on_message=self._bus.send)
        self._interface = CANInterface(self._bus)
        self._dtc_mgr   = DTCManager()
        self._lib       = ProcedureLibrary()
        self._reporter  = ReportGenerator()

        # Wire DTC updates: CAN → DTCManager → UI
        self._interface.on_dtc(self._dtc_mgr.on_dtc_update)
        self._dtc_mgr.on_change(self._on_dtcs_changed)

        # --- Build UI ---
        self._build_menu()
        self._build_toolbar()
        self._build_central()
        self._build_status_bar()

        # --- Timers ---
        self._ui_timer = QTimer()
        self._ui_timer.timeout.connect(self._refresh_live_data)
        self._ui_timer.start(100)  # 10 Hz

        self._status_timer = QTimer()
        self._status_timer.timeout.connect(self._refresh_status_bar)
        self._status_timer.start(500)

        # --- Start backend ---
        self._interface.start()
        self._ecu.start()
        self._ecu.set_engine_rpm(800)

        self._log(f"HeavyDiag started. Simulated ECU online. CAN interface active.")

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_menu(self):
        menubar = self.menuBar()
        menubar.setStyleSheet(
            f"QMenuBar {{ background-color: {COLOR_BG_DARK}; color: {COLOR_TEXT_PRIMARY}; "
            f"border-bottom: 1px solid {COLOR_BORDER}; }}"
            f"QMenuBar::item:selected {{ background-color: {COLOR_ACCENT}; }}"
            f"QMenu {{ background-color: {COLOR_BG_CARD}; color: {COLOR_TEXT_PRIMARY}; "
            f"border: 1px solid {COLOR_BORDER}; }}"
            f"QMenu::item:selected {{ background-color: {COLOR_ACCENT}; }}"
        )
        file_menu = menubar.addMenu("File")
        export_action = QAction("Export Diagnostic Report…", self)
        export_action.triggered.connect(self._export_report)
        file_menu.addAction(export_action)
        file_menu.addSeparator()
        quit_action = QAction("Quit", self)
        quit_action.triggered.connect(QApplication.quit)
        file_menu.addAction(quit_action)

        diag_menu = menubar.addMenu("Diagnostics")
        clear_action = QAction("Clear All DTCs", self)
        clear_action.triggered.connect(self._clear_dtcs)
        diag_menu.addAction(clear_action)

    def _build_toolbar(self):
        """Top bar: branding + vehicle info + fault injection controls."""
        toolbar_widget = QWidget()
        toolbar_widget.setFixedHeight(56)
        toolbar_widget.setStyleSheet(
            f"background-color: {COLOR_BG_CARD}; "
            f"border-bottom: 1px solid {COLOR_BORDER};"
        )
        layout = QHBoxLayout(toolbar_widget)
        layout.setContentsMargins(16, 0, 16, 0)
        layout.setSpacing(16)

        # Branding
        brand = QLabel("⬡  HEAVYDIAG")
        brand.setStyleSheet(
            f"color: {COLOR_ACCENT}; font-size: 15px; font-weight: 800; letter-spacing: 2px;"
        )
        layout.addWidget(brand)

        sep = QFrame()
        sep.setFrameShape(QFrame.VLine)
        sep.setStyleSheet(f"color: {COLOR_BORDER};")
        layout.addWidget(sep)

        # Vehicle ID
        layout.addWidget(self._muted("Vehicle:"))
        vin_label = QLabel("KW T680  |  VIN: 1XKWDB0X0KJ123456  |  Engine: PACCAR MX-13")
        vin_label.setStyleSheet(f"color: {COLOR_TEXT_PRIMARY}; font-size: 12px;")
        layout.addWidget(vin_label)

        layout.addStretch()

        # RPM control
        layout.addWidget(self._muted("Engine RPM:"))
        self._rpm_combo = QComboBox()
        self._rpm_combo.addItems(["800 (Idle)", "1200", "1500", "1800", "2100"])
        self._rpm_combo.setFixedWidth(130)
        self._rpm_combo.currentTextChanged.connect(self._on_rpm_changed)
        layout.addWidget(self._rpm_combo)

        sep2 = QFrame()
        sep2.setFrameShape(QFrame.VLine)
        sep2.setStyleSheet(f"color: {COLOR_BORDER};")
        layout.addWidget(sep2)

        # Fault injection
        layout.addWidget(self._muted("Inject Fault:"))
        self._fault_combo = QComboBox()
        self._fault_combo.addItems([
            "— Select fault —",
            "High Coolant Temp",
            "Low Oil Pressure",
            "Low Battery Voltage",
            "Coolant Sensor Short",
            "Low Fuel Pressure",
        ])
        self._fault_combo.setFixedWidth(180)
        layout.addWidget(self._fault_combo)

        btn_inject = QPushButton("Inject")
        btn_inject.setObjectName("btn_danger")
        btn_inject.setFixedWidth(70)
        btn_inject.clicked.connect(self._on_inject_fault)
        layout.addWidget(btn_inject)

        btn_clear_faults = QPushButton("Clear All")
        btn_clear_faults.setFixedWidth(75)
        btn_clear_faults.clicked.connect(self._on_clear_all_faults)
        layout.addWidget(btn_clear_faults)

        # Add to window
        container = QWidget()
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)
        container_layout.addWidget(toolbar_widget)

        # Central + tabs go below toolbar
        self._main_container = container
        self.setCentralWidget(container)

    def _build_central(self):
        """Main tabbed content area."""
        self._tabs = QTabWidget()
        self._tabs.setTabPosition(QTabWidget.North)

        # Tab 1: Live Data
        self._live_panel = LiveDataPanel()
        self._tabs.addTab(self._live_panel, "📊  Live Data")

        # Tab 2: Fault Codes
        self._dtc_panel = DTCPanel()
        self._dtc_panel.start_diagnosis_requested.connect(self._launch_guided_diag)
        self._dtc_panel.connect_clear_button(self._clear_dtcs)
        self._tabs.addTab(self._dtc_panel, "⚠   Fault Codes")

        # Tab 3: Guided Diagnosis
        self._guided_panel = GuidedDiagPanel(self._lib)
        self._guided_panel.procedure_completed.connect(self._on_procedure_complete)
        self._tabs.addTab(self._guided_panel, "🔍  Guided Diagnosis")

        self._main_container.layout().addWidget(self._tabs)

    def _build_status_bar(self):
        sb = QStatusBar()
        sb.setStyleSheet(
            f"QStatusBar {{ background-color: {COLOR_BG_CARD}; "
            f"color: {COLOR_TEXT_SECONDARY}; "
            f"border-top: 1px solid {COLOR_BORDER}; font-size: 11px; }}"
        )
        self.setStatusBar(sb)

        self._lbl_bus_status = QLabel("🟢 CAN Bus: Active")
        self._lbl_bus_status.setStyleSheet(f"color: {COLOR_SUCCESS}; margin: 0 8px;")
        sb.addWidget(self._lbl_bus_status)

        sb.addWidget(self._v_sep())

        self._lbl_msg_count = QLabel("Messages: 0")
        sb.addWidget(self._lbl_msg_count)

        sb.addWidget(self._v_sep())

        self._lbl_active_dtcs = QLabel("Active DTCs: 0")
        sb.addWidget(self._lbl_active_dtcs)

        sb.addPermanentWidget(self._muted("HeavyDiag v1.0  |  J1939 Simulator  |  PACCAR Portfolio Project"))

    # ------------------------------------------------------------------
    # Timer callbacks
    # ------------------------------------------------------------------

    def _refresh_live_data(self):
        """Poll CANInterface for latest signals and update live data panel."""
        signals = self._interface.get_latest_signals()
        if signals:
            self._live_panel.update_signals(signals)

    def _refresh_status_bar(self):
        log = self._interface.get_message_log()
        self._lbl_msg_count.setText(f"Messages: {len(log)}")
        dtc_count = len(self._dtc_mgr.get_active_dtcs())
        self._lbl_active_dtcs.setText(f"Active DTCs: {dtc_count}")
        if dtc_count > 0:
            self._lbl_active_dtcs.setStyleSheet(f"color: {COLOR_DANGER}; margin: 0 8px;")
            # Update tab label
            self._tabs.setTabText(1, f"⚠   Fault Codes  ({dtc_count})")
        else:
            self._lbl_active_dtcs.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY}; margin: 0 8px;")
            self._tabs.setTabText(1, "⚠   Fault Codes")

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    @pyqtSlot(list)
    def _on_dtcs_changed(self, dtcs):
        """Called from DTCManager (background thread) — schedule UI update."""
        # Qt signal-slot will marshal to main thread safely
        self._dtc_panel.refresh_dtcs(dtcs)

    def _on_rpm_changed(self, text: str):
        rpm_str = text.split()[0]
        try:
            self._ecu.set_engine_rpm(float(rpm_str))
        except ValueError:
            pass

    def _on_inject_fault(self):
        fault_map = {
            "High Coolant Temp":     FaultType.HIGH_COOLANT_TEMP,
            "Low Oil Pressure":      FaultType.LOW_OIL_PRESSURE,
            "Low Battery Voltage":   FaultType.LOW_BATTERY_VOLTAGE,
            "Coolant Sensor Short":  FaultType.HIGH_COOLANT_TEMP_SENSOR_SHORT,
            "Low Fuel Pressure":     FaultType.FUEL_PRESSURE_LOW,
        }
        selected = self._fault_combo.currentText()
        fault    = fault_map.get(selected)
        if fault:
            self._ecu.inject_fault(fault)
            self._log(f"Fault injected: {selected}")
            # Auto-switch to fault codes tab
            self._tabs.setCurrentIndex(1)

    def _on_clear_all_faults(self):
        self._clear_dtcs()
        self._log("All faults and DTCs cleared.")

    def _clear_dtcs(self):
        self._ecu.clear_all_faults()
        self._dtc_mgr.clear_all_active()
        self._dtc_panel.refresh_dtcs([])

    def _launch_guided_diag(self, dtc_code: str):
        dtc = self._dtc_mgr.get_dtc(dtc_code)
        if dtc:
            self._guided_panel.start_procedure(dtc)
            self._tabs.setCurrentIndex(2)
            self._log(f"Guided diagnosis started for {dtc_code}")

    def _on_procedure_complete(self, dtc_code: str, outcome: str):
        self._dtc_mgr.set_resolution(dtc_code, outcome)
        self._log(f"Procedure for {dtc_code} completed: {outcome}")

    def _export_report(self):
        history = self._dtc_mgr.get_history()
        path = self._reporter.generate(history)
        self._log(f"Report exported to: {path}")
        self.statusBar().showMessage(f"Report saved: {path}", 5000)

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def closeEvent(self, event):
        self._ui_timer.stop()
        self._status_timer.stop()
        self._ecu.stop()
        self._interface.stop()
        event.accept()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _log(self, msg: str):
        self.statusBar().showMessage(msg, 3000)

    def _muted(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(f"color: {COLOR_TEXT_MUTED}; font-size: 11px;")
        return lbl

    def _v_sep(self) -> QFrame:
        sep = QFrame()
        sep.setFrameShape(QFrame.VLine)
        sep.setStyleSheet(f"color: {COLOR_BORDER};")
        sep.setFixedWidth(1)
        return sep