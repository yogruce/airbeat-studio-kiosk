"""
Otomatik Güncelleme Servisi (Auto-Updater) — AirBeat Studio Kiosk Edition
-------------------------------------------------------------------------
Hem .exe (PyInstaller) hem de Python kaynak kodu kurulumlarında:
1. Açılışta ve Ayarlar menüsünden GitHub'daki son commit'i (`yogruce/airbeat-studio-kiosk`) kontrol eder.
2. Yeni bir revize/güncelleme yayınlandığında GitHub üzerinden güncel dosyaları indirir,
   eski dosyaların üzerine yazar ve uygulamayı otomatik olarak yeniden başlatır.
"""

from __future__ import annotations

import io
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Optional

GITHUB_REPO = "yogruce/airbeat-studio-kiosk"
GITHUB_COMMITS_URL = f"https://api.github.com/repos/{GITHUB_REPO}/commits/main"
GITHUB_ZIP_URL = f"https://github.com/{GITHUB_REPO}/archive/refs/heads/main.zip"


def get_app_root() -> Path:
    """Uygulamanın kurulu olduğu ana klasörü döndürür (EXE veya Python kaynak dizini)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


class AutoUpdater:
    def __init__(self, app_dir: Optional[Path] = None) -> None:
        self.app_dir = Path(app_dir) if app_dir else get_app_root()
        self.version_file = self.app_dir / ".version"
        self.status_text: str = "Kontrol ediliyor..."
        self.has_update: bool = False
        self.is_updating: bool = False
        self.local_commit: str = self._read_local_commit()
        self.remote_commit: str = ""
        self.remote_message: str = ""
        self._lock = threading.Lock()

    def _has_git(self) -> bool:
        return (self.app_dir / ".git").is_dir() and (shutil.which("git") is not None)

    def _read_local_commit(self) -> str:
        if self.version_file.exists():
            try:
                data = json.loads(self.version_file.read_text(encoding="utf-8"))
                c = str(data.get("commit", "")).strip()
                if c:
                    return c[:7]
            except Exception:
                pass

        if self._has_git():
            try:
                res = subprocess.run(
                    ["git", "rev-parse", "--short", "HEAD"],
                    cwd=str(self.app_dir),
                    capture_output=True,
                    text=True,
                    timeout=4,
                    check=False,
                )
                if res.returncode == 0 and res.stdout.strip():
                    return res.stdout.strip()[:7]
            except Exception:
                pass

        return "v1.0"

    def save_version(self, commit_sha: str, message: str = "") -> None:
        try:
            self.local_commit = commit_sha[:7]
            self.version_file.write_text(
                json.dumps(
                    {
                        "commit": self.local_commit,
                        "message": message,
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                    },
                    indent=2,
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
        except Exception:
            pass

    def check_for_updates(self) -> Dict[str, Any]:
        """GitHub API üzerinden en son commit hash'ini sorgular."""
        with self._lock:
            self.local_commit = self._read_local_commit()

        remote_sha = ""
        remote_msg = ""
        try:
            req = urllib.request.Request(
                GITHUB_COMMITS_URL,
                headers={
                    "User-Agent": "AirBeatStudioKiosk-Updater",
                    "Accept": "application/vnd.github.v3+json",
                },
            )
            with urllib.request.urlopen(req, timeout=6) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    remote_sha = str(data.get("sha") or "")[:7]
                    commit_obj = data.get("commit", {})
                    remote_msg = str(commit_obj.get("message") or "").splitlines()[0]
        except Exception as e:
            with self._lock:
                self.status_text = f"Surum: {self.local_commit} (Cevrimdisi)"
            return {"ok": False, "has_update": False, "error": str(e)}

        with self._lock:
            self.remote_commit = remote_sha
            self.remote_message = remote_msg
            if remote_sha and self.local_commit == "v1.0":
                # İlk kez çalışıyorsa mevcut sürümü kaydet ve yine de güncelleme varsa çekebilsin
                self.has_update = True
                self.status_text = f"Yeni Guncelleme Var! ({remote_sha})"
            elif remote_sha and remote_sha.lower() != self.local_commit.lower():
                self.has_update = True
                self.status_text = f"Yeni Guncelleme Var! ({self.local_commit} -> {remote_sha})"
            else:
                self.has_update = False
                self.status_text = f"Guncel ({self.local_commit})"

        return {
            "ok": True,
            "has_update": self.has_update,
            "local_commit": self.local_commit,
            "remote_commit": self.remote_commit,
            "remote_message": self.remote_message,
        }

    def apply_update(self, on_progress: Optional[Callable[[str], None]] = None) -> bool:
        """GitHub'dan son sürümü indirir ve mevcut kurulumun üzerine yazar."""
        with self._lock:
            if self.is_updating:
                return False
            self.is_updating = True
            self.status_text = "Guncelleme indiriliyor..."

        if on_progress:
            on_progress("GitHub'dan guncelleme indiriliyor...")

        try:
            if not self.remote_commit:
                self.check_for_updates()

            # 1. Eğer .git klasörü varsa ve taşınabilir EXE değilse git pull dene
            git_ok = False
            if self._has_git() and not getattr(sys, "frozen", False):
                try:
                    subprocess.run(
                        ["git", "fetch", "origin", "main"],
                        cwd=str(self.app_dir),
                        capture_output=True,
                        timeout=15,
                        check=False,
                    )
                    res = subprocess.run(
                        ["git", "reset", "--hard", "origin/main"],
                        cwd=str(self.app_dir),
                        capture_output=True,
                        text=True,
                        timeout=20,
                        check=False,
                    )
                    if res.returncode == 0:
                        git_ok = True
                except Exception:
                    git_ok = False

            # 2. ZIP İndirme (Git olmasa da, EXE olsa da %100 çalışır)
            if not git_ok:
                req = urllib.request.Request(
                    GITHUB_ZIP_URL,
                    headers={"User-Agent": "AirBeatStudioKiosk-Updater"},
                )
                with urllib.request.urlopen(req, timeout=45) as resp:
                    zip_bytes = resp.read()

                if on_progress:
                    on_progress("Dosyalar cikartiliyor ve guncelleniyor...")

                zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
                prefix = ""
                for name in zf.namelist():
                    if "/" in name:
                        prefix = name.split("/", 1)[0] + "/"
                        break

                skip_first = {".git", ".venv", "venv", "build", "dist", "__pycache__"}
                for member in zf.infolist():
                    if member.is_dir():
                        continue
                    rel_path = member.filename
                    if prefix and rel_path.startswith(prefix):
                        rel_path = rel_path[len(prefix) :]
                    if not rel_path:
                        continue

                    first_part = rel_path.split("/")[0]
                    if first_part in skip_first:
                        continue

                    target_file = self.app_dir / rel_path
                    target_file.parent.mkdir(parents=True, exist_ok=True)
                    content = zf.read(member.filename)
                    try:
                        target_file.write_bytes(content)
                    except Exception:
                        pass

            if self.remote_commit:
                self.save_version(self.remote_commit, self.remote_message)

            with self._lock:
                self.has_update = False
                self.is_updating = False
                self.status_text = f"Guncellendi ({self.local_commit})! Yeniden baslatiliyor..."

            return True
        except Exception as e:
            with self._lock:
                self.is_updating = False
                self.status_text = f"Guncelleme Hatasi: {str(e)[:28]}"
            return False

    def check_and_auto_update_async(self, on_restart_needed: Callable[[], None]) -> None:
        """Arka planda güncellemeyi kontrol eder, yeni sürüm varsa otomatik indirip yeniden başlatmayı tetikler."""

        def _worker() -> None:
            info = self.check_for_updates()
            if info.get("has_update"):
                ok = self.apply_update()
                if ok:
                    time.sleep(0.8)
                    on_restart_needed()

        threading.Thread(target=_worker, daemon=True, name="AutoUpdateWorker").start()


def restart_application() -> None:
    """Uygulamayı güncellenmiş dosyalarla yeniden başlatır."""
    try:
        if getattr(sys, "frozen", False):
            subprocess.Popen([sys.executable] + sys.argv[1:], cwd=str(get_app_root()))
        else:
            subprocess.Popen([sys.executable] + sys.argv, cwd=str(get_app_root()))
    except Exception:
        pass
    os._exit(42)
