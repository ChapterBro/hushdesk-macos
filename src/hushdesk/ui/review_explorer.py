"""Review Explorer panel for grouped decision navigation."""

from __future__ import annotations

from functools import partial
from typing import Dict, Iterable, List, Optional, Set

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QLineEdit,
    QSizePolicy,
    QStyle,
    QTabWidget,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)


_KIND_ORDER: List[str] = ["HOLD-MISS", "HELD-OK", "COMPLIANT", "DC'D"]
_COUNT_KEY_MAP: Dict[str, str] = {
    "HOLD-MISS": "hold_miss",
    "HELD-OK": "held_ok",
    "COMPLIANT": "compliant",
    "DC'D": "dcd",
}


class ReviewExplorer(QWidget):
    """Grouped decision list with search, QA mode, and anomaly navigation."""

    record_selected = Signal(dict)
    anomaly_selected = Signal(dict)
    preview_requested = Signal(dict)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setMinimumWidth(260)
        self._records: List[dict] = []
        self._counts: Dict[str, int] = {}
        self._filter_text = ""
        self._exceptions_only = False
        self._qa_mode_enabled = False
        self._anomalies: List[dict] = []
        self._anomaly_filter_ids: Optional[Set[int]] = None

        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(8)

        title = QLabel("Review Explorer")
        title.setStyleSheet("font-size: 14px; font-weight: 600;")
        header.addWidget(title, stretch=1)

        layout.addLayout(header)

        search_frame = QFrame()
        search_layout = QHBoxLayout(search_frame)
        search_layout.setContentsMargins(0, 0, 0, 0)
        search_layout.setSpacing(8)

        self.search_field = QLineEdit()
        self.search_field.setPlaceholderText("Search room, rule, vital…")
        self.search_field.textChanged.connect(self._on_search_changed)

        self.exceptions_toggle = QCheckBox("Exceptions only")
        self.exceptions_toggle.stateChanged.connect(self._on_exceptions_changed)

        search_layout.addWidget(self.search_field, stretch=1)
        search_layout.addWidget(self.exceptions_toggle)

        layout.addWidget(search_frame)

        self.tree = QTreeWidget()
        self.tree.setColumnCount(3)
        self.tree.setHeaderHidden(True)
        self.tree.setRootIsDecorated(False)
        self.tree.setAlternatingRowColors(False)
        self.tree.setSelectionMode(QTreeWidget.SelectionMode.SingleSelection)
        self.tree.itemSelectionChanged.connect(self._on_selection_changed)
        self.tree.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        header_view = self.tree.header()
        header_view.setStretchLastSection(False)
        header_view.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header_view.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header_view.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        header_view.resizeSection(2, 52)
        self.tree.setColumnHidden(1, True)

        decisions_container = QWidget()
        decisions_layout = QVBoxLayout(decisions_container)
        decisions_layout.setContentsMargins(0, 0, 0, 0)
        decisions_layout.setSpacing(0)
        decisions_layout.addWidget(self.tree)

        self.anomaly_list = QListWidget()
        self.anomaly_list.itemClicked.connect(self._on_anomaly_clicked)

        anomalies_container = QWidget()
        anomalies_layout = QVBoxLayout(anomalies_container)
        anomalies_layout.setContentsMargins(0, 0, 0, 0)
        anomalies_layout.setSpacing(0)
        anomalies_layout.addWidget(self.anomaly_list)

        self.tab_widget = QTabWidget()
        self.tab_widget.addTab(decisions_container, "Decisions")
        self.tab_widget.addTab(anomalies_container, "Anomalies (0)")

        layout.addWidget(self.tab_widget, stretch=1)

        footer = QLabel("Select a row to view evidence. QA Mode surfaces source and cluster metrics.")
        footer.setStyleSheet("color: #6b7280; font-size: 12px;")
        layout.addWidget(footer)

    def update_records(self, *, counts: Optional[Dict[str, int]] = None, records: Iterable[dict]) -> None:
        if counts is not None:
            normalized = {key: int(value) for key, value in counts.items()}
            self._counts = normalized
        self._records = [dict(record) for record in records]
        self._anomaly_filter_ids = None
        self._apply_filters()

    def update_anomalies(self, anomalies: Iterable[dict]) -> None:
        self._anomalies = [dict(entry) for entry in anomalies]
        self._populate_anomaly_list()

    def set_qa_mode(self, enabled: bool) -> None:
        if self._qa_mode_enabled == enabled:
            return
        self._qa_mode_enabled = enabled
        self.tree.setColumnHidden(1, not enabled)
        self._apply_filters()

    def apply_anomaly_filter(self, anomaly: dict) -> None:
        if not isinstance(anomaly, dict):
            return
        self.tab_widget.setCurrentIndex(0)
        record_ids = anomaly.get("record_ids") if isinstance(anomaly.get("record_ids"), list) else []
        ids = {int(rid) for rid in record_ids if isinstance(rid, int)}
        if ids:
            self._anomaly_filter_ids = ids
            self.search_field.blockSignals(True)
            self.search_field.clear()
            self.search_field.blockSignals(False)
            self._filter_text = ""
            self._apply_filters()
            self._select_first_filtered_record()
            return

        target = " ".join(
            part for part in (anomaly.get("room_bed"), anomaly.get("slot")) if part
        ).strip()
        self._anomaly_filter_ids = None
        if target:
            self.search_field.blockSignals(True)
            self.search_field.setText(target)
            self.search_field.blockSignals(False)
            return
        self._apply_filters()

    def clear_anomaly_filter(self) -> None:
        self._anomaly_filter_ids = None
        self._apply_filters()

    def clear(self) -> None:
        self._records = []
        self._counts = {}
        self._filter_text = ""
        self._exceptions_only = False
        self._anomalies = []
        self._anomaly_filter_ids = None
        self.search_field.blockSignals(True)
        self.search_field.clear()
        self.search_field.blockSignals(False)
        self.exceptions_toggle.blockSignals(True)
        self.exceptions_toggle.setChecked(False)
        self.exceptions_toggle.blockSignals(False)
        self.tree.clear()
        self.anomaly_list.clear()
        self._update_anomaly_tab_label()

    def _on_search_changed(self, text: str) -> None:
        self._filter_text = text.strip().lower()
        self._anomaly_filter_ids = None
        self._apply_filters()

    def _on_exceptions_changed(self, state: int) -> None:
        self._exceptions_only = state == Qt.CheckState.Checked
        self._apply_filters()

    def _apply_filters(self) -> None:
        self.tree.blockSignals(True)
        self.tree.clear()

        filter_text = self._filter_text
        exceptions_only = self._exceptions_only
        filter_ids = self._anomaly_filter_ids

        for kind in _KIND_ORDER:
            kind_records = [record for record in self._records if record.get("kind") == kind]
            count_key = _COUNT_KEY_MAP.get(kind)
            if not kind_records and (count_key is None or count_key not in self._counts):
                continue
            total_count = self._counts.get(count_key, len(kind_records)) if count_key else len(kind_records)
            filtered = [
                record
                for record in kind_records
                if self._record_visible(record, filter_text, exceptions_only, filter_ids)
            ]

            if not filtered and total_count == 0:
                continue

            header_text = f"{kind} ({total_count})"
            header_item = QTreeWidgetItem([header_text, "", ""])
            header_item.setFlags(header_item.flags() & ~Qt.ItemIsSelectable)
            header_item.setFirstColumnSpanned(True)
            self.tree.addTopLevelItem(header_item)

            if not filtered:
                placeholder = QTreeWidgetItem(["(no matches)", "", ""])
                placeholder.setFlags(placeholder.flags() & ~Qt.ItemIsSelectable)
                placeholder.setFirstColumnSpanned(True)
                header_item.addChild(placeholder)
                header_item.setExpanded(True)
                continue

            for record in filtered:
                item = QTreeWidgetItem(["", "", ""])
                item.setData(0, Qt.ItemDataRole.UserRole, record)
                self._decorate_record_item(item, record)
                header_item.addChild(item)
                button = self._make_preview_button(record)
                self.tree.setItemWidget(item, 2, button)

            header_item.setExpanded(True)

        self.tree.blockSignals(False)
        if self._anomaly_filter_ids:
            self._select_first_filtered_record()

    @staticmethod
    def _record_visible(
        record: dict,
        filter_text: str,
        exceptions_only: bool,
        filter_ids: Optional[Set[int]],
    ) -> bool:
        if exceptions_only and not record.get("exception"):
            return False
        if filter_ids is not None:
            record_id = record.get("id")
            if record_id not in filter_ids:
                return False
        if not filter_text:
            return True
        blob = record.get("search_blob") or ""
        return filter_text in blob

    def _decorate_record_item(self, item: QTreeWidgetItem, record: dict) -> None:
        item.setText(0, self._format_row(record))
        if self._qa_mode_enabled:
            qa_text, qa_color = self._qa_details(record)
            item.setText(1, qa_text)
            if qa_color is not None:
                item.setForeground(1, qa_color)
            else:
                item.setData(1, Qt.ItemDataRole.ForegroundRole, None)
        else:
            item.setText(1, "")
            item.setData(1, Qt.ItemDataRole.ForegroundRole, None)

    def _qa_details(self, record: dict) -> tuple[str, Optional[QColor]]:
        source_meta = record.get("source_meta") if isinstance(record.get("source_meta"), dict) else {}
        extras = record.get("extras") if isinstance(record.get("extras"), dict) else {}

        source = source_meta.get("vital_source") or record.get("source_type") or extras.get("source_type")
        dy_value = source_meta.get("dy_px")
        dy_px = float(dy_value) if isinstance(dy_value, (int, float)) else None

        parts: List[str] = []
        if source:
            parts.append(f"source={source}")
        if dy_px is not None:
            parts.append(f"dy={dy_px:+.0f}px")

        flags: List[str] = []
        if record.get("vital_bbox") is None:
            flags.append("NoVital")
        code_value = record.get("code")
        if code_value is not None and not record.get("triggered", False):
            flags.append("Code-NoTrigger")
        slot_boxes = record.get("slot_bboxes") if isinstance(record.get("slot_bboxes"), dict) else {}
        if not slot_boxes or slot_boxes.get("AM") is None or slot_boxes.get("PM") is None:
            flags.append("NoSlots")

        if flags:
            flag_blob = ", ".join(flags)
            parts.append(f"flags: {flag_blob}")

        text = " | ".join(parts)

        color: Optional[QColor] = None
        if "NoVital" in flags:
            color = QColor("#DC2626")
        elif "NoSlots" in flags:
            color = QColor("#CA8A04")
        elif "Code-NoTrigger" in flags:
            color = QColor("#6B7280")

        return text, color

    def _format_row(self, record: dict) -> str:
        room = record.get("room_bed") or "Unknown"
        dose = record.get("slot_label") or record.get("dose") or "-"
        rule_text = record.get("rule_text") or ""
        vital_text = record.get("vital_text") or ""
        mark_display = record.get("mark_display") or ""

        parts = [f"{room} ({dose})"]
        if rule_text:
            parts.append(rule_text)
        if vital_text:
            parts.append(vital_text)
        if mark_display:
            parts.append(mark_display)

        return " · ".join(parts)

    def _on_selection_changed(self) -> None:
        selected = self.tree.selectedItems()
        if not selected:
            return
        for item in selected:
            payload = item.data(0, Qt.ItemDataRole.UserRole)
            if isinstance(payload, dict):
                self.record_selected.emit(dict(payload))
                break

    def _populate_anomaly_list(self) -> None:
        self.anomaly_list.clear()
        for anomaly in self._anomalies:
            text = anomaly.get("message") or "(unknown anomaly)"
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, anomaly)
            self.anomaly_list.addItem(item)
        self._update_anomaly_tab_label()

    def _update_anomaly_tab_label(self) -> None:
        count = len(self._anomalies)
        self.tab_widget.setTabText(1, f"Anomalies ({count})")

    def _on_anomaly_clicked(self, item: QListWidgetItem) -> None:
        payload = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(payload, dict):
            self.anomaly_selected.emit(dict(payload))

    def _make_preview_button(self, record: dict) -> QToolButton:
        button = QToolButton(self.tree)
        button.setAutoRaise(True)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        icon = self.style().standardIcon(QStyle.StandardPixmap.SP_DialogOpenButton)
        button.setIcon(icon)
        button.setToolTip("Open decision preview")
        payload = dict(record)
        button.clicked.connect(partial(self.preview_requested.emit, payload))
        return button

    def _select_first_filtered_record(self) -> None:
        if not self._anomaly_filter_ids:
            return
        for index in range(self.tree.topLevelItemCount()):
            header_item = self.tree.topLevelItem(index)
            for child_index in range(header_item.childCount()):
                child = header_item.child(child_index)
                payload = child.data(0, Qt.ItemDataRole.UserRole)
                if not isinstance(payload, dict):
                    continue
                record_id = payload.get("id")
                if record_id in self._anomaly_filter_ids:
                    self.tree.setCurrentItem(child)
                    return
