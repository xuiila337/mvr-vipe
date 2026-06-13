# core/update_checker.py
from __future__ import annotations

import json
import os
import sys
import shutil
import subprocess
import tempfile
import urllib.request
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
        raise FileNotFoundError(
            "Компонент обновления (updater.exe) не найден.\nПожалуйста, скачайте обновление вручную."
        )

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
