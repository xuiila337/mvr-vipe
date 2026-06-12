from __future__ import annotations

from core.types import HighlightRect, HighlightsMap, PdfText, ParseResult
from highlights.base import Highlighter
from highlights.psp_impl import build_highlights_psp


class PspHighlighter(Highlighter):
    def build(self, pdf_text: PdfText, result: ParseResult) -> HighlightsMap:
        raw = build_highlights_psp(pdf_text.pdf_path, pdf_text.raw_text, result.actual_text)
        out: HighlightsMap = {}
        for pi, rects in raw.items():
            out[pi] = [HighlightRect(x0, top, x1, bottom) for (x0, top, x1, bottom) in rects]
        return out
