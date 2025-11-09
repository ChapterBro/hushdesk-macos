"""UI module namespace for HushDesk."""

__all__ = ["MainWindow"]


def __getattr__(name: str):
    if name == "MainWindow":
        from .main_window import MainWindow  # noqa: WPS433 (late import to avoid cycles)

        return MainWindow
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
