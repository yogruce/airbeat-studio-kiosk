"""
1. BATERİ MODÜLÜ (Air Drums)
Ekranın alt ve üst kısımlarında yarı saydam 5 vurmalı bölge:
- Sol Üst: HI-HAT
- Sağ Üst: CRASH ZİLİ
- Sol Alt: SNARE (Trampet)
- Merkez Alt: KICK (Bas Davul)
- Sağ Alt: FLOOR TOM
Algılama: Parmak ucu / baget ucu ilgili bölgeye yüksek aşağı hızla (vy) girdiğinde
veya bölge içinde vuruş (downstroke strike) yaptığında hız şiddetine (velocity) göre tetiklenir.
"""

from dataclasses import dataclass
import time
from typing import Dict, List, Tuple
import pygame

from core.audio_engine import AudioEngine
from core.hand_tracker import HandPhysicsState
from core.looper import LiveLooper
from ui.vfx_renderer import VFXRenderer, VisualMode


@dataclass
class DrumPad:
    name: str
    drum_key: str
    norm_x: float
    norm_y: float
    radius_px: int
    color: Tuple[int, int, int]
    pan: float
    flash_timer: float = 0.0


class AirDrumsInstrument:
    NAME = "BATERI"

    def __init__(self, width: int = 1280, height: int = 720) -> None:
        self.width = width
        self.height = height
        self.pads: List[DrumPad] = [
            DrumPad("HI-HAT", "hihat", 0.20, 0.34, 78, (0, 235, 255), 0.20),
            DrumPad("SNARE",  "snare", 0.31, 0.68, 86, (255, 70, 165), 0.35),
            DrumPad("KICK",   "kick",  0.50, 0.77, 94, (255, 165, 30), 0.50),
            DrumPad("TOM",    "tom",   0.69, 0.68, 86, (80, 250, 140), 0.65),
            DrumPad("CRASH",  "crash", 0.80, 0.34, 78, (255, 235, 65), 0.80),
        ]
        # Her elin hangi pedin içinde olduğunu takip eder (bölgeye hızlı giriş vuruşunu yakalamak için)
        self.hand_inside: Dict[Tuple[str, int], float] = {}

    def trigger_kick_pedal(self, audio: AudioEngine, vfx: VFXRenderer, looper: LiveLooper) -> None:
        kick_pad = self.pads[2]
        px = int(kick_pad.norm_x * self.width)
        py = int(kick_pad.norm_y * self.height)
        audio.trigger_drum("kick", velocity=0.95, pan=0.5)
        looper.record_event(
            "drum",
            {"drum_key": "kick", "velocity": 0.95, "pan": 0.5, "px": px, "py": py, "color": kick_pad.color, "name": "KICK"},
        )
        vfx.spawn_hit_vfx(px, py, kick_pad.color, intensity=0.95, label="KICK")
        kick_pad.flash_timer = 1.0

    def update_and_render(
        self,
        screen: pygame.Surface,
        active_hands: List[HandPhysicsState],
        audio: AudioEngine,
        vfx: VFXRenderer,
        looper: LiveLooper,
        dt: float,
    ) -> None:
        now = time.perf_counter()

        for pad_idx, pad in enumerate(self.pads):
            px = int(pad.norm_x * self.width)
            py = int(pad.norm_y * self.height)
            pad.flash_timer = max(0.0, pad.flash_timer - dt * 4.5)

            for hand in active_hands:
                if len(hand.landmarks_px) <= 8:
                    continue
                tx, ty = hand.landmarks_px[8]
                dist = ((tx - px) ** 2 + (ty - py) ** 2) ** 0.5
                key = (hand.label, pad_idx)
                was_inside = key in self.hand_inside
                last_hit = self.hand_inside.get(key, 0.0)

                if dist <= pad.radius_px * 1.12:
                    # Tetikleme koşulu:
                    # A) Pedin dışından içine giriş yapması VEYA
                    # B) Pedin içindeyken aşağı hareket / vuruş yapması
                    entering_pad = (not was_inside) and (hand.vy > 0.12 or hand.speed > 0.28)
                    striking_inside = (hand.is_downstroke_strike or hand.vy > 0.55) and ((now - last_hit) > 0.12)

                    if (entering_pad or striking_inside) and ((now - last_hit) > 0.11):
                        vel = float(min(1.0, max(0.45, max(hand.vy, hand.speed) / 2.4)))
                        audio.trigger_drum(pad.drum_key, velocity=vel, pan=pad.pan)
                        looper.record_event(
                            "drum",
                            {"drum_key": pad.drum_key, "velocity": vel, "pan": pad.pan, "px": px, "py": py, "color": pad.color, "name": pad.name},
                        )
                        vfx.spawn_hit_vfx(px, py, pad.color, intensity=vel, label=pad.name)
                        pad.flash_timer = 1.0
                        self.hand_inside[key] = now
                    elif not was_inside:
                        self.hand_inside[key] = last_hit
                else:
                    if was_inside:
                        del self.hand_inside[key]

            # Ped Çizimi
            r = int(pad.radius_px * (1.0 + 0.14 * pad.flash_timer))
            if vfx.visual_mode != VisualMode.PERFORMANCE_MINIMAL:
                pad_surf = pygame.Surface((r * 2 + 8, r * 2 + 8), pygame.SRCALPHA)
                fill_alpha = int(45 + 135 * pad.flash_timer)
                pygame.draw.circle(
                    pad_surf,
                    (pad.color[0], pad.color[1], pad.color[2], fill_alpha),
                    (r + 4, r + 4),
                    r,
                )
                screen.blit(pad_surf, (px - r - 4, py - r - 4))

            border_col = (255, 255, 255) if pad.flash_timer > 0.3 else pad.color
            pygame.draw.circle(screen, border_col, (px, py), r, 4 if pad.flash_timer > 0.2 else 3)
            pygame.draw.circle(screen, pad.color, (px, py), int(r * 0.65), 1)

            lbl = vfx.font_md.render(pad.name, True, (255, 255, 255))
            screen.blit(lbl, (px - lbl.get_width() // 2, py - lbl.get_height() // 2))
