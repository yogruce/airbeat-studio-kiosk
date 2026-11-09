"""
AirBeat Studio (Kiosk Edition) — Taşınabilir EXE Bootstrapper
-------------------------------------------------------------
PyInstaller ile derlendiğinde bile, klasördeki güncel `main.py`, `core/`, `instruments/`
ve `ui/` dosyalarını doğrudan çalıştırır. Böylece `AutoUpdater` GitHub'dan yeni bir
revize indirdiğinde, kullanıcının yeni EXE indirmesine gerek kalmadan yapılan tüm
kod ve ses revizeleri anında aktif olur!
"""

import os
import runpy
import sys

# PyInstaller'ın tüm kütüphaneleri (cv2, mediapipe, pygame, numpy, sounddevice, scipy)
# EXE içerisine dahil etmesi için açık importlar:
import cv2  # noqa: F401
import mediapipe  # noqa: F401
from mediapipe.tasks import python as mp_python  # noqa: F401
from mediapipe.tasks.python import vision as mp_vision  # noqa: F401
import numpy  # noqa: F401
import pygame  # noqa: F401
import scipy  # noqa: F401
from scipy import signal  # noqa: F401
import sounddevice  # noqa: F401


def main() -> None:
    if getattr(sys, "frozen", False):
        app_dir = os.path.dirname(os.path.abspath(sys.executable))
    else:
        app_dir = os.path.dirname(os.path.abspath(__file__))

    os.chdir(app_dir)
    # Класördeki güncel kaynak dosyalarının (_internal içindeki eski kopyalardan önce) yüklenmesini sağla
    if app_dir in sys.path:
        sys.path.remove(app_dir)
    sys.path.insert(0, app_dir)

    external_main = os.path.join(app_dir, "main.py")
    if os.path.exists(external_main):
        runpy.run_path(external_main, run_name="__main__")
    else:
        import main as bundled_main
        app = bundled_main.AirBeatStudioApp()
        app.run()


if __name__ == "__main__":
    main()
