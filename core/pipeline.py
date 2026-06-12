from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Tuple

from .detect import detect_doc_type
from .pdf_text import extract_pdf_text
from .types import DocType, Issue, ParseResult, PdfText

from parsers.base import Parser
from highlights.base import Highlighter


@dataclass
class Engine:
    """
    The application core:
      PDF -> extracted text -> doc detect -> parser -> highlights
    UI should only call Engine.run() and render ParseResult.
    """
    parsers: Dict[DocType, Parser]
    highlighters: Dict[DocType, Highlighter]

    def run(self, pdf_path: str) -> Tuple[PdfText, ParseResult]:
        pdf_text = extract_pdf_text(pdf_path)

        if not (pdf_text.raw_text or "").strip():
            res = ParseResult(
                doc_type="UNKNOWN",
                actual_text="",
                debug_log={"error": "No extractable text (scan?)"},
                highlights={},
                issues=[Issue("error", "NO_TEXT", "В PDF нет извлекаемого текста. Возможно, это скан — нужен OCR.")]
            )
            return pdf_text, res

        doc_type: DocType = detect_doc_type(pdf_text.raw_text)
        parser = self.parsers.get(doc_type)

        if parser is None:
            res = ParseResult(
                doc_type="UNKNOWN",
                actual_text="",
                debug_log={"detected_doc_type": doc_type},
                highlights={},
                issues=[Issue("error", "UNKNOWN_DOC", f"Не удалось распознать тип документа: {doc_type}")]
            )
            return pdf_text, res

        # IMPORTANT: keep debug log generation always ON (needed for debug bundle)
        res = parser.parse(pdf_text)

        highlighter = self.highlighters.get(res.doc_type)
        if highlighter is not None:
            try:
                res.highlights = highlighter.build(pdf_text, res)
            except Exception as e:
                res.issues.append(Issue("warning", "HIGHLIGHTS_FAILED", "Подсветка не построена", {"err": str(e)}))

        return pdf_text, res
