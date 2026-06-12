from __future__ import annotations

from typing import Optional, Tuple

# PDF render
try:
    import fitz  # PyMuPDF
    from PIL import Image, ImageTk
    PDF_VIEW_AVAILABLE = True
except Exception:
    fitz = None
    Image = None
    ImageTk = None
    PDF_VIEW_AVAILABLE = False

import tkinter as tk


def get_page_count(pdf_path: str) -> int:
    if not PDF_VIEW_AVAILABLE or fitz is None:
        return 0
    doc = fitz.open(pdf_path)  # type: ignore[union-attr]
    try:
        return int(doc.page_count)
    finally:
        doc.close()


def render_pdf_page_to_photo(pdf_path: str, page_index: int, zoom: float) -> Tuple[Optional[tk.PhotoImage], float, float]:
    if not PDF_VIEW_AVAILABLE or fitz is None or Image is None or ImageTk is None:
        return None, 0.0, 0.0

    doc = fitz.open(pdf_path)  # type: ignore[union-attr]
    try:
        page = doc.load_page(page_index)
        mat = fitz.Matrix(zoom, zoom)  # type: ignore[union-attr]
        pix = page.get_pixmap(matrix=mat, alpha=False)
        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        photo = ImageTk.PhotoImage(img)
        return photo, float(pix.width), float(pix.height)
    finally:
        doc.close()
