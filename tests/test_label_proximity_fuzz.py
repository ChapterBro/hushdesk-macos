from hushdesk.pdf.mar_grid_extract import _augment_words_with_labels, _is_hr_label
from hushdesk.pdf.spatial_index import SpatialWordIndex


class DummyWord:
    def __init__(self, text: str, x: float, y: float):
        self.text = text
        self.center = (x, y)
        self.bbox = (x - 1.0, y - 1.0, x + 1.0, y + 1.0)


def _build_index(words):
    index = SpatialWordIndex.build(words)
    assert index is not None
    return index


def test_hr_label_spacing_extends_dx_window():
    label = DummyWord("HR", 10.0, 10.0)
    colon = DummyWord(":", 80.0, 10.0)
    digits = DummyWord("58", 150.0, 10.0)
    block_words = [label, colon, digits]
    augmented = _augment_words_with_labels(
        [label],
        block_words=block_words,
        band=(0.0, 20.0),
        index=_build_index(block_words),
        predicate=_is_hr_label,
        dx_steps=(110.0, 150.0),
    )
    assert any(word.text == "58" for word in augmented)


def test_stray_colon_not_treated_as_numeric():
    label = DummyWord("PULSE", 5.0, 5.0)
    colon = DummyWord(":", 70.0, 5.0)
    digits = DummyWord("110", 95.0, 5.0)
    block_words = [label, colon, digits]
    augmented = _augment_words_with_labels(
        [label],
        block_words=block_words,
        band=(0.0, 12.0),
        index=_build_index(block_words),
        predicate=_is_hr_label,
        dx_steps=(110.0, 150.0),
    )
    assert any(word.text == "110" for word in augmented)
    assert all(word.text != ":" for word in augmented)
