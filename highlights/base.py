from __future__ import annotations

from abc import ABC, abstractmethod

from core.types import HighlightsMap, PdfText, ParseResult


class Highlighter(ABC):
    @abstractmethod
    def build(self, pdf_text: PdfText, result: ParseResult) -> HighlightsMap:
        raise NotImplementedError
