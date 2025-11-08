from __future__ import annotations
from PySide6.QtCore import Qt, QCoreApplication
def apply():
    # Safe to call multiple times; prefer pass-through rounding on Retina
    QCoreApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    try:
        from PySide6.QtCore import QHighDpiScaleFactorRoundingPolicy as Rounding
        QCoreApplication.setHighDpiScaleFactorRoundingPolicy(Rounding.PassThrough)
    except Exception:
        pass
