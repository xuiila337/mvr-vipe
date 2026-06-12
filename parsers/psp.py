from __future__ import annotations

from core.types import ParseResult, PdfText
from parsers.base import Parser

from .psp_impl import parse_psp_with_debug


class PspParser(Parser):
    def parse(self, pdf_text: PdfText) -> ParseResult:
        actual, dbg = parse_psp_with_debug(pdf_text.raw_text)
        return ParseResult(doc_type="PSP", actual_text=actual, debug_log=dbg)
