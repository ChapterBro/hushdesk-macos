from hushdesk.pdf.band_resolver import Band, BandResolver


class DummyRect:
    def __init__(self, x0: float, y0: float, x1: float, y1: float):
        self.x0 = x0
        self.y0 = y0
        self.x1 = x1
        self.y1 = y1
        self.height = y1 - y0


class DummyPage:
    def __init__(self, header_text: str, page_text: str = ""):
        self.rect = DummyRect(0.0, 0.0, 100.0, 1000.0)
        self._header_text = header_text
        self._page_text = page_text or header_text

    def get_text(self, kind: str, clip=None):
        if clip is not None:
            return self._header_text
        return self._page_text


def test_header_y_tolerance_detects_shifted_date():
    resolver = BandResolver()
    page = DummyPage(header_text="Vitals DATE 11/11/2025")
    band = resolver.resolve(page)
    assert band is not None
    assert band.stage in {"header", "page"}


def test_borrow_only_with_reasonable_prev_band():
    resolver = BandResolver()
    prev = Band(100.0, 780.0, "header")
    page = DummyPage(header_text="", page_text="no date anywhere")
    band = resolver.resolve(page, prev)
    assert band is not None
    assert band.stage == "borrow"
    assert (band.y0, band.y1) == (prev.y0, prev.y1)
