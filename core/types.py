from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional

DocType = Literal["MVR", "PSP", "UNKNOWN"]


@dataclass(frozen=True)
class HighlightRect:
    """A rectangle in PDF coordinate space (pdfplumber word boxes)."""
    x0: float
    top: float
    x1: float
    bottom: float


HighlightsMap = Dict[int, List[HighlightRect]]  # page_index -> rects


@dataclass
class Issue:
    level: Literal["info", "warning", "error"]
    code: str
    message: str
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ParseResult:
    doc_type: DocType
    actual_text: str
    debug_log: Dict[str, Any] = field(default_factory=dict)
    highlights: HighlightsMap = field(default_factory=dict)
    issues: List[Issue] = field(default_factory=list)


@dataclass(frozen=True)
class PdfText:
    pdf_path: str
    page_texts: List[str]
    raw_text: str
