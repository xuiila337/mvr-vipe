from __future__ import annotations

from core.pipeline import Engine

from parsers.mvr import MvrParser
from parsers.psp import PspParser

from highlights.mvr import MvrHighlighter
from highlights.psp import PspHighlighter

from ui.main_window import run_ui


def main() -> None:
    engine = Engine(
        parsers={
            "MVR": MvrParser(),
            "PSP": PspParser(),
        },
        highlighters={
            "MVR": MvrHighlighter(),
            "PSP": PspHighlighter(),
        },
    )
    run_ui(engine)


if __name__ == "__main__":
    main()
