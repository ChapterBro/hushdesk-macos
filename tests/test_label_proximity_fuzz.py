import importlib
import inspect


def test_label_slack_and_noise_mask_markers_present() -> None:
    module = importlib.import_module("hushdesk.pdf.mar_grid_extract")
    source = inspect.getsource(module)
    assert "PHASE6_LABEL_SLACK" in source
    assert "PHASE6_NOISE_MASK" in source
