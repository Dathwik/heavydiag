"""
dtc_panel.py
------------
Displays active Diagnostic Trouble Codes in a table with severity badges.

Emits start_diagnosis_requested(dtc_code: str) when the technician clicks
"Start Guided Diagnosis" on a selected DTC row.
"""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFrame, QScrollArea, QSizePolicy
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont

from heavydiag.ui.styles import (
    COLOR_BG_CARD, COLOR_BORDER, COLOR_TEXT_PRIMARY, COLOR_TEXT_SECONDARY,
    COLOR_SUCCESS, COLOR_WARNING, COLOR_DANGER, COLOR_TEXT_MUTED,
    COLOR_BG_PANEL, COLOR_BG_DARK, COLOR_ACCENT
)


class DTCRow(QFrame):
    """One row in the DTC list representing a single fault code."""

    selected = pyqtSignal(str)   # emits dtc_code

    def __init__(self, dtc, parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        self.setFixedHeight(72)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setCursor(Qt.PointingHandCursor)
        self._dtc_code = dtc.dtc_code
        self._selected = False
        self._build_ui(dtc)

    def _build_ui(self, dtc):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 8, 16, 8)
        layout.setSpacing(16)

        # Severity indicator bar
        sev_bar = QFrame()
        sev_bar.setFixedWidth(4)
        sev_bar.setFixedHeight(48)
        sev_bar.setStyleSheet(
            f"background-color: {dtc.severity.color}; border-radius: 2px;"
        )
        layout.addWidget(sev_bar)

        # DTC code + component
        info_col = QVBoxLayout()
        info_col.setSpacing(3)

        code_lbl = QLabel(dtc.dtc_code)
        code_lbl.setStyleSheet(
            f"color: {COLOR_TEXT_PRIMARY}; font-size: 13px; font-weight: 700; "
            f"font-family: 'Consolas', monospace;"
        )
        info_col.addWidget(code_lbl)

        comp_lbl = QLabel(dtc.component_name)
        comp_lbl.setStyleSheet(
            f"color: {COLOR_TEXT_SECONDARY}; font-size: 11px;"
        )
        info_col.addWidget(comp_lbl)

        layout.addLayout(info_col, stretch=2)

        # Cause description
        cause_lbl = QLabel(dtc.fmi_cause)
        cause_lbl.setStyleSheet(
            f"color: {COLOR_TEXT_SECONDARY}; font-size: 11px;"
        )
        cause_lbl.setWordWrap(True)
        layout.addWidget(cause_lbl, stretch=3)

        # Right column: occurrences + age + severity badge
        right_col = QVBoxLayout()
        right_col.setSpacing(3)
        right_col.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        sev_badge = QLabel(dtc.severity.value.upper())
        sev_badge.setStyleSheet(
            f"color: {dtc.severity.color}; font-size: 10px; font-weight: 700; "
            f"border: 1px solid {dtc.severity.color}; border-radius: 3px; "
            f"padding: 2px 8px;"
        )
        sev_badge.setAlignment(Qt.AlignCenter)
        right_col.addWidget(sev_badge)

        meta_lbl = QLabel(f"OC: {dtc.occurrence_count}  ·  {dtc.age_str()}")
        meta_lbl.setStyleSheet(
            f"color: {COLOR_TEXT_MUTED}; font-size: 10px;"
        )
        meta_lbl.setAlignment(Qt.AlignRight)
        right_col.addWidget(meta_lbl)

        layout.addLayout(right_col)

        self._update_style(selected=False)

    def mousePressEvent(self, event):
        self.selected.emit(self._dtc_code)
        super().mousePressEvent(event)

    def set_selected(self, selected: bool):
        self._selected = selected
        self._update_style(selected)

    def _update_style(self, selected: bool):
        border = COLOR_ACCENT if selected else COLOR_BORDER
        self.setStyleSheet(
            f"QFrame#card {{ background-color: {COLOR_BG_CARD}; "
            f"border: 1px solid {border}; border-radius: 8px; }}"
        )


