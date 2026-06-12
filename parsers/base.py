from __future__ import annotations

from abc import ABC, abstractmethod

from core.types import PdfText, ParseResult


class Parser(ABC):
    @abstractmethod
    def parse(self, pdf_text: PdfText) -> ParseResult:
        raise NotImplementedError
