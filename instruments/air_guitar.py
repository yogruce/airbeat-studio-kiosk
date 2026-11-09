"""
KIOSK EDITION - GİTAR MODÜLÜ (Air Guitar - Kiosk Kutu Arayüzü + Solo Nota & Akor + Sustain)
Sol tarafta büyük Kiosk Akor/Perde seçim kutuları ve sağ tarafta yatay tel çizgileri yer alır.
Performans & Ses Güncellemeleri:
- [M] ile SOLO NOTA, AKOR ve HİBRİT modlarını destekler,
- El hareket ettikçe gitar sesini uzatır (sustain),
- Sol el parmaklarıyla solo nota geçişi yapılabilir.
"""

import time
from typing import List, Optional
import pygame

from core.audio_engine import AudioEngine
from core.hand_tracker import HandPhysicsState
from core.looper import LiveLooper
from core.scale_quantizer import PlayMode, ScaleQuantizer
from ui.vfx_renderer import VFXRenderer


class AirGuitarInstrument:
    NAME = "GITAR"

    def __init__(self, width: int = 1280, height: int = 720) -> None:
        self.width = width
        self.height = height
        self.selected_chord_idx: int = 0
        self.selected_note_idx: int = 4
        self.prev_right_y: Optional[float] = None
        self.last_strum_time: float = 0.0
        self.string_vibration: float = 0.0

    def update_and_render(
        self,
        screen: pygame.Surface,
        active_hands: List[HandPhysicsState],
        audio: AudioEngine,
        quantizer: ScaleQuantizer,
        vfx: VFXRenderer,
        looper: LiveLooper,
        dt: float,
    ) -> None:
        chords = quantizer.get_chords()
        n_chords = len(chords)
        self.string_vibration = max(0.0, self.string_vibration - dt * 3.0)

        left_hand: Optional[HandPhysicsState] = None
        right_hand: Optional[HandPhysicsState] = None

        for h in active_hands:
            if h.label == "Left" or h.palm_x < 0.45:
                left_hand = h
            else:
                right_hand = h

        if right_hand is None and left_hand is not None and len(active_hands) == 1:
            right_hand = left_hand

        fret_top = int(self.height * 0.20)
        fret_bot = int(self.height * 0.80)
        slot_h = (fret_bot - fret_top) // n_chords

        finger_offset = 0
        if left_hand is not None:
            rel_y = (left_hand.palm_y * self.height - fret_top) / max(1, (fret_bot - fret_top))
            self.selected_chord_idx = max(0, min(n_chords - 1, int(rel_y * n_chords)))
            ext = left_hand.finger_extended_mask
            finger_offset = 3 if ext[4] else (2 if ext[3] else (1 if ext[2] else 0))
            if left_hand.speed > 0.12:
                audio.extend_sustain_by_tag("guitar_", energy=0.75)

        chord_name, chord_notes = chords[self.selected_chord_idx]
        self.selected_note_idx = max(0, min(14, self.selected_chord_idx * 2 + finger_offset))
        _, solo_note_name, solo_midi = quantizer.get_note_by_index(self.selected_note_idx, octave_shift=1)

        # Sol Kiosk Perde Kutuları
        fret_x = 45
        fret_w = 210
        title_s = vfx.font_sm.render(f"SOL EL: PERDE ({solo_note_name})", True, (0, 230, 255))
        screen.blit(title_s, (fret_x, fret_top - 28))

        for i, (c_name, _) in enumerate(chords):
            ry = fret_top + i * slot_h
            rect = pygame.Rect(fret_x, ry + 4, fret_w, slot_h - 8)
            is_sel = i == self.selected_chord_idx
            col = (0, 220, 255) if is_sel else (45, 65, 95)
            pygame.draw.rect(screen, (15, 35, 60) if is_sel else (15, 20, 32), rect, border_radius=10)
            pygame.draw.rect(screen, col, rect, width=3 if is_sel else 1, border_radius=10)
            txt = vfx.font_md.render(f"{c_name}", True, (255, 255, 255) if is_sel else (150, 175, 205))
            screen.blit(txt, (rect.centerx - txt.get_width() // 2, rect.centery - txt.get_height() // 2))

        strum_y_norm = 0.58
        strum_y_px = int(self.height * strum_y_norm)
        strum_x1 = int(self.width * 0.34)
        strum_x2 = int(self.width * 0.88)

        now = time.perf_counter()
        if right_hand is not None:
            cur_y = right_hand.tip_y
            in_x_zone = 0.28 <= right_hand.tip_x <= 0.94
            if right_hand.speed > 0.15:
                audio.extend_sustain_by_tag("guitar_", energy=0.60)

            if self.prev_right_y is not None and in_x_zone and (now - self.last_strum_time) > 0.11:
                crossed_down = (self.prev_right_y < strum_y_norm <= cur_y) and right_hand.vy > 0.30
                crossed_up = (self.prev_right_y > strum_y_norm >= cur_y) and right_hand.vy < -0.30
                fast_strike_near = (
                    abs(cur_y - strum_y_norm) < 0.095
                    and (right_hand.is_downstroke_strike or any(fg.is_downstroke_strike for fg in right_hand.fingers[1:4]))
                )

                if crossed_down or crossed_up or fast_strike_near:
                    vel = float(min(1.0, max(0.52, max(abs(right_hand.vy), right_hand.speed) / 2.1)))
                    upstroke = crossed_up
                    sx = int(right_hand.tip_x * self.width)

                    play_solo = (
                        quantizer.play_mode == PlayMode.NOTE_ONLY
                        or (quantizer.play_mode == PlayMode.HYBRID and (right_hand.is_pinching or right_hand.open_fingers <= 2))
                    )
                    if play_solo:
                        audio.trigger_guitar_note(solo_midi, velocity=vel, pan=0.5)
                        looper.record_event(
                            "guitar_note",
                            {"midi_note": solo_midi, "velocity": vel, "px": sx, "py": strum_y_px, "note_name": solo_note_name},
                        )
                        vfx.spawn_hit_vfx(sx, strum_y_px, (0, 245, 255), intensity=vel, label=f"Solo {solo_note_name}")
                    else:
                        audio.trigger_guitar_chord(chord_notes, velocity=vel, upstroke=upstroke)
                        looper.record_event(
                            "guitar",
                            {
                                "chord_notes": chord_notes,
                                "velocity": vel,
                                "upstroke": upstroke,
                                "px": sx,
                                "py": strum_y_px,
                                "chord_name": chord_name,
                            },
                        )
                        vfx.spawn_hit_vfx(sx, strum_y_px, (255, 95, 210), intensity=vel, label=f"Akor {chord_name}")
                    self.last_strum_time = now
                    self.string_vibration = 1.0

            self.prev_right_y = cur_y
        else:
            self.prev_right_y = None

        strum_lbl = vfx.font_sm.render(
            f"SAG EL PENA BOLGESI (Akor: {chord_name} | Solo: {solo_note_name} | Mod: {quantizer.current_play_mode_name})",
            True,
            (255, 160, 230),
        )
        screen.blit(strum_lbl, (strum_x1, strum_y_px - 52))

        for s_idx in range(-2, 4):
            offset_y = s_idx * 10
            vib = int(
                (1.0 if s_idx % 2 == 0 else -1.0)
                * self.string_vibration
                * 11.0
                * (1.0 if int(now * 60) % 2 == 0 else -1.0)
            )
            sy = strum_y_px + offset_y + vib
            s_col = (255, 230, 110) if self.string_vibration > 0.2 else (255, 90, 200)
            pygame.draw.line(screen, s_col, (strum_x1, sy), (strum_x2, sy), 3 if s_idx == 0 else 2)
