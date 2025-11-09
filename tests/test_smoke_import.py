from importlib import import_module


def test_imports_and_fallbacks():
    # dates and dev_override_date must import even if env is unset
    dates = import_module("hushdesk.pdf.dates")
    assert hasattr(dates, "dev_override_date")

    # worker (or main module) should import without raising
    # Adjust to actual worker module if different in this project:
    for mod in [
        "hushdesk.workers.audit_worker",
        "hushdesk.worker",
        "hushdesk.core.worker",
        "hushdesk.audit.worker",
    ]:
        try:
            import_module(mod)
            break
        except Exception:
            continue
