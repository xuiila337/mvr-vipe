import base64
import io
import json
import os
from datetime import datetime
from typing import Any, Dict, Optional

from core.bundle import save_debug_bundle
from core.pipeline import Engine
from core.types import PdfText, ParseResult


class Api:
    """pywebview JS API — все методы доступны из JS как window.pywebview.api.method()"""
    
    def __init__(self, engine: Engine):
        self.engine = engine
        self.pdf_path = ""
        self.original_filename = ""
        self.pdf_text: Optional[PdfText] = None
        self.result: Optional[ParseResult] = None
        self.page_count = 0
        self._window = None  # будет установлено после создания окна
    
    def set_window(self, window):
        self._window = window
    
    def choose_pdf(self) -> dict:
        """Открывает file dialog, парсит PDF, возвращает результат."""
        import webview
        file_types = ('PDF Files (*.pdf)',)
        paths = self._window.create_file_dialog(
            webview.OPEN_DIALOG,
            file_types=file_types
        )
        if not paths:
            return {"ok": False}
        
        return self._process_pdf(paths[0])
    
    def process_dropped_pdf_bytes(self, base64_data: str, filename: str) -> dict:
        """Декодирует PDF из base64, сохраняет во временный файл и парсит."""
        try:
            import base64
            import tempfile
            
            pdf_bytes = base64.b64decode(base64_data)
            
            # Создаем временный файл с оригинальным расширением .pdf
            fd, temp_path = tempfile.mkstemp(suffix=".pdf", prefix="dropped_")
            try:
                with os.fdopen(fd, 'wb') as tmp:
                    tmp.write(pdf_bytes)
            except Exception as e:
                return {"ok": False, "error": f"Failed to write temp file: {e}"}
            
            self.original_filename = filename
            
            # Обрабатываем
            return self._process_pdf(temp_path)
        except Exception as e:
            return {"ok": False, "error": str(e)}
    
    def _process_pdf(self, path: str) -> dict:
        try:
            pdf_text, result = self.engine.run(path)
            self.pdf_path = path
            self.original_filename = os.path.basename(path)
            self.pdf_text = pdf_text
            self.result = result
            
            from ui.pdf_viewer import get_page_count
            self.page_count = get_page_count(path)
            if self.page_count <= 0:
                self.page_count = len(pdf_text.page_texts)
            
            return {
                "ok": True,
                "actual_text": result.actual_text or "",
                "doc_type": result.doc_type,
                "page_count": self.page_count,
                "debug_log": json.dumps(result.debug_log or {}, ensure_ascii=False, indent=2),
                "issues": [{"level": i.level, "message": i.message} for i in (result.issues or [])]
            }
        except Exception as e:
            return {"ok": False, "error": str(e)}
    
    def render_page(self, page_index: int, zoom: float) -> dict:
        """Рендерит PDF-страницу в base64 PNG."""
        if not self.pdf_path:
            return {"ok": False}
        
        from ui.pdf_viewer import render_pdf_page_to_base64
        b64, w, h = render_pdf_page_to_base64(self.pdf_path, page_index, zoom)
        if not b64:
            return {"ok": False}
        
        return {"ok": True, "base64_png": b64, "width": w, "height": h}
    
    def get_highlights(self, page_index: int, zoom: float) -> dict:
        """Возвращает координаты highlight-прямоугольников."""
        if not self.result:
            return {"rects": []}
        
        rects = self.result.highlights.get(page_index, [])
        return {
            "rects": [
                {"x0": r.x0 * zoom, "top": r.top * zoom,
                 "x1": r.x1 * zoom, "bottom": r.bottom * zoom}
                for r in rects
            ]
        }
    
    def save_txt(self, content: str) -> dict:
        """Сохранить actual output в .txt."""
        import webview
        path = self._window.create_file_dialog(
            webview.SAVE_DIALOG,
            file_types=('Text Files (*.txt)',)
        )
        if not path:
            return {"ok": False}
        
        save_path = path if isinstance(path, str) else path[0]
        with open(save_path, "w", encoding="utf-8") as f:
            f.write(content + "\n")
        return {"ok": True, "path": save_path}
    
    def copy_clipboard(self, text: str) -> dict:
        """Копирует текст в буфер обмена."""
        import subprocess
        process = subprocess.Popen(['clip'], stdin=subprocess.PIPE)
        process.communicate(text.encode('utf-16-le'))
        return {"ok": True}
    
    def save_bundle(self, expected_text: str) -> dict:
        """Сохранить debug bundle ZIP."""
        if not self.pdf_path or not self.pdf_text or not self.result:
            return {"ok": False, "error": "Load a PDF first"}
        
        import webview
        pdf_base = os.path.splitext(self.original_filename)[0] if self.original_filename else "dropped_file"
        stamp = datetime.now().strftime("%Y-%m-%d__%H%M")
        doc = self.result.doc_type
        default_name = f"{doc}__{pdf_base}__{stamp}.zip"
        
        path = self._window.create_file_dialog(
            webview.SAVE_DIALOG,
            file_types=('ZIP Files (*.zip)',),
            save_filename=default_name
        )
        if not path:
            return {"ok": False}
        
        save_path = path if isinstance(path, str) else path[0]
        save_debug_bundle(save_path, self.pdf_text, self.result, expected_text)
        return {"ok": True, "path": save_path}
    
    def check_updates(self) -> dict:
        """Проверяет обновления (синхронно)."""
        from core.update_checker import get_latest_release_info, is_version_newer, CURRENT_VERSION
        info = get_latest_release_info()
        if not info:
            return {"ok": False, "message": "Не удалось проверить обновления"}
        
        if is_version_newer(CURRENT_VERSION, info["version"]):
            return {
                "ok": True,
                "has_update": True,
                "version": info["version"],
                "download_url": info["download_url"],
                "notes": info.get("release_notes", "")
            }
        
        return {"ok": True, "has_update": False, "message": "У вас последняя версия"}

    def download_and_install_update(self, url: str, version: str) -> dict:
        """Скачивает zip-архив обновления и запускает updater.exe."""
        try:
            import urllib.request
            import tempfile
            from core.update_checker import launch_updater_and_exit
            
            temp_zip = os.path.join(tempfile.gettempdir(), f"mvr_psp_update_{version}.zip")
            
            req = urllib.request.Request(url, headers={"User-Agent": "MVR-PSP-Check-AutoUpdater"})
            with urllib.request.urlopen(req) as response:
                with open(temp_zip, 'wb') as f:
                    f.write(response.read())
            
            launch_updater_and_exit(temp_zip)
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}
