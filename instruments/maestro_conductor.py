"""
7. ORKESTRA ŞEFİ MODÜLÜ (Maestro / Conductor Mode - Gerçek Baton Tutuşu & Kesintisiz Senfoni)
- SAĞ EL (Conductor Baton / Şef Bageti): Sağ elin ucundan parlayan altın bir Orkestra Şefi Bageti uzanır.
  Her aşağı vuruş (Downbeat) senfonik akor geçişini ve Timpani vuruşunu tetikler.
  El havada hareket ettiği sürece senfoni orkestrası ASLA kesilmez, nefes alır ve uzar!
- SOL EL (Crescendo & Katmanlar): Sol el yükseldikçe Yaylıların (Strings) üzerine
  Fransız Kornoları (Brass) ve Timpani davulları eklenir.
"""

from collections import deque
import math
import time
from typing import Deque, List, Optional
import pygame

from core.audio_engine import AudioEngine
from core.hand_tracker import HandPhysicsState
from core.looper import LiveLooper
from core.scale_quantizer import ScaleQuantizer
from ui.vfx_renderer import VFXRenderer


class MaestroConductorInstrument:
    NAME = "MAESTRO"

    def __init__(self, width: int = 1280, height: int = 720) -> None:
        self.width = width
        self.height = height
        self.beat_index: int = 0
        self.beat_times: Deque[float] = deque(maxlen=5)
        self.current_bpm: int = 110
        self.crescendo_level: float = 0.55
        self.sustain_energy: float = 0.0
        self.last_beat_time: float = 0.0

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
        chords = quantizer.get_chords()

        left_hand: Optional[HandPhysicsState] = None
        right_hand: Optional[HandPhysicsState] = None

        for h in active_hands:
            if h.label == "Left" or h.palm_x < 0.46:
                left_hand = h
            else:
                right_hand = h

        if right_hand is None and left_hand is not None and len(active_hands) == 1:
            right_hand = left_hand

        # 1. Sol El Yüksekliği -> Crescendo
        if left_hand is not None:
            target_cresc = float(max(0.20, min(1.0, 1.15 - left_hand.palm_y * 1.25)))
            self.crescendo_level = 0.85 * self.crescendo_level + 0.15 * target_cresc

        # 2. Sağ El Baget (Baton) Çizimi, Vuruşu & Kesintisiz Senfoni Sustain
        active_chord_name, active_chord_notes = chords[self.beat_index % len(chords)]

        if right_hand is not None:
            if len(right_hand.landmarks_px) > 9:
                px_p, py_p = right_hand.landmarks_px[9]
                st_x, st_y = right_hand.stick_tip_px
                pygame.draw.line(screen, (255, 225, 95), (px_p, py_p), (st_x, st_y), 6)
                pygame.draw.line(screen, (255, 255, 255), (px_p, py_p), (st_x, st_y), 2)
                pygame.draw.circle(screen, (255, 240, 120), (st_x, st_y), 11)

            if right_hand.is_downstroke_strike and (now - self.last_beat_time) > 0.22:
                if self.beat_times:
                    interval = now - self.beat_times[-1]
                    if 0.22 <= interval <= 2.0:
                        inst_bpm = int(60.0 / interval)
                        self.current_bpm = int(0.6 * self.current_bpm + 0.4 * inst_bpm)

                self.beat_times.append(now)
                self.last_beat_time = now
                self.beat_index = (self.beat_index + 1) % len(chords)
                active_chord_name, active_chord_notes = chords[self.beat_index]

                vel = float(min(1.0, max(0.60, right_hand.strike_velocity * (0.5 + 0.6 * self.crescendo_level))))
                audio.trigger_maestro_beat(active_chord_notes, velocity=vel, richness=self.crescendo_level)
                bx, by = right_hand.stick_tip_px
                looper.record_event(
                    "maestro",
                    {
                        "chord_notes": active_chord_notes,
                        "velocity": vel,
                        "richness": self.crescendo_level,
                        "px": bx,
                        "py": by,
                        "chord_name": active_chord_name,
                    },
                )
                vfx.spawn_hit_vfx(
                    bx,
                    by,
                    (255, 215, 65),
                    intensity=vel,
                    label=f"Beat {(self.beat_index % 4) + 1} ({active_chord_name})",
                )
                self.sustain_energy = 1.0

            baton_motion = min(1.0, max(right_hand.speed, right_hand.stick_speed) / 1.1)
            if baton_motion > 0.05:
                target_s = max(0.45, baton_motion) * (0.35 + 0.65 * self.crescendo_level)
                self.sustain_energy = max(self.sustain_energy * 0.96, target_s)
            else:
                self.sustain_energy = max(0.0, self.sustain_energy - dt * 0.45)
        else:
            self.sustain_energy = max(0.0, self.sustain_energy - dt * 1.1)

        if self.sustain_energy > 0.04:
            root_midi = active_chord_notes[0]
            root_freq = quantizer.midi_to_freq(root_midi)
            audio.update_continuous(
                active=True,
                freq=root_freq,
                volume=self.sustain_energy,
                timbre="orchestra",
                richness=self.crescendo_level,
                chord_midis=active_chord_notes,
            )
        else:
            audio.update_continuous(active=False)

        # 3. Senfonik Orkestra Yarım Daire Görselleştirmesi
        cx = self.width // 2
        cy = int(self.height * 0.72)
        sections = [
            ("STRINGS (Yaylilar)", math.pi * 0.82, math.pi * 0.58, (0, 225, 255), True),
            ("BRASS & HORNS (Kornolar)", math.pi * 0.56, math.pi * 0.44, (255, 200, 50), self.crescendo_level > 0.35),
            ("TIMPANI & PERC (Davullar)", math.pi * 0.42, math.pi * 0.18, (255, 80, 150), self.crescendo_level > 0.55),
        ]

        arc_r = 285
        for sec_name, a_start, a_end, col, is_engaged in sections:
            mid_a = (a_start + a_end) * 0.5
            lx = int(cx + math.cos(mid_a) * (arc_r + 35))
            ly = int(cy - math.sin(mid_a) * (arc_r + 35))
            draw_col = col if is_engaged else (70, 80, 100)

            pts = []
            for step in range(14):
                ang = a_start + (a_end - a_start) * (step / 13.0)
                pts.append((int(cx + math.cos(ang) * arc_r), int(cy - math.sin(ang) * arc_r)))
            pygame.draw.lines(screen, draw_col, False, pts, 7 if is_engaged else 2)

            s_txt = vfx.font_sm.render(sec_name, True, draw_col)
            screen.blit(s_txt, (lx - s_txt.get_width() // 2, ly - 12))

        if self.crescendo_level < 0.35:
            dyn_label = "p (Pianissimo - Yumusak Yaylilar)"
        elif self.crescendo_level < 0.65:
            dyn_label = "mf (Mezzo-Forte - Yaylilar + Korno)"
        else:
            dyn_label = "ff (FORTISSIMO - Tam Senfoni + Timpani!)"

        banner = vfx.font_md.render(
            f"TEMPO: {self.current_bpm} BPM  |  AKOR: {active_chord_name}  |  DINAMIK: {dyn_label}",
            True,
            (255, 230, 110),
        )
        screen.blit(banner, (cx - banner.get_width() // 2, int(self.height * 0.14)))
