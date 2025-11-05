"""Review Explorer panel for grouped decision navigation."""

from __future__ import annotations

from typing import Dict, Iterable, List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QSizePolicy,
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
    """Grouped decision list with search and filters."""

    record_selected = Signal(dict)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setMinimumWidth(260)
        self._records: List[dict] = []
        self._counts: Dict[str, int] = {}
        self._filter_text = ""
        self._exceptions_only = False

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
        self.tree.setHeaderHidden(True)
        self.tree.setRootIsDecorated(False)
        self.tree.setAlternatingRowColors(False)
        self.tree.setSelectionMode(QTreeWidget.SelectionMode.SingleSelection)
        self.tree.itemSelectionChanged.connect(self._on_selection_changed)
        self.tree.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        layout.addWidget(self.tree, stretch=1)

        footer = QLabel("Select a row to view evidence.")
        footer.setStyleSheet("color: #6b7280; font-size: 12px;")
        layout.addWidget(footer)

    def update_records(self, *, counts: Optional[Dict[str, int]] = None, records: Iterable[dict]) -> None:
        if counts is not None:
            normalized = {key: int(value) for key, value in counts.items()}
            self._counts = normalized
        self._records = [dict(record) for record in records]
        self._apply_filters()

    def clear(self) -> None:
        self._records = []
        self._counts = {}
        self.tree.clear()

    def _on_search_changed(self, text: str) -> None:
        self._filter_text = text.strip().lower()
        self._apply_filters()

    def _on_exceptions_changed(self, state: int) -> None:
        self._exceptions_only = state == Qt.CheckState.Checked
        self._apply_filters()

    def _apply_filters(self) -> None:
        self.tree.blockSignals(True)
        self.tree.clear()

        filter_text = self._filter_text
        exceptions_only = self._exceptions_only

        for kind in _KIND_ORDER:
            kind_records = [record for record in self._records if record.get("kind") == kind]
            count_key = _COUNT_KEY_MAP.get(kind)
            if not kind_records and (count_key is None or count_key not in self._counts):
                continue
            total_count = self._counts.get(count_key, len(kind_records)) if count_key else len(kind_records)
            filtered = [
                record
                for record in kind_records
                if self._record_visible(record, filter_text, exceptions_only)
            ]

            if not filtered and total_count == 0:
                continue

            header_text = f"{kind} ({total_count})"
            header_item = QTreeWidgetItem([header_text])
            header_item.setFlags(header_item.flags() & ~Qt.ItemIsSelectable)
            self.tree.addTopLevelItem(header_item)

            if not filtered:
                placeholder = QTreeWidgetItem(["(no matches)"])
                placeholder.setFlags(placeholder.flags() & ~Qt.ItemIsSelectable)
                header_item.addChild(placeholder)
                header_item.setExpanded(True)
                continue

            for record in filtered:
                item = QTreeWidgetItem([self._format_row(record)])
                item.setData(0, Qt.ItemDataRole.UserRole, record)
                header_item.addChild(item)

            header_item.setExpanded(True)

        self.tree.blockSignals(False)

    @staticmethod
    def _record_visible(record: dict, filter_text: str, exceptions_only: bool) -> bool:
        if exceptions_only and not record.get("exception"):
            return False
        if not filter_text:
            return True
        blob = record.get("search_blob") or ""
        return filter_text in blob

    @staticmethod
    def _format_row(record: dict) -> str:
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
