import importlib
import inspect


def test_header_slice_marker_present() -> None:
    module = importlib.import_module("hushdesk.pdf.band_resolver")
    source = inspect.getsource(module)
    assert "PHASE6_TOLERANCE" in source
