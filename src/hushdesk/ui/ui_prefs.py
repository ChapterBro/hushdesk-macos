from __future__ import annotations

from PySide6 import QtCore


class UIPrefs:
    """Thin wrapper around QSettings for UI persistence."""

    def __init__(self, org: str = "HushDesk", app: str = "HushDeskApp") -> None:
        self._settings = QtCore.QSettings(org, app)

    def get(self, key: str, default=None, *, type=None):
        if type is not None:
            value = self._settings.value(key, default, type=type)
        else:
            value = self._settings.value(key, default)
        return default if value is None else value

    def set(self, key: str, value) -> None:
        self._settings.setValue(key, value)

    def remove(self, key: str) -> None:
        self._settings.remove(key)

    def contains(self, key: str) -> bool:
        return self._settings.contains(key)

    def sync(self) -> None:
        self._settings.sync()

    # Compatibility helpers -------------------------------------------------

    def value(self, key: str, default=None, type=None):
        if type is not None:
            return self._settings.value(key, default, type=type)
        return self._settings.value(key, default)

    def setValue(self, key: str, value) -> None:  # noqa: N802 (Qt-style method)
        self._settings.setValue(key, value)
