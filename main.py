"""
AirBeat Studio (Air Orchestra) - Gerçek Enstrüman Tutuşu & Polifonik PC Müzik Oyunu
-------------------------------------------------------------------------------
Kamera karşısında gerçek enstrüman tutuyormuş gibi (Air Guitar, Air Drums, 10-Parmak Piyano,
Omuzda Keman, Gövde Önünde Dikey Çello, Saksafon ve Orkestra Şefi) çalmanızı sağlayan
düşük gecikmeli masaüstü oyun motoru.

Kısayol Tuşları (veya Ekran Üstü El Hover / Fare Tıklama Kapsülleri):
- [1] Bateri (Air Drums - 7 Parça Stüdyo Seti + Sanal Bagetler + [SPACE] Kick Pedalı)
- [2] Gitar (Air Guitar - Çapraz Gitar Sapı + Solo Nota & Akor + Sustain)
- [3] Piyano (Air Piano - 16 Tuş Geniş Klavye + 10 Parmak Çoklu Basım Polifoni + Sustain)
- [4] Keman (Air Violin - Sol Omuz Tutuşu + Sağ El Yay + Kesilmeyen Uzayan Ses)
- [5] Çello (Air Cello - Gövde Önü Dikey Çello + Derin Bas Yay + Kesilmeyen Ses)
- [6] Saksafon (Air Sax - Göğüs/Ağız Tutuşu + 6 Perde Parmak Tuşları + Legato Ses)
- [7] Orkestra Şefi (Maestro - Sağ El Baton + Sol El Crescendo Senfoni)
- [M] ÇALMA MODU DEĞİŞTİR: SOLO NOTA (Melody) <-> AKOR (Chords) <-> HİBRİT (Nota + Akor)
- [S] AYARLAR EKRANI (Kamera, Hoparlör/Kulaklık Seçimi, Ses Testi, RTX/Görünüm Modu, Hassasiyet)
- [V] Görsel / Performans Modu Değiştir
- [G] Gam Kilidi (Scale Quantization) Değiştir
- [L] 4-Bar Live Looper Kayıt Aç/Kapat   |   [C] Looper Temizle
- [F] Tam Ekran (Fullscreen)             |   [ESC] Çıkış
"""

import time
from typing import Dict, List, Tuple
import cv2
import numpy as np
import pygame

from core.audio_engine import AudioEngine
from core.hand_tracker import HandTracker
from core.looper import LiveLooper
from core.scale_quantizer import ScaleQuantizer
from core.updater import AutoUpdater, restart_application
from instruments.air_cello import AirCelloInstrument
from instruments.air_drums import AirDrumsInstrument
from instruments.air_guitar import AirGuitarInstrument
from instruments.air_piano import AirPianoInstrument
from instruments.air_sax import AirSaxInstrument
from instruments.air_violin import AirViolinInstrument
from instruments.maestro_conductor import MaestroConductorInstrument
from ui.vfx_renderer import VFXRenderer


