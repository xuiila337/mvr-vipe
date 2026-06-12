from __future__ import annotations

from core.types import ParseResult, PdfText
from parsers.base import Parser

from .mvr_impl import format_output_with_debug


class MvrParser(Parser):
    def parse(self, pdf_text: PdfText) -> ParseResult:
        actual, dbg = format_output_with_debug(pdf_text.raw_text, pdf_text.page_texts, pdf_text.pdf_path)
        return ParseResult(doc_type="MVR", actual_text=actual, debug_log=dbg)
