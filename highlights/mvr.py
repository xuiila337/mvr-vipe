from __future__ import annotations

from core.types import HighlightRect, HighlightsMap, PdfText, ParseResult
from highlights.base import Highlighter
from highlights.mvr_impl import build_highlights_mvr


class MvrHighlighter(Highlighter):
    def build(self, pdf_text: PdfText, result: ParseResult) -> HighlightsMap:
        raw = build_highlights_mvr(pdf_text.pdf_path, pdf_text.raw_text)
        out: HighlightsMap = {}
        for pi, rects in raw.items():
            out[pi] = [HighlightRect(x0, top, x1, bottom) for (x0, top, x1, bottom) in rects]
        return out