class AirBeatStudioApp:
    WIDTH = 1280
    HEIGHT = 720

    def __init__(self) -> None:
        pygame.init()
        pygame.display.set_caption("AirBeat Studio — Real Posture Air Instrument & Maestro Game")
        self.screen = pygame.display.set_mode((self.WIDTH, self.HEIGHT), pygame.DOUBLEBUF)
        self.clock = pygame.time.Clock()
        self.is_fullscreen = False
        self.show_settings = False

        # Kamera Başlatma
        self.camera_index = 0
        self.camera_status = "Baglaniyor..."
        self.cap = None
        self._open_camera(self.camera_index)

        # Çekirdek Motorlar
        self.audio = AudioEngine()
        self.tracker = HandTracker(width=self.WIDTH, height=self.HEIGHT)
        self.quantizer = ScaleQuantizer()
        self.looper = LiveLooper(loop_duration=8.0)
        self.vfx = VFXRenderer(width=self.WIDTH, height=self.HEIGHT)

        # 7 Ayrı Gerçek Tutuşlu Enstrüman Modülü (Keman ve Çello ayrı!)
        self.drums = AirDrumsInstrument(self.WIDTH, self.HEIGHT)
        self.guitar = AirGuitarInstrument(self.WIDTH, self.HEIGHT)
        self.piano = AirPianoInstrument(self.WIDTH, self.HEIGHT)
        self.violin = AirViolinInstrument(self.WIDTH, self.HEIGHT)
        self.cello = AirCelloInstrument(self.WIDTH, self.HEIGHT)
        self.sax = AirSaxInstrument(self.WIDTH, self.HEIGHT)
        self.maestro = MaestroConductorInstrument(self.WIDTH, self.HEIGHT)

        self.instrument_names = [
            self.drums.NAME,
            self.guitar.NAME,
            self.piano.NAME,
            self.violin.NAME,
            self.cello.NAME,
            self.sax.NAME,
            self.maestro.NAME,
        ]
        self.current_inst_idx: int = 0
        self.last_hover_switch: float = 0.0
        self.capsule_rects: List[Tuple[pygame.Rect, int]] = []
        self.settings_buttons: Dict[str, pygame.Rect] = {}

        # Otomatik Güncelleyici (Açılışta GitHub'dan yeni revize varsa otomatik çeker)
        self.updater = AutoUpdater()
        self.restart_requested: bool = False
        self.updater.check_and_auto_update_async(self._on_auto_update_ready)

    def _on_auto_update_ready(self) -> None:
        self.restart_requested = True

    def trigger_manual_update(self) -> None:
        if self.updater.is_updating:
            return
        import threading

        def _job() -> None:
            info = self.updater.check_for_updates()
            if info.get("has_update"):
                if self.updater.apply_update():
                    time.sleep(0.8)
                    self.restart_requested = True

        threading.Thread(target=_job, daemon=True).start()

    def _open_camera(self, cam_idx: int) -> None:
        if self.cap is not None:
            try:
                self.cap.release()
            except Exception:
                pass

        cap = cv2.VideoCapture(cam_idx)
        ok, test_frame = False, None
        for _ in range(8):
            ok, test_frame = cap.read()
            if ok and test_frame is not None and test_frame.mean() > 15.0:
                break
            time.sleep(0.04)

        if not ok or test_frame is None or test_frame.mean() < 3.0:
            cap.release()
            cap = cv2.VideoCapture(cam_idx, cv2.CAP_DSHOW)
            for _ in range(8):
                ok, test_frame = cap.read()
                if ok and test_frame is not None and test_frame.mean() > 15.0:
                    break
                time.sleep(0.04)

        if ok and test_frame is not None and test_frame.mean() >= 1.0:
            self.cap = cap
            h, w = test_frame.shape[:2]
            self.camera_status = f"Aktif ({w}x{h})"
        else:
            self.cap = cap
            self.camera_status = "Kamera Sinyali Yok"

    def cycle_camera(self) -> None:
        for next_idx in ((self.camera_index + 1) % 3, 0):
            test_cap = cv2.VideoCapture(next_idx)
            ok, frm = test_cap.read()
            test_cap.release()
            if ok and frm is not None:
                self.camera_index = next_idx
                self._open_camera(self.camera_index)
                return
        self._open_camera(0)

    def switch_instrument(self, new_idx: int) -> None:
        if new_idx == 99:
            self.show_settings = not self.show_settings
            self.audio.stop_all_continuous()
            return
        if new_idx == 98:
            mode_lbl = self.quantizer.cycle_play_mode()
            self.vfx.spawn_hit_vfx(self.WIDTH - 220, 40, (80, 250, 195), intensity=0.6, label=mode_lbl)
            return
        new_idx = new_idx % len(self.instrument_names)
        if new_idx != self.current_inst_idx:
            self.audio.stop_all_continuous()
            self.current_inst_idx = new_idx

    def _handle_settings_click(self, mx: int, my: int) -> None:
        for key, rect in self.settings_buttons.items():
            if rect.collidepoint(mx, my):
                if key == "close":
                    self.show_settings = False
                elif key == "camera":
                    self.cycle_camera()
                elif key == "audio_out":
                    self.audio.cycle_output_device()
                elif key == "test_sound":
                    self.audio.trigger_drum("kick", velocity=0.95, pan=0.35)
                    self.audio.trigger_guitar_chord([60, 64, 67, 72], velocity=0.9, upstroke=False)
                elif key == "note_naming":
                    self.quantizer.cycle_naming_mode()
                elif key == "visual_mode":
                    self.vfx.cycle_visual_mode()
                elif key == "sensitivity":
                    levels = [0.8, 1.0, 1.3, 1.6, 1.9]
                    cur = min(levels, key=lambda x: abs(x - self.tracker.sensitivity))
                    nxt = levels[(levels.index(cur) + 1) % len(levels)]
                    self.tracker.sensitivity = nxt
                elif key == "volume":
                    vols = [0.5, 0.75, 1.0, 1.25, 1.5]
                    cur = min(vols, key=lambda x: abs(x - self.audio.master_volume))
                    nxt = vols[(vols.index(cur) + 1) % len(vols)]
                    self.audio.master_volume = nxt
                    self.audio.trigger_drum("hihat", velocity=0.8)
                elif key == "scale":
                    self.quantizer.next_scale()
                    chords = self.quantizer.get_chords()
                    if chords:
                        self.audio.trigger_guitar_chord(chords[0][1], velocity=0.8)
                elif key == "update":
                    self.trigger_manual_update()
                break

    def _replay_looper_event(self, event_type: str, payload: Dict) -> None:
        if event_type == "drum":
            self.audio.trigger_drum(payload["drum_key"], velocity=payload["velocity"] * 0.85, pan=payload["pan"])
            self.vfx.spawn_hit_vfx(payload["px"], payload["py"], payload["color"], intensity=0.55, label=f"Loop: {payload['name']}")
        elif event_type == "guitar":
            self.audio.trigger_guitar_chord(payload["chord_notes"], velocity=payload["velocity"] * 0.8, upstroke=payload["upstroke"])
            self.vfx.spawn_hit_vfx(payload["px"], payload["py"], (255, 95, 210), intensity=0.55, label=f"Loop: {payload['chord_name']}")
        elif event_type == "guitar_note":
            self.audio.trigger_guitar_note(payload["midi_note"], velocity=payload["velocity"] * 0.85, pan=0.5)
            self.vfx.spawn_hit_vfx(payload["px"], payload["py"], (0, 245, 255), intensity=0.55, label=f"Loop: {payload['note_name']}")
        elif event_type == "piano":
            self.audio.trigger_piano_note(payload["freq"], velocity=payload["velocity"] * 0.8, pan=payload["pan"])
            self.vfx.spawn_hit_vfx(payload["px"], payload["py"], (0, 235, 255), intensity=0.55, label=f"Loop: {payload['note_name']}")
        elif event_type == "piano_chord":
            self.audio.trigger_piano_chord(payload["midi_notes"], velocity=payload["velocity"] * 0.8, pan=payload["pan"])
            self.vfx.spawn_hit_vfx(payload["px"], payload["py"], (255, 195, 70), intensity=0.55, label=f"Loop: {payload['note_name']}")
        elif event_type == "maestro":
            self.audio.trigger_maestro_beat(payload["chord_notes"], velocity=payload["velocity"] * 0.8, richness=payload["richness"])
            self.vfx.spawn_hit_vfx(payload["px"], payload["py"], (255, 215, 65), intensity=0.6, label=f"Loop: {payload['chord_name']}")

    def _get_camera_frame(self) -> np.ndarray:
        if self.cap is not None and self.cap.isOpened():
            ret, frame = self.cap.read()
            if ret and frame is not None and frame.size > 0:
                if frame.shape[1] != self.WIDTH or frame.shape[0] != self.HEIGHT:
                    frame = cv2.resize(frame, (self.WIDTH, self.HEIGHT), interpolation=cv2.INTER_LINEAR)
                return cv2.flip(frame, 1)

        fallback = np.zeros((self.HEIGHT, self.WIDTH, 3), dtype=np.uint8)
        fallback[:] = (28, 20, 16)
        return fallback

    def run(self) -> None:
        running = True
        prev_time = time.perf_counter()

        while running:
            now = time.perf_counter()
            dt = max(0.001, min(0.1, now - prev_time))
            prev_time = now
            fps = self.clock.get_fps() or 60.0

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        if self.show_settings:
                            self.show_settings = False
                        else:
                            running = False
                    elif event.key == pygame.K_s:
                        self.show_settings = not self.show_settings
                        self.audio.stop_all_continuous()
                    elif event.key == pygame.K_m:
                        mode_lbl = self.quantizer.cycle_play_mode()
                        self.vfx.spawn_hit_vfx(self.WIDTH // 2, 110, (80, 250, 195), intensity=0.7, label=f"MOD: {mode_lbl}")
                    elif event.key == pygame.K_n:
                        n_lbl = self.quantizer.cycle_naming_mode()
                        self.vfx.spawn_hit_vfx(self.WIDTH // 2, 110, (255, 225, 80), intensity=0.7, label=f"NOTA DILI: {n_lbl}")
                    elif event.key == pygame.K_t:
                        s_lbl = self.quantizer.cycle_melody_guide()
                        self.vfx.spawn_hit_vfx(self.WIDTH // 2, 110, (0, 235, 255), intensity=0.7, label=s_lbl)
                    elif event.key == pygame.K_u:
                        self.trigger_manual_update()
                        self.vfx.spawn_hit_vfx(self.WIDTH // 2, 110, (255, 180, 50), intensity=0.7, label="Guncelleme Kontrol Ediliyor...")
                    elif event.key == pygame.K_SPACE and self.current_inst_idx == 0 and not self.show_settings:
                        self.drums.trigger_kick_pedal(self.audio, self.vfx, self.looper)
                    elif event.key == pygame.K_1:
                        self.switch_instrument(0)
                    elif event.key == pygame.K_2:
                        self.switch_instrument(1)
                    elif event.key == pygame.K_3:
                        self.switch_instrument(2)
                    elif event.key == pygame.K_4:
                        self.switch_instrument(3)
                    elif event.key == pygame.K_5:
                        self.switch_instrument(4)
                    elif event.key == pygame.K_6:
                        self.switch_instrument(5)
                    elif event.key == pygame.K_7:
                        self.switch_instrument(6)
                    elif event.key == pygame.K_v:
                        self.vfx.cycle_visual_mode()
                    elif event.key == pygame.K_g:
                        self.quantizer.next_scale()
                    elif event.key == pygame.K_l:
                        self.looper.toggle_record()
                    elif event.key == pygame.K_c:
                        self.looper.clear()
                    elif event.key == pygame.K_f:
                        self.is_fullscreen = not self.is_fullscreen
                        flags = pygame.FULLSCREEN | pygame.DOUBLEBUF if self.is_fullscreen else pygame.DOUBLEBUF
                        self.screen = pygame.display.set_mode((self.WIDTH, self.HEIGHT), flags)
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    mx, my = event.pos
                    if self.show_settings:
                        self._handle_settings_click(mx, my)
                    else:
                        for rect, idx in self.capsule_rects:
                            if rect.collidepoint(mx, my):
                                self.switch_instrument(idx)
                                break

            # 1. Kamera Karesini Al & 10-Parmak El Fiziğini Güncelle
            bgr_mirrored = self._get_camera_frame()
            self.tracker.process_frame(bgr_mirrored)
            active_hands = self.tracker.get_active_hands()

            # 2. Kamera / Sahne Arka Planını Çiz
            self.vfx.render_camera_background(self.screen, bgr_mirrored)

            # 3. 4-Bar Live Looper Güncellemesi
            self.looper.update(self._replay_looper_event)

            # 4. Seçili Enstrüman Modülünü Çalıştır ve Çiz
            if not self.show_settings:
                if self.current_inst_idx == 0:
                    self.drums.update_and_render(self.screen, active_hands, self.audio, self.vfx, self.looper, dt)
                elif self.current_inst_idx == 1:
                    self.guitar.update_and_render(
                        self.screen, active_hands, self.audio, self.quantizer, self.vfx, self.looper, dt
                    )
                elif self.current_inst_idx == 2:
                    self.piano.update_and_render(
                        self.screen, active_hands, self.audio, self.quantizer, self.vfx, self.looper, dt
                    )
                elif self.current_inst_idx == 3:
                    self.violin.update_and_render(
                        self.screen, active_hands, self.audio, self.quantizer, self.vfx, dt
                    )
                elif self.current_inst_idx == 4:
                    self.cello.update_and_render(
                        self.screen, active_hands, self.audio, self.quantizer, self.vfx, dt
                    )
                elif self.current_inst_idx == 5:
                    self.sax.update_and_render(
                        self.screen, active_hands, self.audio, self.quantizer, self.vfx, dt
                    )
                elif self.current_inst_idx == 6:
                    self.maestro.update_and_render(
                        self.screen, active_hands, self.audio, self.quantizer, self.vfx, self.looper, dt
                    )

            # 5. El İskeleti (10 Parmak Ucu) ve VFX
            self.vfx.render_hands_and_vfx(self.screen, active_hands, dt)

            # 6. Üst Holografik Kapsül Menüsü + [M] Nota/Akor Modu + [S] Ayarlar Butonu
            self.capsule_rects = self.vfx.render_top_hud(
                self.screen,
                self.instrument_names,
                self.current_inst_idx,
                self.quantizer.current_scale_name,
                fps,
                self.looper.is_recording,
                len(self.looper.events),
                self.looper.get_progress(),
                self.quantizer.current_play_mode_name,
            )

            # Havada El İle Üst Kapsüllere Dokunarak Enstrüman / Nota-Akor / Ayar Seçimi
            if not self.show_settings and (now - self.last_hover_switch) > 0.50:
                for hand in active_hands:
                    if len(hand.landmarks_px) > 8:
                        tx, ty = hand.landmarks_px[8]
                        if ty < 74:
                            for rect, idx in self.capsule_rects:
                                if rect.collidepoint(tx, ty) and idx != self.current_inst_idx:
                                    self.switch_instrument(idx)
                                    if idx == 99:
                                        lbl = "AYARLAR"
                                    elif idx == 98:
                                        lbl = self.quantizer.current_play_mode_name
                                    else:
                                        lbl = self.instrument_names[idx]
                                    self.vfx.spawn_hit_vfx(rect.centerx, rect.centery, (0, 235, 255), intensity=0.6, label=lbl)
                                    self.last_hover_switch = now
                                    break

            # 7. Ayarlar (Settings) Modalı Açıksa Çiz
            if self.show_settings:
                self.settings_buttons = self.vfx.render_settings_modal(
                    self.screen,
                    self.camera_index,
                    self.camera_status,
                    self.audio.current_output_name,
                    self.audio.current_input_name,
                    self.audio.master_volume,
                    self.tracker.sensitivity,
                    self.quantizer.current_scale_name,
                    self.quantizer.current_naming_mode_name,
                    self.updater.status_text,
                    self.updater.has_update,
                )

            # Otomatik Güncelleme indiriliyorsa veya tamamlandıysa üstte bilgi bandı göster
            if self.updater.is_updating or self.restart_requested:
                upd_bar = pygame.Rect(self.WIDTH // 2 - 260, 82, 520, 38)
                pygame.draw.rect(self.screen, (25, 110, 75), upd_bar, border_radius=10)
                pygame.draw.rect(self.screen, (100, 255, 180), upd_bar, width=2, border_radius=10)
                u_txt = self.vfx.font_sm.render(self.updater.status_text, True, (255, 255, 255))
                self.screen.blit(u_txt, (upd_bar.centerx - u_txt.get_width() // 2, upd_bar.centery - u_txt.get_height() // 2))

            pygame.display.flip()
            self.clock.tick(60)

            if self.restart_requested:
                self.audio.close()
                if self.cap is not None and self.cap.isOpened():
                    self.cap.release()
                pygame.quit()
                restart_application()
                return

        self.audio.close()
        if self.cap is not None and self.cap.isOpened():
            self.cap.release()
        pygame.quit()


if __name__ == "__main__":
    app = AirBeatStudioApp()
    app.run()
