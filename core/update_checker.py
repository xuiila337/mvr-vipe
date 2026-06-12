# core/update_checker.py
from __future__ import annotations

import json
import os
import sys
import shutil
import subprocess
import tempfile
import threading
import urllib.request
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Optional, Dict, Any

CURRENT_VERSION = "1.0.0"
GITHUB_REPO = "xuiila337/mvr-vipe"


def get_latest_release_info() -> Optional[Dict[str, Any]]:
    """
    Fetch the latest release info from the GitHub API.
    Returns a dict with version, download_url, and release_notes, or None.
    """
    url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "MVR-PSP-Check-AutoUpdater"}
        )
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode("utf-8"))
            
            tag_name = data.get("tag_name", "").strip("v")
            assets = data.get("assets", [])
            
            # Find a zip asset (or fallback to source code zip)
            download_url = None
            for asset in assets:
                name = asset.get("name", "").lower()
                if name.endswith(".zip"):
                    download_url = asset.get("browser_download_url")
                    break
                    
            if not download_url:
                download_url = data.get("zipball_url")
                
            return {
                "version": tag_name,
                "download_url": download_url,
                "release_notes": data.get("body", "")
            }
    except Exception as e:
        print(f"[UpdateChecker] Failed to check for updates: {e}")
        return None


def is_version_newer(current: str, latest: str) -> bool:
    """Compare two version strings (e.g. 1.0.0 and 1.0.1)."""
    try:
        c_parts = [int(x) for x in current.split(".")]
        l_parts = [int(x) for x in latest.split(".")]
        # Pad with zeros if parts count differ
        max_len = max(len(c_parts), len(l_parts))
        c_parts += [0] * (max_len - len(c_parts))
        l_parts += [0] * (max_len - len(l_parts))
        return l_parts > c_parts
    except Exception:
        # Fallback to simple string comparison
        return latest != current


class DownloadProgressWindow:
    def __init__(self, parent: tk.Tk, url: str, dest_path: str, on_complete):
        self.parent = parent
        self.url = url
        self.dest_path = dest_path
        self.on_complete = on_complete
        
        self.win = tk.Toplevel(parent)
        self.win.title("Обновление...")
        self.win.geometry("400x150")
        self.win.resizable(False, False)
        self.win.configure(bg="#131316")
        self.win.transient(parent)
        self.win.grab_set()
        
        # Center the window
        self.win.update_idletasks()
        w = self.win.winfo_width()
        h = self.win.winfo_height()
        xp = parent.winfo_x() + (parent.winfo_width() - w) // 2
        yp = parent.winfo_y() + (parent.winfo_height() - h) // 2
        self.win.geometry(f"+{xp}+{yp}")
        
        # Styling
        lbl = tk.Label(
            self.win,
            text="Скачивание новой версии программы...",
            fg="#F1F5F9",
            bg="#131316",
            font=("Segoe UI", 11)
        )
        lbl.pack(pady=(20, 10))
        
        self.progress = ttk.Progressbar(self.win, length=300, mode="determinate")
        self.progress.pack(pady=10)
        
        self.status_lbl = tk.Label(
            self.win,
            text="0%",
            fg="#94A3B8",
            bg="#131316",
            font=("Segoe UI", 9)
        )
        self.status_lbl.pack()
        
        # Start download thread
        threading.Thread(target=self.download, daemon=True).start()

    def download(self):
        try:
            req = urllib.request.Request(self.url, headers={"User-Agent": "MVR-PSP-Check-AutoUpdater"})
            with urllib.request.urlopen(req) as response:
                total_size = int(response.info().get('Content-Length', 0))
                downloaded = 0
                block_size = 1024 * 8
                
                with open(self.dest_path, 'wb') as f:
                    while True:
                        block = response.read(block_size)
                        if not block:
                            break
                        f.write(block)
                        downloaded += len(block)
                        
                        if total_size > 0:
                            percent = int(downloaded * 100 / total_size)
                            self.parent.after(0, self.update_progress, percent)
                            
                self.parent.after(0, self.complete)
        except Exception as e:
            self.parent.after(0, lambda: messagebox.showerror("Ошибка", f"Не удалось скачать обновление:\n{e}"))
            self.parent.after(0, self.win.destroy)

    def update_progress(self, percent: int):
        self.progress['value'] = percent
        self.status_lbl.config(text=f"{percent}%")

    def complete(self):
        self.win.destroy()
        self.on_complete()


def launch_updater_and_exit(zip_path: str):
    """
    Locates updater.exe, copies it to temp directory to avoid locking,
    launches it, and exits the main application.
    """
    app_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
    
    # Try different locations for updater
    updater_candidates = [
        os.path.join(app_dir, "updater.exe"),
        os.path.join(app_dir, "..", "updater", "updater.exe"),
        os.path.join(app_dir, "updater", "updater.exe"),
    ]
    
    updater_exe = None
    for cand in updater_candidates:
        if os.path.isfile(cand):
            updater_exe = cand
            break
            
    if not updater_exe:
        messagebox.showerror(
            "Ошибка", 
            "Компонент обновления (updater.exe) не найден.\nПожалуйста, скачайте обновление вручную."
        )
        return

    try:
        # Copy updater to temp to prevent it locking target directory files
        temp_dir = tempfile.gettempdir()
        temp_updater = os.path.join(temp_dir, f"updater_{os.getpid()}.exe")
        shutil.copy2(updater_exe, temp_updater)
        
        # Parameters for updater:
        # --zip: path to downloaded update zip
        # --target: directory of the current app to overwrite
        # --launch: executable to run after update (our own current executable)
        # --pid: our pid to wait for exit
        args = [
            temp_updater,
            "--zip", zip_path,
            "--target", app_dir,
            "--launch", sys.executable if sys.executable.endswith(".exe") else os.path.join(app_dir, "MVR_PSP_Check.exe"),
            "--pid", str(os.getpid())
        ]
        
        # Start updater in a separate detached process
        subprocess.Popen(args, close_fds=True)
        sys.exit(0)
    except Exception as e:
        messagebox.showerror("Ошибка", f"Не удалось запустить обновление:\n{e}")


def check_for_updates_async(root: tk.Tk, silent: bool = True):
    """Run update check in a background thread."""
    def run():
        info = get_latest_release_info()
        if not info:
            if not silent:
                root.after(0, lambda: messagebox.showinfo("Обновление", "Не удалось проверить наличие обновлений."))
            return
            
        latest_version = info["version"]
        if is_version_newer(CURRENT_VERSION, latest_version):
            root.after(0, lambda: prompt_update(root, info))
        else:
            if not silent:
                root.after(0, lambda: messagebox.showinfo("Обновление", "У вас установлена последняя версия программы."))
                
    threading.Thread(target=run, daemon=True).start()


def prompt_update(root: tk.Tk, info: Dict[str, Any]):
    latest_version = info["version"]
    notes = info["release_notes"]
    msg = f"Доступна новая версия {latest_version}!\n\nЧто нового:\n{notes}\n\nХотите обновить программу сейчас?"
    
    if messagebox.askyesno("Доступно обновление", msg):
        temp_zip = os.path.join(tempfile.gettempdir(), f"mvr_psp_update_{latest_version}.zip")
        DownloadProgressWindow(
            root, 
            info["download_url"], 
            temp_zip, 
            on_complete=lambda: launch_updater_and_exit(temp_zip)
        )
