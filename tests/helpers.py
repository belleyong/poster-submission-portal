import io

from PIL import Image
from pypdf import PdfWriter

MM_TO_PT = 72 / 25.4


def make_pdf(w_mm: float, h_mm: float, pages: int = 1) -> bytes:
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=w_mm * MM_TO_PT, height=h_mm * MM_TO_PT)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def make_image(w_px: int, h_px: int, fmt: str = "PNG") -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w_px, h_px), "white").save(buf, format=fmt)
    return buf.getvalue()
