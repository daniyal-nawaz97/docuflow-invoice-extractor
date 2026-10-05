"""Turn an uploaded file into page images + positioned text segments.

Text PDFs  -> exact words from the PDF text layer.
Scans / photos -> offline OCR (RapidOCR), no internet needed.
Every segment keeps its box so the review screen can highlight where a value came from.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

from .config import MAX_PAGES_PER_DOC, PAGES_DIR

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff", ".heic"}
PDF_SCALE = 2.0  # render PDFs at 144 dpi

_ocr = None
_ocr_lock = threading.Lock()
_pdfium_lock = threading.Lock()  # pdfium is not thread-safe


class UnreadableDocument(Exception):
    """Raised with a friendly, client-facing message."""


@dataclass
class Segment:
    text: str
    box: tuple  # x0, y0, x1, y1 in page-image pixels
    conf: float = 1.0
    size: float = 0.0  # font size or box height


@dataclass
class Page:
    n: int
    width: int
    height: int
    image_path: str
    segments: list = field(default_factory=list)
    source: str = "text"  # text | ocr


@dataclass
class ReadResult:
    kind: str  # pdf | scan | photo
    pages: list
    sharpness: float | None = None
    images: list = field(default_factory=list)  # PIL images (kept for the AI vision model)


def _get_ocr():
    global _ocr
    with _ocr_lock:
        if _ocr is None:
            from rapidocr_onnxruntime import RapidOCR
            _ocr = RapidOCR()
        return _ocr


def _ocr_raw(img: Image.Image):
    engine = _get_ocr()
    with _ocr_lock:
        result, _ = engine(np.asarray(img.convert("RGB")))
    return result or []


def _to_segments(result) -> list[Segment]:
    segs = []
    for box, text, score in result:
        xs = [p[0] for p in box]; ys = [p[1] for p in box]
        x0, y0, x1, y1 = min(xs), min(ys), max(xs), max(ys)
        h = float(np.hypot(box[3][0] - box[0][0], box[3][1] - box[0][1])) or (y1 - y0)
        segs.append(Segment(text.strip(), (x0, y0, x1, y1), float(score), h))
    return [s for s in segs if s.text]


def _skew_degrees(result) -> float:
    """Median slope of the wider text boxes: a tilted photo makes rows drift into each other."""
    angles = []
    for box, text, _ in result:
        dx, dy = box[1][0] - box[0][0], box[1][1] - box[0][1]
        if dx > 60 and len(text) >= 4:
            angles.append(np.degrees(np.arctan2(dy, dx)))
    return float(np.median(angles)) if len(angles) >= 5 else 0.0


def ocr_page(img: Image.Image) -> tuple[Image.Image, list[Segment]]:
    """OCR a page image; tilted photos are straightened first so table rows stay on one line."""
    result = _ocr_raw(img)
    angle = _skew_degrees(result)
    if 0.4 <= abs(angle) <= 15:
        # straighten and read again: a straight image gives cleaner text and keeps table rows on one line
        img = img.rotate(angle, resample=Image.BICUBIC, expand=True, fillcolor=(255, 255, 255))
        result = _ocr_raw(img)
    return img, _to_segments(result)


def ocr_image(img: Image.Image) -> list[Segment]:
    return _to_segments(_ocr_raw(img))


def sharpness(img: Image.Image) -> float:
    """Variance of a Laplacian: low numbers mean a blurry photo."""
    g = np.asarray(ImageOps.grayscale(img).resize((1000, int(1000 * img.height / img.width)))).astype(np.float32)
    lap = (-4 * g[1:-1, 1:-1] + g[:-2, 1:-1] + g[2:, 1:-1] + g[1:-1, :-2] + g[1:-1, 2:])
    return float(lap.var())


def _save_page_image(doc_id: str, n: int, img: Image.Image) -> str:
    path = PAGES_DIR / f"{doc_id}_{n}.jpg"
    img.convert("RGB").save(path, "JPEG", quality=85)
    return str(path)


def read_document(path: Path, doc_id: str) -> ReadResult:
    ext = path.suffix.lower()
    if ext == ".pdf":
        return _read_pdf(path, doc_id)
    if ext in IMAGE_EXT:
        return _read_image(path, doc_id)
    raise UnreadableDocument("This file type is not supported. Please upload PDF, JPG or PNG files.")


def _read_image(path: Path, doc_id: str) -> ReadResult:
    try:
        img = Image.open(path)
        img = ImageOps.exif_transpose(img).convert("RGB")
    except Exception:
        raise UnreadableDocument("We couldn't open this image. Please upload a JPG or PNG photo.")
    if max(img.size) > 2000:
        img.thumbnail((2000, 2000))
    if min(img.size) < 300:
        raise UnreadableDocument("This image is too small to read. Please upload a larger photo.")
    sharp = sharpness(img)
    img, segs = ocr_page(img)
    page = Page(1, img.width, img.height, _save_page_image(doc_id, 1, img), segs, "ocr")
    return ReadResult("photo", [page], sharp, [img])


def _read_pdf(path: Path, doc_id: str) -> ReadResult:
    import pdfplumber
    import pypdfium2 as pdfium

    with _pdfium_lock:
        try:
            pdf = pdfium.PdfDocument(str(path))
        except Exception:
            raise UnreadableDocument("This PDF seems damaged or password-protected. Please export it again and re-upload.")
        try:
            rendered = [pdf[i].render(scale=PDF_SCALE).to_pil().convert("RGB") for i in range(min(len(pdf), MAX_PAGES_PER_DOC))]
        finally:
            pdf.close()
    pages, images, kind, sharp_vals = [], [], "pdf", []
    try:
        with pdfplumber.open(str(path)) as plumb:
            for i, img in enumerate(rendered):
                words = plumb.pages[i].extract_words(extra_attrs=["size"], keep_blank_chars=False, use_text_flow=False)
                segs = [Segment(w["text"], (w["x0"] * PDF_SCALE, w["top"] * PDF_SCALE, w["x1"] * PDF_SCALE, w["bottom"] * PDF_SCALE),
                                1.0, float(w.get("size", 0))) for w in words]
                source = "text"
                if sum(len(s.text) for s in segs) < 25:  # scanned page, no text layer
                    sharp_vals.append(sharpness(img))
                    img, segs = ocr_page(img)
                    source, kind = "ocr", "scan"
                pages.append(Page(i + 1, img.width, img.height, _save_page_image(doc_id, i + 1, img), segs, source))
                images.append(img)
    except Exception:
        raise UnreadableDocument("This PDF seems damaged or password-protected. Please export it again and re-upload.")
    if not pages:
        raise UnreadableDocument("This PDF has no pages.")
    return ReadResult(kind, pages, min(sharp_vals) if sharp_vals else None, images)


# --------------------------------------------------------------------------- layout helpers
@dataclass
class Line:
    page: int
    segments: list
    y: float

    @property
    def text(self) -> str:
        return " ".join(s.text for s in self.segments)

    @property
    def box(self):
        return (min(s.box[0] for s in self.segments), min(s.box[1] for s in self.segments),
                max(s.box[2] for s in self.segments), max(s.box[3] for s in self.segments))

    @property
    def size(self) -> float:
        return max(s.size for s in self.segments)

    @property
    def conf(self) -> float:
        return min(s.conf for s in self.segments)

    def cells(self, gap: float | None = None):
        """Split the line into cells where there is a wide horizontal gap."""
        if not self.segments:
            return []
        h = max(1.0, np.median([s.box[3] - s.box[1] for s in self.segments]))
        gap = gap or h * 2.2
        cells, cur = [], [self.segments[0]]
        for prev, s in zip(self.segments, self.segments[1:]):
            if s.box[0] - prev.box[2] > gap:
                cells.append(cur); cur = []
            cur.append(s)
        cells.append(cur)
        return cells


def group_lines(pages: list[Page]) -> list[Line]:
    lines: list[Line] = []
    for p in pages:
        segs = sorted(p.segments, key=lambda s: ((s.box[1] + s.box[3]) / 2, s.box[0]))
        page_lines: list[Line] = []
        for s in segs:
            cy, h = (s.box[1] + s.box[3]) / 2, s.box[3] - s.box[1]
            best = None
            for ln in page_lines[-6:]:
                ly0, ly1 = ln.box[1], ln.box[3]
                if ly0 - h * 0.25 <= cy <= ly1 + h * 0.25 and abs(cy - ln.y) < max(h, ly1 - ly0) * 0.6:
                    best = ln
            if best:
                best.segments.append(s)
            else:
                page_lines.append(Line(p.n, [s], cy))
        for ln in page_lines:
            ln.segments.sort(key=lambda s: s.box[0])
        lines.extend(page_lines)
    return lines
