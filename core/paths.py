"""
Resource Path Helper (Kiosk Edition - Ana Projedeki Ses Bankası ve AI Modellerini Paylaşır)
"""

import os
import sys


def get_resource_path(relative_path: str) -> str:
    kiosk_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    candidate = os.path.join(kiosk_root, relative_path)
    if os.path.exists(candidate):
        return candidate

    if getattr(sys, "frozen", False):
        exe_dir = os.path.dirname(sys.executable)
        exe_candidate = os.path.join(exe_dir, relative_path)
        if os.path.exists(exe_candidate):
            return exe_candidate

    if hasattr(sys, "_MEIPASS"):
        base_path = getattr(sys, "_MEIPASS")
        return os.path.join(base_path, relative_path)

    parent_root = os.path.dirname(kiosk_root)
    return os.path.join(parent_root, relative_path)
