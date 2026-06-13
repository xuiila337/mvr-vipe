from __future__ import annotations
import os
import sys
import webview
from core.pipeline import Engine
from ui.webview_api import Api


def run_ui(engine: Engine) -> None:
    api = Api(engine)
    
    # Определяем путь к HTML
    if getattr(sys, 'frozen', False):
        # Скомпилированный exe
        base_dir = sys._MEIPASS
    else:
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    
    html_path = os.path.join(base_dir, 'ui', 'web', 'index.html')
    
    window = webview.create_window(
        "MVR / PSP Check — beta 1.0",
        url=html_path,
        js_api=api,
        width=1420,
        height=840,
        min_size=(1100, 650),
        background_color='#0D0D14'
    )
    
    api.set_window(window)
    webview.start()