class DTCPanel(QWidget):
    """
    Full DTC panel — shows a scrollable list of active fault codes and
    a detail/action pane for the selected DTC.
    """

    start_diagnosis_requested = pyqtSignal(str)   # dtc_code

    def __init__(self, parent=None):
        super().__init__(parent)
        self._rows: dict[str, DTCRow] = {}
        self._dtc_map: dict = {}
        self._selected_code: str = ""
        self._clear_callback = None
        self._build_ui()

    def connect_clear_button(self, callback):
        self._clear_callback = callback

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        # Header
        header_row = QHBoxLayout()
        self._lbl_header = QLabel("ACTIVE FAULT CODES")
        self._lbl_header.setStyleSheet(
            f"color: {COLOR_TEXT_SECONDARY}; font-size: 11px; "
            f"font-weight: 700; letter-spacing: 1.5px;"
        )
        header_row.addWidget(self._lbl_header)
        header_row.addStretch()

        btn_clear = QPushButton("Clear All DTCs")
        btn_clear.setObjectName("btn_danger")
        btn_clear.setFixedWidth(120)
        btn_clear.clicked.connect(lambda: self._clear_callback and self._clear_callback())
        header_row.addWidget(btn_clear)
        root.addLayout(header_row)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background-color: {COLOR_BORDER};")
        root.addWidget(sep)

        # Main content: list (left) + detail (right)
        content = QHBoxLayout()
        content.setSpacing(12)

        # DTC list
        list_container = QWidget()
        list_container.setMinimumWidth(380)
        list_outer = QVBoxLayout(list_container)
        list_outer.setContentsMargins(0, 0, 0, 0)
        list_outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        scroll_content = QWidget()
        self._rows_layout = QVBoxLayout(scroll_content)
        self._rows_layout.setContentsMargins(0, 0, 4, 0)
        self._rows_layout.setSpacing(8)
        self._rows_layout.setAlignment(Qt.AlignTop)

        self._empty_label = QLabel("No active fault codes.\nSystem operating normally.")
        self._empty_label.setAlignment(Qt.AlignCenter)
        self._empty_label.setStyleSheet(
            f"color: {COLOR_TEXT_MUTED}; font-size: 13px; padding: 40px;"
        )
        self._rows_layout.addWidget(self._empty_label)

        scroll.setWidget(scroll_content)
        list_outer.addWidget(scroll)
        content.addWidget(list_container, stretch=2)

        # Detail pane
        self._detail_frame = QFrame()
        self._detail_frame.setObjectName("card")
        self._detail_frame.hide()
        detail_layout = QVBoxLayout(self._detail_frame)
        detail_layout.setContentsMargins(20, 16, 20, 16)
        detail_layout.setSpacing(10)

        self._det_code = QLabel("")
        self._det_code.setStyleSheet(
            f"color: {COLOR_TEXT_PRIMARY}; font-size: 18px; font-weight: 700; "
            f"font-family: 'Consolas', monospace;"
        )
        detail_layout.addWidget(self._det_code)

        self._det_component = QLabel("")
        self._det_component.setStyleSheet(
            f"color: {COLOR_ACCENT}; font-size: 12px; font-weight: 600;"
        )
        detail_layout.addWidget(self._det_component)

        sep2 = QFrame()
        sep2.setFrameShape(QFrame.HLine)
        sep2.setStyleSheet(f"background-color: {COLOR_BORDER};")
        detail_layout.addWidget(sep2)

        self._det_cause = self._make_field("Fault Cause", "")
        detail_layout.addLayout(self._det_cause[0])

        self._det_root = self._make_field("Likely Root Cause", "")
        detail_layout.addLayout(self._det_root[0])

        self._det_subsystem = self._make_field("Subsystem", "")
        detail_layout.addLayout(self._det_subsystem[0])

        detail_layout.addStretch()

        self._btn_start_diag = QPushButton("Start Guided Diagnosis →")
        self._btn_start_diag.setObjectName("btn_success")
        self._btn_start_diag.setFixedHeight(36)
        self._btn_start_diag.clicked.connect(self._on_start_diagnosis)
        detail_layout.addWidget(self._btn_start_diag)

        no_proc_lbl = QLabel("No guided procedure available for this DTC.")
        no_proc_lbl.setStyleSheet(
            f"color: {COLOR_TEXT_MUTED}; font-size: 11px;"
        )
        no_proc_lbl.setAlignment(Qt.AlignCenter)
        no_proc_lbl.hide()
        self._no_proc_label = no_proc_lbl
        detail_layout.addWidget(no_proc_lbl)

        content.addWidget(self._detail_frame, stretch=3)
        root.addLayout(content)

    def _make_field(self, label_text: str, value: str):
        layout = QVBoxLayout()
        layout.setSpacing(2)
        lbl = QLabel(label_text.upper())
        lbl.setStyleSheet(
            f"color: {COLOR_TEXT_MUTED}; font-size: 10px; font-weight: 700; "
            f"letter-spacing: 0.5px;"
        )
        val = QLabel(value)
        val.setStyleSheet(
            f"color: {COLOR_TEXT_SECONDARY}; font-size: 12px;"
        )
        val.setWordWrap(True)
        layout.addWidget(lbl)
        layout.addWidget(val)
        return layout, val

    # ------------------------------------------------------------------
    # Slots / helpers
    # ------------------------------------------------------------------

    def _on_row_selected(self, dtc_code: str):
        # Deselect previous
        if self._selected_code and self._selected_code in self._rows:
            self._rows[self._selected_code].set_selected(False)
        self._selected_code = dtc_code
        if dtc_code in self._rows:
            self._rows[dtc_code].set_selected(True)

        # Find the ManagedDTC — we need to get it from the row's parent widget
        # Since rows store the dtc_code only, find via sender's parent list
        # We store dtc objects during refresh for the detail pane
        dtc = self._dtc_map.get(dtc_code)
        if dtc:
            self._show_detail(dtc)

    def refresh_dtcs(self, dtcs: list):
        """Replace the displayed DTC list with a new set."""
        self._dtc_map = {d.dtc_code: d for d in dtcs}

        for row in self._rows.values():
            row.deleteLater()
        self._rows.clear()
        self._selected_code = ""

        if not dtcs:
            self._empty_label.show()
            self._detail_frame.hide()
            self._update_header(0)
            return

        self._empty_label.hide()

        severity_order = {"critical": 0, "warning": 1, "info": 2}
        for dtc in sorted(dtcs, key=lambda d: severity_order.get(d.severity.value, 9)):
            row = DTCRow(dtc)
            row.selected.connect(self._on_row_selected)
            self._rows_layout.addWidget(row)
            self._rows[dtc.dtc_code] = row

        self._update_header(len(dtcs))

        if dtcs:
            first = sorted(dtcs, key=lambda d: severity_order.get(d.severity.value, 9))[0]
            self._show_detail(first)
            if first.dtc_code in self._rows:
                self._rows[first.dtc_code].set_selected(True)
            self._selected_code = first.dtc_code

    def _show_detail(self, dtc):
        self._detail_frame.show()
        self._det_code.setText(dtc.dtc_code)
        self._det_component.setText(f"{dtc.component_name}  ·  {dtc.subsystem}")
        self._det_cause[1].setText(dtc.fmi_cause or "—")
        self._det_root[1].setText(dtc.root_cause_hint or "—")
        self._det_subsystem[1].setText(dtc.subsystem)

        has_proc = bool(dtc.procedure_id)
        self._btn_start_diag.setVisible(has_proc)
        self._no_proc_label.setVisible(not has_proc)

    def _on_start_diagnosis(self):
        if self._selected_code:
            self.start_diagnosis_requested.emit(self._selected_code)

    def _update_header(self, count: int):
        color = COLOR_DANGER if count > 0 else COLOR_TEXT_SECONDARY
        self._lbl_header.setText(
            f"ACTIVE FAULT CODES  —  {count} ACTIVE" if count else "ACTIVE FAULT CODES"
        )
        self._lbl_header.setStyleSheet(
            f"color: {color}; font-size: 11px; font-weight: 700; letter-spacing: 1.5px;"
        )
