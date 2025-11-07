from __future__ import annotations

import json
import re
from pathlib import Path

APP_SUPPORT = Path.home() / "Library" / "Application Support" / "HushDesk" / "logs"
HEADLESS = APP_SUPPORT / "last_headless.json"
GUI_LOG = APP_SUPPORT / "gui_last_run.log"
PARITY = APP_SUPPORT / "parity.json"


def parse_gui_counts(log: str):
    # Expect a line like:
    # GUI_AUDIT_OK source=".../Administration Record Report 2025-11-05.pdf" reviewed=46 hm=0 ha=2 comp=38 dcd=6
    m = re.search(
        r"GUI_AUDIT_OK .* reviewed=(\d+)\s+hm=(\d+)\s+ha=(\d+)\s+comp=(\d+)\s+dcd=(\d+)",
        log,
    )
    if not m:
        return None
    r, hm, ha, comp, dcd = (int(x) for x in m.groups())
    return {
        "reviewed": r,
        "hold_miss": hm,
        "held_appropriate": ha,
        "compliant": comp,
        "dcd": dcd,
    }


def main():
    out = {
        "status": "fail",
        "reason": "",
        "headless": None,
        "gui": None,
        "equal": False,
    }
    if not HEADLESS.exists():
        out["reason"] = f"missing {HEADLESS}"
        PARITY.write_text(json.dumps(out, indent=2))
        print("PARITY_MISS headless_json")
        return 2
    if not GUI_LOG.exists():
        out["reason"] = f"missing {GUI_LOG}"
        PARITY.write_text(json.dumps(out, indent=2))
        print("PARITY_MISS gui_log")
        return 2

    headless = json.loads(HEADLESS.read_text())
    gui_text = GUI_LOG.read_text()
    gui_counts = parse_gui_counts(gui_text)
    if not gui_counts:
        out["reason"] = "GUI_AUDIT_OK line not found in gui_last_run.log"
        PARITY.write_text(json.dumps(out, indent=2))
        print("PARITY_MISS gui_ok_line")
        return 2

    h = headless.get("counts", {})
    same = all(
        int(h.get(k, -1)) == int(gui_counts.get(k, -2))
        for k in ("reviewed", "hold_miss", "held_appropriate", "compliant", "dcd")
    )

    out.update(
        {
            "status": "ok" if same else "diff",
            "headless": h,
            "gui": gui_counts,
            "equal": same,
        }
    )
    PARITY.write_text(json.dumps(out, indent=2))

    if same:
        print(
            "PARITY_OK reviewed={r} hm={hm} ha={ha} comp={c} dcd={d}".format(
                r=gui_counts["reviewed"],
                hm=gui_counts["hold_miss"],
                ha=gui_counts["held_appropriate"],
                c=gui_counts["compliant"],
                d=gui_counts["dcd"],
            )
        )
        return 0
    else:
        print(
            "PARITY_DIFF headless={h} gui={g}".format(
                h=h,
                g=gui_counts,
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
