"""Debug helper to validate canonical MuPDF matrices."""

from __future__ import annotations

import random
import sys
from pathlib import Path

try:  # pragma: no cover - optional dependency during docs builds
    import fitz  # type: ignore
except ImportError:  # pragma: no cover
    fitz = None  # type: ignore

from PIL import Image, ImageDraw  # type: ignore

from .mupdf_canon import build_canon_page

RANDOM_SEED = 1337
SAMPLE_COUNT = 50
EPSILON = 1e-3


def _pixmap_to_image(pixmap: "fitz.Pixmap") -> Image.Image:
    if pixmap.n not in (1, 3):
        pixmap = fitz.Pixmap(fitz.csRGB, pixmap)  # type: ignore[attr-defined]
    mode = "L" if pixmap.n == 1 else "RGB"
    return Image.frombytes(mode, (pixmap.width, pixmap.height), pixmap.samples)


def main(argv: list[str]) -> int:
    if fitz is None:
        print("CANON_FAIL missing-pymupdf", file=sys.stderr)
        return 1

    if len(argv) != 2:
        print("Usage: python -m hushdesk.pdf.debug_canon <pdf-path>", file=sys.stderr)
        return 1

    pdf_path = Path(argv[1]).expanduser()
    if not pdf_path.exists():
        print(f"CANON_FAIL missing-pdf path={pdf_path}", file=sys.stderr)
        return 1

    doc = fitz.open(str(pdf_path))
    try:
        page = doc.load_page(0)
        canon = build_canon_page(0, page, scale=2.0)
        words = canon.words
        width = canon.width
        height = canon.height

        if not words:
            print("CANON_FAIL no-words", file=sys.stderr)
            return 1

        min_x = min(word.bbox[0] for word in words)
        min_y = min(word.bbox[1] for word in words)
        max_x = max(word.bbox[2] for word in words)
        max_y = max(word.bbox[3] for word in words)

        if (
            min_x < -EPSILON
            or min_y < -EPSILON
            or max_x > width + EPSILON
            or max_y > height + EPSILON
        ):
            print(
                "CANON_FAIL bounds "
                f"w={width:.2f} h={height:.2f} "
                f"minx={min_x:.2f} miny={min_y:.2f} "
                f"maxx={max_x:.2f} maxy={max_y:.2f}",
                file=sys.stderr,
            )
            return 1

        debug_dir = Path("debug")
        debug_dir.mkdir(parents=True, exist_ok=True)
        image = _pixmap_to_image(canon.pixmap)
        draw = ImageDraw.Draw(image)
        random.seed(RANDOM_SEED)

        choices = words if len(words) <= SAMPLE_COUNT else random.sample(words, SAMPLE_COUNT)
        for word in choices:
            x0, y0, x1, y1 = word.bbox
            draw.rectangle([x0, y0, x1, y1], outline="#ff0000", width=2)

        output_path = debug_dir / "qa_p1_words.png"
        image.save(output_path)

        print(
            "CANON_OK "
            f"w={int(width)} h={int(height)} "
            f"minx={min_x:.2f} miny={min_y:.2f} "
            f"maxx={max_x:.2f} maxy={max_y:.2f} "
            f"words={len(words)}"
        )
        return 0
    finally:
        doc.close()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
