"""Page images in, model-ready bytes out: EXIF rotation applied, long side capped, JPEG-encoded; PDFs rendered page by page."""
from __future__ import annotations

import io
from pathlib import Path
from typing import Iterable

from PIL import Image, ImageOps

MAX_SIDE = 2000
JPEG_QUALITY = 90


def prepare(img: Image.Image, max_side: int = MAX_SIDE, quality: int = JPEG_QUALITY) -> bytes:
    img = ImageOps.exif_transpose(img)
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    w, h = img.size
    scale = min(1.0, max_side / max(w, h))
    if scale < 1.0:
        img = img.resize((max(1, round(w * scale)), max(1, round(h * scale))), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality, optimize=True)
    return buf.getvalue()


def pdf_pages(data: bytes, dpi: int = 170, max_pages: int = 20) -> list[Image.Image]:
    import pypdfium2 as pdfium
    doc = pdfium.PdfDocument(data)
    out = []
    for i in range(min(len(doc), max_pages)):
        page = doc[i]
        out.append(page.render(scale=dpi / 72).to_pil())
    return out


def load_pages(source: str | Path | bytes, filename: str | None = None) -> list[bytes]:
    """A path or raw bytes (image or PDF) -> one JPEG byte-string per page."""
    if isinstance(source, (str, Path)):
        p = Path(source)
        data = p.read_bytes()
        filename = p.name
    else:
        data = source
        filename = filename or ""
    is_pdf = data[:5] == b"%PDF-" or filename.lower().endswith(".pdf")
    if is_pdf:
        return [prepare(im) for im in pdf_pages(data)]
    return [prepare(Image.open(io.BytesIO(data)))]


def load_many(sources: Iterable[str | Path]) -> list[tuple[str, bytes]]:
    out = []
    for s in sources:
        pages = load_pages(s)
        name = Path(s).name
        for i, b in enumerate(pages, 1):
            out.append((f"{name}#p{i}" if len(pages) > 1 else name, b))
    return out
