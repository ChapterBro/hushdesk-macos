"""Room and hall resolution tests."""

from __future__ import annotations

import unittest

from hushdesk.id.rooms import load_building_master, resolve_room_from_block


def _span(text: str) -> dict:
    return {"text": text, "bbox": (0.0, 0.0, 10.0, 10.0)}


class RoomResolverTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.master = load_building_master()

    def test_resolves_explicit_room_bed(self) -> None:
        result = resolve_room_from_block([_span("Room 101-1")], self.master)
        self.assertIsNotNone(result)
        room_bed, hall = result  # type: ignore[misc]
        self.assertEqual(room_bed, "101-1")
        self.assertEqual(hall, "Mercer")

    def test_resolves_whitespace_separator(self) -> None:
        result = resolve_room_from_block([_span("Bed 207 2")], self.master)
        self.assertIsNotNone(result)
        room_bed, hall = result  # type: ignore[misc]
        self.assertEqual(room_bed, "207-2")
        self.assertEqual(hall, "Holaday")

    def test_resolves_slash_separator(self) -> None:
        result = resolve_room_from_block([_span("At 318/1 today")], self.master)
        self.assertIsNotNone(result)
        room_bed, hall = result  # type: ignore[misc]
        self.assertEqual(room_bed, "318-1")
        self.assertEqual(hall, "Bridgeman")

    def test_defaults_bed_when_unspecified(self) -> None:
        result = resolve_room_from_block([_span("Morton 418")], self.master)
        self.assertIsNotNone(result)
        room_bed, hall = result  # type: ignore[misc]
        self.assertEqual(room_bed, "418-1")
        self.assertEqual(hall, "Morton")

    def test_rejects_room_not_in_master(self) -> None:
        result = resolve_room_from_block([_span("509-1")], self.master)
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
