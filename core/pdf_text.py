from __future__ import annotations

from typing import List

import pdfplumber

from .types import PdfText


def extract_text_from_pdf_pages(pdf_path: str) -> List[str]:
    page_texts: List[str] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            page_texts.append(page.extract_text() or "")
    return page_texts


def join_pages(page_texts: List[str]) -> str:
    return "\n".join(page_texts)


def extract_pdf_text(pdf_path: str) -> PdfText:
    pts = extract_text_from_pdf_pages(pdf_path)
    raw = join_pages(pts)
    return PdfText(pdf_path=pdf_path, page_texts=pts, raw_text=raw)
