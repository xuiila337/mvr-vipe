from __future__ import annotations
import base64
import io
from typing import Optional, Tuple

try:
    import fitz  # PyMuPDF
    from PIL import Image
    PDF_VIEW_AVAILABLE = True
except Exception:
    fitz = None
    Image = None
    PDF_VIEW_AVAILABLE = False


def get_page_count(pdf_path: str) -> int:
    if not PDF_VIEW_AVAILABLE or fitz is None:
        return 0
    doc = fitz.open(pdf_path)
    try:
        return int(doc.page_count)
    finally:
        doc.close()


def render_pdf_page_to_base64(pdf_path: str, page_index: int, zoom: float) -> Tuple[Optional[str], int, int]:
    """Рендерит PDF-страницу и возвращает (base64_png, width, height)."""
    if not PDF_VIEW_AVAILABLE or fitz is None or Image is None:
        return None, 0, 0
    
    doc = fitz.open(pdf_path)
    try:
        page = doc.load_page(page_index)
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode("ascii")
        
        return b64, pix.width, pix.height
    finally:
        doc.close()
