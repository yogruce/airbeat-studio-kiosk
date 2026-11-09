"""
KIOSK EDITION - SAKSAFON MODÜLÜ (Air Sax - Kiosk Dikey Tuş Hologramı + Kesilmeyen Legato Sustain)
Kiosk dikey 8-tuş hologram arayüzünü korur, ancak:
- Titreme yapmayan yumuşatılmış nota geçişi (smooth_note_idx),
- El hareketiyle kesintisiz uzayan ses (Sustain Reservoir),
- [M] ile hem SOLO NOTA hem AKOR çalma desteği eklendi.
"""

from typing import List
import pygame

from core.audio_engine import AudioEngine
from core.hand_tracker import HandPhysicsState
from core.scale_quantizer import PlayMode, ScaleQuantizer
from ui.vfx_renderer import VFXRenderer


class AirSaxInstrument:
    NAME = "SAKSAFON"

    def __init__(self, width: int = 1280, height: int = 720) -> None:
        self.width = width
        self.height = height
        self.sustain_energy: float = 0.0
        self.smooth_note_idx: float = 4.0

    def update_and_render(
        self,
        screen: pygame.Surface,
        active_hands: List[HandPhysicsState],
        audio: AudioEngine,
        quantizer: ScaleQuantizer,
        vfx: VFXRenderer,
        dt: float,
    ) -> None:
        total_fingers = sum(h.open_fingers for h in active_hands)

        if active_hands:
            primary = active_hands[0]
            target_idx = (1.0 - max(0.0, min(1.0, (primary.palm_y - 0.18) / 0.60))) * 7.0 + (total_fingers % 4) * 0.7
            self.smooth_note_idx = 0.78 * self.smooth_note_idx + 0.22 * target_idx

            in_wind_zone = any(0.18 <= h.palm_x <= 0.82 and 0.14 <= h.palm_y <= 0.86 for h in active_hands)
            motion = max(h.speed for h in active_hands)
            breath_power = max(audio.mic_rms, min(1.0, 0.62 + motion * 0.45) if in_wind_zone else 0.0)

            if breath_power > 0.10:
                self.sustain_energy = max(self.sustain_energy * 0.95, breath_power)
            else:
                self.sustain_energy = max(0.0, self.sustain_energy - dt * 0.55)
        else:
            self.sustain_energy = max(0.0, self.sustain_energy - dt * 1.3)

        base_idx = int(round(self.smooth_note_idx))
        freq, note_name, _ = quantizer.get_note_by_index(base_idx, octave_shift=1)
        chord_label, chord_midis = quantizer.get_diatonic_chord_by_index(base_idx, octave_shift=1)

        use_chord = (
            quantizer.play_mode == PlayMode.CHORD_ONLY
            or (quantizer.play_mode == PlayMode.HYBRID and total_fingers >= 8)
        )
        disp_name = f"Sax Akor {chord_label}" if use_chord else note_name

        if self.sustain_energy > 0.04:
            audio.update_continuous(
                active=True,
                freq=freq,
                volume=self.sustain_energy,
                timbre="sax",
                chord_midis=chord_midis if use_chord else None,
            )
            vfx.last_hit_note = disp_name
        else:
            audio.update_continuous(active=False)

        cx = self.width // 2
        top_y = int(self.height * 0.20)
        bot_y = int(self.height * 0.76)
        pygame.draw.line(screen, (255, 200, 60), (cx, top_y), (cx, bot_y), 8)

        for k_idx in range(8):
            ky = top_y + int((bot_y - top_y) * (k_idx / 7.0))
            is_active_key = k_idx == (base_idx % 8)
            col = (255, 245, 130) if is_active_key else (120, 95, 40)
            pygame.draw.circle(screen, col, (cx, ky), 18 if is_active_key else 12)
            pygame.draw.circle(screen, (255, 255, 255), (cx, ky), 18 if is_active_key else 12, 2)

        lbl = vfx.font_md.render(
            f"SAKSAFON: {disp_name} | Acik Parmak: {total_fingers} | Sustain: %{int(self.sustain_energy*100)}",
            True,
            (255, 225, 95),
        )
        screen.blit(lbl, (cx - lbl.get_width() // 2, bot_y + 22))
