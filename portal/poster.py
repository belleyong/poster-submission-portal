"""Checks that an uploaded poster file is A1 (594 x 841 mm, portrait or landscape).

PDFs are measured from the page box, so the physical size is exact.
Raster images (PNG/JPEG) carry no reliable physical size, so they must have
the A1 aspect ratio and enough pixels to print at the minimum DPI.
"""

import io
from dataclasses import dataclass, field

from PIL import Image, UnidentifiedImageError
from pypdf import PdfReader
from pypdf.errors import PdfReadError

A1_MM = (594.0, 841.0)
A1_RATIO = A1_MM[1] / A1_MM[0]  # ~1.4158 (ISO 216 rounds to whole mm)
MM_PER_INCH = 25.4
PT_PER_INCH = 72.0
RATIO_TOLERANCE = 0.01  # 1% for raster images

ALLOWED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg"}

Image.MAX_IMAGE_PIXELS = 300_000_000  # A1 at 600 DPI is ~280 MP


@dataclass
class PosterResult:
    ok: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    details: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"ok": self.ok, "errors": self.errors, "warnings": self.warnings, "details": self.details}


def _fmt_mm(w: float, h: float) -> str:
    return f"{w:.0f} x {h:.0f} mm"


def _nearest_iso_size(w_mm: float, h_mm: float) -> str | None:
    short, long_ = sorted((w_mm, h_mm))
    sizes = {"A0": (841, 1189), "A1": (594, 841), "A2": (420, 594), "A3": (297, 420), "A4": (210, 297)}
    for name, (s, l) in sizes.items():
        if abs(short - s) <= 10 and abs(long_ - l) <= 10:
            return name
    return None


def _size_hint(w_mm: float, h_mm: float) -> str:
    nearest = _nearest_iso_size(w_mm, h_mm)
    if nearest and nearest != "A1":
        return f" It looks like {nearest}; re-export the poster at A1 (594 x 841 mm)."
    return " Set your document size to A1 (594 x 841 mm) and export again."


def check_pdf(data: bytes, tolerance_mm: float) -> PosterResult:
    try:
        reader = PdfReader(io.BytesIO(data))
        pages = reader.pages
        if len(pages) == 0:
            return PosterResult(False, ["This PDF has no pages."])
    except (PdfReadError, ValueError, OSError):
        return PosterResult(False, ["This file couldn't be read as a PDF. Try exporting it again."])

    if reader.is_encrypted:
        return PosterResult(False, ["This PDF is password-protected. Export an unprotected copy."])

    warnings = []
    if len(pages) > 1:
        return PosterResult(False, [f"Your PDF has {len(pages)} pages. The poster must be a single A1 page."])

    page = pages[0]
    box = page.cropbox or page.mediabox
    user_unit = float(page.get("/UserUnit", 1) or 1)
    w_pt, h_pt = float(box.width) * user_unit, float(box.height) * user_unit
    if (page.rotation or 0) % 180 == 90:
        w_pt, h_pt = h_pt, w_pt

    w_mm = w_pt / PT_PER_INCH * MM_PER_INCH
    h_mm = h_pt / PT_PER_INCH * MM_PER_INCH
    short, long_ = sorted((w_mm, h_mm))
    orientation = "portrait" if h_mm >= w_mm else "landscape"
    details = {"type": "pdf", "width_mm": round(w_mm, 1), "height_mm": round(h_mm, 1),
               "orientation": orientation, "pages": len(pages)}

    if abs(short - A1_MM[0]) > tolerance_mm or abs(long_ - A1_MM[1]) > tolerance_mm:
        return PosterResult(False, [f"Your poster is {_fmt_mm(w_mm, h_mm)}, not A1." + _size_hint(w_mm, h_mm)],
                            warnings, details)

    return PosterResult(True, [], warnings, details)


def check_image(data: bytes, min_dpi: int) -> PosterResult:
    try:
        with Image.open(io.BytesIO(data)) as img:
            img.verify()
        with Image.open(io.BytesIO(data)) as img:
            w_px, h_px = img.size
            fmt = (img.format or "").lower()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
        return PosterResult(False, ["This image couldn't be opened. Upload a PDF, PNG or JPEG."])

    short, long_ = sorted((w_px, h_px))
    ratio = long_ / short
    orientation = "portrait" if h_px >= w_px else "landscape"
    effective_dpi = short / (A1_MM[0] / MM_PER_INCH)
    need_short = round(A1_MM[0] / MM_PER_INCH * min_dpi)
    need_long = round(A1_MM[1] / MM_PER_INCH * min_dpi)
    details = {"type": fmt, "width_px": w_px, "height_px": h_px, "orientation": orientation,
               "print_dpi_at_a1": round(effective_dpi)}

    errors = []
    if abs(ratio - A1_RATIO) / A1_RATIO > RATIO_TOLERANCE:
        errors.append(
            f"Your image is {w_px} x {h_px} px, which isn't A1 proportions (1 : 1.414). "
            "Set your document size to A1 (594 x 841 mm) and export again."
        )
    if effective_dpi < min_dpi:
        errors.append(
            f"Your image is too low-resolution to print at A1 ({round(effective_dpi)} DPI). "
            f"Export at least {need_short} x {need_long} px ({min_dpi} DPI), or upload a PDF."
        )

    warnings = []
    if not errors and fmt == "jpeg":
        warnings.append("JPEG accepted. A PDF export usually prints text more sharply.")

    return PosterResult(not errors, errors, warnings, details)


def check_poster(filename: str, data: bytes, config) -> PosterResult:
    name = (filename or "").lower()
    ext = "." + name.rsplit(".", 1)[-1] if "." in name else ""
    if ext not in ALLOWED_EXTENSIONS:
        return PosterResult(False, ["Upload your poster as a PDF, PNG or JPEG file."])

    if len(data) > config.max_upload_mb * 1024 * 1024:
        return PosterResult(False, [f"This file is over {config.max_upload_mb} MB. Compress it or export a smaller PDF."])

    if ext == ".pdf" or data[:5] == b"%PDF-":
        return check_pdf(data, config.a1_tolerance_mm)
    return check_image(data, config.min_image_dpi)
