# Guided diagnostic panel UI
"""
guided_diag_panel.py
--------------------
Guided diagnostic procedure UI — the step-by-step fault resolution workflow.

This is the centrepiece feature that mirrors what PACCAR's production
diagnostic tools do: walk a technician through a validated decision tree
to find and fix the root cause of a fault.

Layout:
  ┌──────────────────────────────────────────────┐
  │  Procedure header (title, DTC, severity)      │
  │  Progress bar + elapsed time                  │
  ├──────────────────────────────────────────────┤
  │  Step card (instruction text)                 │
  │                                               │
  │  [Choice A]  [Choice B]   (decision step)    │
  │  OR  [Step Complete →]    (action step)       │
  ├──────────────────────────────────────────────┤
  │  History log                                  │
  └──────────────────────────────────────────────┘
"""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFrame, QScrollArea, QTextEdit,
    QProgressBar, QSizePolicy, QSpacerItem
)
from PyQt5.QtCore import Qt, pyqtSignal, QTimer
from PyQt5.QtGui import QFont, QColor

from heavydiag.diagnostics.guided_procedure import (
    GuidedProcedure, ProcedureStep, ProcedureLibrary
)
from heavydiag.diagnostics.dtc_manager import ManagedDTC, DTCSeverity
from heavydiag.ui.styles import (
    COLOR_BG_CARD, COLOR_BORDER, COLOR_TEXT_PRIMARY, COLOR_TEXT_SECONDARY,
    COLOR_SUCCESS, COLOR_WARNING, COLOR_DANGER, COLOR_ACCENT,
    COLOR_TEXT_MUTED, COLOR_BG_PANEL, COLOR_BG_DARK
)


