"""
KIOSK EDITION - ÇELLO MODÜLÜ (Air Cello - Kiosk Nota Sütunu Arayüzü + Derin Sustain + Nota/Akor)
Kemandan ayrı, derin bas oktavda (-1 oktav) çalışan Kiosk Çello modülü.
"""

import math
from typing import List, Optional
import pygame

from core.audio_engine import AudioEngine
from core.hand_tracker import HandPhysicsState
from core.scale_quantizer import PlayMode, ScaleQuantizer
from ui.vfx_renderer import VFXRenderer


class AirCelloInstrument:
    NAME = "CELLO"

    def __init__(self, width: int = 1280, height: int = 720) -> None:
        self.width = width
        self.height = height
        self.current_note_name: str = "A2"
        self.sustain_energy: float = 0.0
        self.smooth_pitch_idx: float = 3.0

    def update_and_render(
        self,
        screen: pygame.Surface,
        active_hands: List[HandPhysicsState],
        audio: AudioEngine,
        quantizer: ScaleQuantizer,
        vfx: VFXRenderer,
        dt: float,
    ) -> None:
        left_hand: Optional[HandPhysicsState] = None
        right_hand: Optional[HandPhysicsState] = None

        for h in active_hands:
            if h.label == "Left" or h.palm_x < 0.48:
                left_hand = h
            else:
                right_hand = h

        if right_hand is None and left_hand is not None and len(active_hands) == 1:
            right_hand = left_hand

        pitch_hand = left_hand if left_hand is not None else right_hand
        norm_y = pitch_hand.palm_y if pitch_hand is not None else 0.5
        finger_shift = 0
        if pitch_hand is not None:
            ext = pitch_hand.finger_extended_mask
            finger_shift = 3 if ext[4] else (2 if ext[3] else (1 if ext[2] else 0))
            raw_idx = (1.0 - max(0.0, min(1.0, (norm_y - 0.18) / 0.60))) * 9.0 + finger_shift
            self.smooth_pitch_idx = 0.72 * self.smooth_pitch_idx + 0.28 * raw_idx

        note_idx = int(round(self.smooth_pitch_idx))
        freq, note_name, _ = quantizer.get_note_by_index(note_idx, octave_shift=-1)
        chord_label, chord_midis = quantizer.get_diatonic_chord_by_index(note_idx, octave_shift=-1)

        use_chord = (
            quantizer.play_mode == PlayMode.CHORD_ONLY
            or (quantizer.play_mode == PlayMode.HYBRID and pitch_hand is not None and pitch_hand.open_fingers >= 4)
        )
        self.current_note_name = f"Cello Akor {chord_label}" if use_chord else note_name

        bow_motion = 0.0
        if right_hand is not None:
            bow_motion = float(math.hypot(right_hand.vx, right_hand.vy))
        if left_hand is not None and left_hand is not right_hand:
            bow_motion = max(bow_motion, float(left_hand.speed * 0.65))

        if active_hands:
            if bow_motion > 0.055:
                self.sustain_energy = max(self.sustain_energy * 0.95, min(1.0, 0.45 + bow_motion / 1.40))
            else:
                self.sustain_energy = max(0.0, self.sustain_energy - dt * 0.52)
        else:
            self.sustain_energy = max(0.0, self.sustain_energy - dt * 1.2)

        if self.sustain_energy > 0.04:
            audio.update_continuous(
                active=True,
                freq=freq,
                volume=self.sustain_energy,
                timbre="cello",
                chord_midis=chord_midis if use_chord else None,
            )
            vfx.last_hit_note = self.current_note_name
        else:
            audio.update_continuous(active=False)

        ladder_x = 65
        top_y = int(self.height * 0.18)
        bot_y = int(self.height * 0.80)
        pygame.draw.line(screen, (255, 165, 60), (ladder_x, top_y), (ladder_x, bot_y), 5)

        marker_y = int(max(top_y, min(bot_y, norm_y * self.height)))
        pygame.draw.circle(screen, (255, 200, 65), (ladder_x, marker_y), 15)
        note_lbl = vfx.font_md.render(f"CELLO | {self.current_note_name} ({int(freq)} Hz)", True, (255, 210, 110))
        screen.blit(note_lbl, (ladder_x + 28, marker_y - 14))

        if right_hand is not None and len(right_hand.landmarks_px) > 8:
            rx, ry = right_hand.landmarks_px[8]
            lx = left_hand.landmarks_px[8][0] if (left_hand and len(left_hand.landmarks_px) > 8) else int(self.width * 0.35)
            ly = left_hand.landmarks_px[8][1] if (left_hand and len(left_hand.landmarks_px) > 8) else marker_y
            bow_thick = max(3, int(3 + self.sustain_energy * 11))
            bow_col = (255, 185, 65) if self.sustain_energy > 0.1 else (160, 120, 80)
            pygame.draw.line(screen, bow_col, (lx, ly), (rx, ry), bow_thick)

        bar_w = 360
        bar_x = self.width // 2 - bar_w // 2
        bar_y = int(self.height * 0.82)
        pygame.draw.rect(screen, (25, 35, 55), (bar_x, bar_y, bar_w, 22), border_radius=8)
        if self.sustain_energy > 0.02:
            pygame.draw.rect(screen, (255, 175, 55), (bar_x, bar_y, int(bar_w * self.sustain_energy), 22), border_radius=8)
        pygame.draw.rect(screen, (255, 195, 75), (bar_x, bar_y, bar_w, 22), 2, border_radius=8)
