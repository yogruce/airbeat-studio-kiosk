"""
KIOSK EDITION - PİYANO MODÜLÜ (Air Piano - Kiosk Holografik Ped Arayüzü + 10 Parmak Çoklu Tuş + Sustain)
Kiosk ekran düzenini (yüzen geniş neon tuş kutuları) korur, ancak:
- 12 geniş tuşa çıkarılmıştır,
- Her iki elin 5 parmağının tamamı (10 parmak) aynı anda çoklu tuşa (polifonik) basabilir,
- Parmak tuşun içinde kaldığı/hareket ettiği sürece ses uzar (sustain),
- [M] ile hem SOLO NOTA hem AKOR çalabilir.
"""

import time
from typing import Dict, List, Tuple
import pygame

from core.audio_engine import AudioEngine
from core.hand_tracker import HandPhysicsState
from core.looper import LiveLooper
from core.scale_quantizer import PlayMode, ScaleQuantizer
from ui.vfx_renderer import VFXRenderer, VisualMode


class AirPianoInstrument:
    NAME = "PIYANO"

    def __init__(self, width: int = 1280, height: int = 720) -> None:
        self.width = width
        self.height = height
        self.num_keys = 12
        self.key_flashes: List[float] = [0.0] * self.num_keys
        self.finger_in_key: Dict[Tuple[str, int, int], float] = {}

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
        now = time.perf_counter()
        margin_x = int(self.width * 0.05)
        total_w = self.width - 2 * margin_x
        key_w = total_w // self.num_keys
        key_top = int(self.height * 0.46)
        key_h = int(self.height * 0.30)

        for k in range(self.num_keys):
            self.key_flashes[k] = max(0.0, self.key_flashes[k] - dt * 3.5)
            kx = margin_x + k * key_w
            rect = pygame.Rect(kx + 3, key_top, key_w - 6, key_h)
            freq, note_name, _ = quantizer.get_note_by_index(k, octave_shift=0)
            pan = 0.15 + 0.70 * (k / max(1, self.num_keys - 1))

            for hand in active_hands:
                for fg in hand.fingers:
                    fk = (hand.label, fg.finger_index, k)
                    inside = rect.collidepoint(fg.px, fg.py)
                    was_inside = fk in self.finger_in_key
                    last_t = self.finger_in_key.get(fk, 0.0)

                    if inside:
                        if was_inside and (now - last_t) > 0.05:
                            audio.extend_sustain_by_tag(f"piano_{k}", energy=0.72)
                            self.key_flashes[k] = max(self.key_flashes[k], 0.40)

                        entering_down = (not was_inside) and (fg.vy > 0.16 or hand.vy > 0.16 or fg.speed > 0.28)
                        striking = (fg.is_downstroke_strike or hand.is_downstroke_strike) and (now - last_t > 0.13)

                        if (entering_down or striking) and (now - last_t > 0.11):
                            vel = float(min(1.0, max(0.50, max(fg.vy, hand.vy, fg.speed) / 2.0)))
                            play_chord = (
                                quantizer.play_mode == PlayMode.CHORD_ONLY
                                or (quantizer.play_mode == PlayMode.HYBRID and k < 4 and fg.finger_index in (0, 1))
                            )
                            if play_chord:
                                c_label, c_midis = quantizer.get_diatonic_chord_by_index(k, octave_shift=0)
                                audio.trigger_piano_chord(c_midis, velocity=vel, pan=pan, key_id=k)
                                looper.record_event(
                                    "piano_chord",
                                    {"midi_notes": c_midis, "velocity": vel, "pan": pan, "px": rect.centerx, "py": rect.centery, "note_name": c_label},
                                )
                                vfx.spawn_hit_vfx(rect.centerx, rect.top + 30, (255, 195, 70), intensity=vel, label=f"Akor {c_label}")
                            else:
                                audio.trigger_piano_note(freq, velocity=vel, pan=pan, key_id=k)
                                looper.record_event(
                                    "piano",
                                    {"freq": freq, "velocity": vel, "pan": pan, "px": rect.centerx, "py": rect.centery, "note_name": note_name},
                                )
                                vfx.spawn_hit_vfx(rect.centerx, rect.top + 30, (0, 235, 255), intensity=vel, label=note_name)

                            self.key_flashes[k] = 1.0
                            self.finger_in_key[fk] = now
                        elif not was_inside:
                            self.finger_in_key[fk] = last_t
                    else:
                        if was_inside:
                            del self.finger_in_key[fk]

            flash = self.key_flashes[k]
            if vfx.visual_mode != VisualMode.PERFORMANCE_MINIMAL:
                ksurf = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
                alpha = int(55 + 145 * flash)
                col = (0, 230, 255, alpha) if flash > 0.1 else (30, 45, 75, 115)
                pygame.draw.rect(ksurf, col, (0, 0, rect.width, rect.height), border_radius=12)
                screen.blit(ksurf, rect.topleft)

            b_col = (255, 255, 255) if flash > 0.25 else (0, 200, 245)
            pygame.draw.rect(screen, b_col, rect, width=3 if flash > 0.2 else 2, border_radius=12)

            lbl = vfx.font_md.render(note_name, True, (255, 255, 255))
            screen.blit(lbl, (rect.centerx - lbl.get_width() // 2, rect.bottom - 42))
