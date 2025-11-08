import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QPixmap, QColor
from hushdesk.ui.preview_view import PreviewView

def test_previewview_offscreen_smoke_fit_and_actual():
    app = QApplication.instance() or QApplication([])

    v = PreviewView()
    pm = QPixmap(800, 500)
    pm.fill(QColor("white"))
    v.set_pixmap(pm)

    # Fit Page should not raise, no scrollbars, centered
    v.resize(1200, 800)
    v.set_fit_mode("fit-page")
    v._apply_fit()

    # Actual size should be unscaled but centered, still no exceptions
    v.set_fit_mode("actual")
    v._apply_fit()