class GuidedDiagPanel(QWidget):
    """
    Full guided diagnostic panel.
    Loaded when user selects a DTC and clicks 'Start Guided Diagnosis'.
    """

    # Emitted when a procedure reaches a terminal step
    procedure_completed = pyqtSignal(str, str)  # dtc_code, outcome

    def __init__(self, procedure_library: ProcedureLibrary, parent=None):
        super().__init__(parent)
        self._library    = procedure_library
        self._procedure: GuidedProcedure | None = None
        self._dtc:       ManagedDTC | None = None
        self._timer      = QTimer()
        self._timer.timeout.connect(self._tick_timer)

        self._build_ui()
        self._show_idle_state()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start_procedure(self, dtc: ManagedDTC):
        """Launch the guided procedure for a specific DTC."""
        if not dtc.procedure_id:
            return
        self._dtc = dtc
        self._procedure = GuidedProcedure(
            self._library, dtc.procedure_id, dtc.dtc_code
        )
        self._procedure.on_step_change(self._render_step)
        self._history_log.clear()
        self._timer.start(1000)
        self._render_header()
        self._render_step(self._procedure.current_step())

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        # ---- Header section ----
        self._header_frame = QFrame()
        self._header_frame.setObjectName("card")
        header_layout = QVBoxLayout(self._header_frame)
        header_layout.setContentsMargins(16, 12, 16, 12)
        header_layout.setSpacing(6)

        top_row = QHBoxLayout()
        self._lbl_proc_title = QLabel("No Procedure Active")
        self._lbl_proc_title.setStyleSheet(
            f"color: {COLOR_TEXT_PRIMARY}; font-size: 16px; font-weight: 700;"
        )
        top_row.addWidget(self._lbl_proc_title)
        top_row.addStretch()

        self._lbl_severity = QLabel("")
        self._lbl_severity.setStyleSheet(
            f"color: {COLOR_TEXT_MUTED}; font-size: 12px; font-weight: 600; "
            f"border: 1px solid {COLOR_BORDER}; border-radius: 4px; padding: 3px 10px;"
        )
        top_row.addWidget(self._lbl_severity)
        header_layout.addLayout(top_row)

        self._lbl_dtc_code = QLabel("")
        self._lbl_dtc_code.setStyleSheet(
            f"color: {COLOR_TEXT_SECONDARY}; font-size: 12px;"
        )
        header_layout.addWidget(self._lbl_dtc_code)

        self._lbl_warning = QLabel("")
        self._lbl_warning.setStyleSheet(
            f"color: {COLOR_WARNING}; font-size: 12px; font-weight: 600; "
            f"background-color: #3A2800; border: 1px solid {COLOR_WARNING}; "
            f"border-radius: 4px; padding: 6px 10px;"
        )
        self._lbl_warning.setWordWrap(True)
        self._lbl_warning.hide()
        header_layout.addWidget(self._lbl_warning)

        # Tools required
        self._lbl_tools = QLabel("")
        self._lbl_tools.setStyleSheet(
            f"color: {COLOR_TEXT_SECONDARY}; font-size: 11px;"
        )
        header_layout.addWidget(self._lbl_tools)

        # Progress row
        progress_row = QHBoxLayout()
        self._progress_bar = QProgressBar()
        self._progress_bar.setTextVisible(False)
        self._progress_bar.setFixedHeight(6)
        progress_row.addWidget(self._progress_bar, stretch=1)
        self._lbl_timer = QLabel("00:00")
        self._lbl_timer.setStyleSheet(
            f"color: {COLOR_TEXT_MUTED}; font-size: 11px; padding-left: 8px;"
        )
        progress_row.addWidget(self._lbl_timer)
        header_layout.addLayout(progress_row)

        root.addWidget(self._header_frame)

        # ---- Step card ----
        self._step_frame = QFrame()
        self._step_frame.setObjectName("card")
        step_layout = QVBoxLayout(self._step_frame)
        step_layout.setContentsMargins(20, 16, 20, 16)
        step_layout.setSpacing(14)

        step_header = QHBoxLayout()
        self._lbl_step_num = QLabel("STEP 1")
        self._lbl_step_num.setStyleSheet(
            f"color: {COLOR_ACCENT}; font-size: 11px; font-weight: 700; letter-spacing: 1px;"
        )
        step_header.addWidget(self._lbl_step_num)
        step_header.addStretch()
        self._lbl_step_type = QLabel("")
        self._lbl_step_type.setStyleSheet(
            f"color: {COLOR_TEXT_MUTED}; font-size: 10px; font-weight: 600; "
            f"border: 1px solid {COLOR_BORDER}; border-radius: 3px; padding: 2px 8px;"
        )
        step_header.addWidget(self._lbl_step_type)
        step_layout.addLayout(step_header)

        self._lbl_instruction = QLabel("")
        self._lbl_instruction.setStyleSheet(
            f"color: {COLOR_TEXT_PRIMARY}; font-size: 14px; line-height: 1.5;"
        )
        self._lbl_instruction.setWordWrap(True)
        self._lbl_instruction.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self._lbl_instruction.setMinimumHeight(80)
        step_layout.addWidget(self._lbl_instruction)

        # Choice buttons area
        self._choices_frame = QWidget()
        self._choices_layout = QVBoxLayout(self._choices_frame)
        self._choices_layout.setContentsMargins(0, 0, 0, 0)
        self._choices_layout.setSpacing(8)
        step_layout.addWidget(self._choices_frame)

        root.addWidget(self._step_frame)

        # Back / navigation row
        nav_row = QHBoxLayout()
        self._btn_back = QPushButton("← Back")
        self._btn_back.setEnabled(False)
        self._btn_back.clicked.connect(self._on_back)
        self._btn_back.setFixedWidth(100)
        nav_row.addWidget(self._btn_back)
        nav_row.addStretch()

        self._btn_restart = QPushButton("↺ Restart")
        self._btn_restart.setEnabled(False)
        self._btn_restart.clicked.connect(self._on_restart)
        self._btn_restart.setFixedWidth(100)
        nav_row.addWidget(self._btn_restart)
        root.addLayout(nav_row)

        # ---- History log ----
        log_label = QLabel("DIAGNOSIS LOG")
        log_label.setStyleSheet(
            f"color: {COLOR_TEXT_SECONDARY}; font-size: 10px; font-weight: 700; letter-spacing: 1px;"
        )
        root.addWidget(log_label)

        self._history_log = QTextEdit()
        self._history_log.setReadOnly(True)
        self._history_log.setFixedHeight(100)
        self._history_log.setPlaceholderText(
            "Step-by-step actions will be recorded here…"
        )
        root.addWidget(self._history_log)

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def _render_header(self):
        if not self._procedure or not self._dtc:
            return
        self._lbl_proc_title.setText(self._procedure.title)
        sev = self._dtc.severity
        self._lbl_severity.setText(f"{sev.icon} {sev.value.upper()}")
        self._lbl_severity.setStyleSheet(
            f"color: {sev.color}; font-size: 12px; font-weight: 600; "
            f"background-color: {sev.color}22; "
            f"border: 1px solid {sev.color}; border-radius: 4px; padding: 3px 10px;"
        )
        self._lbl_dtc_code.setText(
            f"DTC: {self._dtc.dtc_code}  |  "
            f"Component: {self._dtc.component_name}  |  "
            f"Subsystem: {self._dtc.subsystem}"
        )
        if self._procedure.warning:
            self._lbl_warning.setText(f"⚠  {self._procedure.warning}")
            self._lbl_warning.show()
        if self._procedure.tools_needed:
            self._lbl_tools.setText(
                "🔧 Tools: " + " · ".join(self._procedure.tools_needed)
            )
        self._btn_restart.setEnabled(True)

    def _render_step(self, step: ProcedureStep):
        if not step or not self._procedure:
            return

        taken, total = self._procedure.progress()
        self._lbl_step_num.setText(f"STEP {taken + 1}")
        self._progress_bar.setMaximum(max(total, 1))
        self._progress_bar.setValue(taken)

        self._lbl_instruction.setText(step.instruction)
        self._lbl_step_type.setText(step.step_type.upper())
        self._btn_back.setEnabled(self._procedure.can_go_back())

        # Clear previous choice buttons
        while self._choices_layout.count():
            item = self._choices_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if step.step_type == "decision":
            for choice_label in step.choices:
                btn = QPushButton(choice_label)
                btn.setMinimumHeight(38)
                btn.setStyleSheet(
                    f"QPushButton {{ background-color: {COLOR_BG_DARK}; "
                    f"color: {COLOR_TEXT_PRIMARY}; border: 1px solid {COLOR_BORDER}; "
                    f"border-radius: 5px; padding: 8px 16px; text-align: left; }}"
                    f"QPushButton:hover {{ background-color: {COLOR_ACCENT}22; "
                    f"border-color: {COLOR_ACCENT}; }}"
                )
                btn.clicked.connect(
                    lambda checked, c=choice_label: self._on_choice(c)
                )
                self._choices_layout.addWidget(btn)

        elif step.step_type == "action":
            btn = QPushButton("✓  Step Complete — Continue →")
            btn.setObjectName("btn_success")
            btn.setMinimumHeight(38)
            btn.clicked.connect(self._on_advance)
            self._choices_layout.addWidget(btn)

        elif step.step_type == "terminal":
            self._render_terminal(step)

        # Append to history log
        self._history_log.append(
            f"[{self._procedure.elapsed_time_str()}] "
            f"Step {taken + 1}: {step.instruction[:80]}{'…' if len(step.instruction) > 80 else ''}"
        )

    def _render_terminal(self, step: ProcedureStep):
        outcome = step.outcome
        if outcome == "resolved":
            color, icon, msg = COLOR_SUCCESS, "✅", "FAULT RESOLVED"
        elif outcome == "escalate":
            color, icon, msg = COLOR_WARNING, "⬆️", "ESCALATE TO DEALER"
        else:
            color, icon, msg = COLOR_TEXT_MUTED, "ℹ️", "PROCEDURE COMPLETE"

        result_frame = QFrame()
        result_frame.setStyleSheet(
            f"background-color: {color}22; border: 2px solid {color}; border-radius: 6px;"
        )
        result_layout = QVBoxLayout(result_frame)
        result_layout.setContentsMargins(16, 12, 16, 12)

        lbl = QLabel(f"{icon}  {msg}")
        lbl.setStyleSheet(
            f"color: {color}; font-size: 16px; font-weight: 700; border: none;"
        )
        result_layout.addWidget(lbl)
        self._choices_layout.addWidget(result_frame)
        self._timer.stop()

        if self._procedure and self._dtc:
            self.procedure_completed.emit(self._dtc.dtc_code, outcome)
            self._history_log.append(
                f"\n=== OUTCOME: {msg} | "
                f"Total time: {self._procedure.elapsed_time_str()} ==="
            )

    def _show_idle_state(self):
        self._lbl_proc_title.setText("No Procedure Active")
        self._lbl_dtc_code.setText(
            "Select a DTC on the Fault Codes tab and click 'Start Guided Diagnosis'."
        )
        self._lbl_instruction.setText("")
        self._lbl_step_num.setText("")

    # ------------------------------------------------------------------
    # Button handlers
    # ------------------------------------------------------------------

    def _on_choice(self, choice: str):
        if self._procedure:
            self._procedure.choose(choice)

    def _on_advance(self):
        if self._procedure:
            self._procedure.advance()

    def _on_back(self):
        if self._procedure:
            self._procedure.go_back()

    def _on_restart(self):
        if self._dtc:
            self.start_procedure(self._dtc)

    def _tick_timer(self):
        if self._procedure:
            self._lbl_timer.setText(self._procedure.elapsed_time_str())