"""
Resource Path Helper (Kiosk Edition - Ana Projedeki Ses Bankası ve AI Modellerini Paylaşır)
"""

import os
import sys


def get_resource_path(relative_path: str) -> str:
    if hasattr(sys, "_MEIPASS"):
        base_path = getattr(sys, "_MEIPASS")
        return os.path.join(base_path, relative_path)

    kiosk_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    candidate = os.path.join(kiosk_root, relative_path)
    if os.path.exists(candidate):
        return candidate

    parent_root = os.path.dirname(kiosk_root)
    return os.path.join(parent_root, relative_path)
