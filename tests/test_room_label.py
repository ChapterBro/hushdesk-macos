import pytest

from hushdesk.pdf.room_label import (
    format_room_label,
    parse_room_and_bed_from_text,
    validate_room,
)


def test_room_label_from_labeled_fields_morton():
    txt = "Patient  •  Room 404  •  Location 1  •  MRN 3672  •  Page 11"
    labeled = parse_room_and_bed_from_text(txt)
    # hall validation is best-effort; call with hall known
    v = validate_room("MORTON", labeled)
    room = format_room_label(v)
    assert room == "404-1"
