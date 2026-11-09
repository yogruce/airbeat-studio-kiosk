"""
VFX Renderer & RTX Edition Visual Engine
Kullanıcının tek tuşla ([V]) seçebileceği 5 Görsel & Performans Modu:
1. PERFORMANS / SADE MOD (Max FPS): Ham kamera, sıfır partikül, sadece net geometrik hedef.
2. DENGELİ AR STÜDYO: Yarı saydam modern enstrüman pedleri, akıcı el izleri, optimize partiküller.
3. SİNEMATİK SAHNE: Dark-Stage filtresi, neon kuyruklu yıldız izleri, kıvılcımlar ve ritim nabzı.
4. HAYALET / SADECE NEON: Kamera görüntüsü gizlenir, siber uzayda neon el iskeleti ve hologramlar parlar.
5. RTX AI KONSER SAHNESİ (RTX Edition):
   - Gerçek zamanlı MediaPipe AI Selfie Segmentation ile kullanıcının odasını (arka planı) siler,
     yerine vuruşlarla parlayan Lazerli Cyberpunk Konser Sahnesi koyar!
   - Oyuncunun vücudunun etrafına gerçek zamanlı Neon Rim-Light (Aura Konturu) çizer.
   - Ekran üzerinde HDR Bloom / Additive Glow parlama katmanı çalıştırır.
"""

from dataclasses import dataclass
import math
import os
import random
import time
from typing import Dict, List, Optional, Tuple

import cv2
import mediapipe as mp
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision as mp_vision
import numpy as np
import pygame

from core.hand_tracker import HAND_CONNECTIONS, HandPhysicsState
from core.paths import get_resource_path


@dataclass
class Shockwave:
    x: int
    y: int
    radius: float
    max_radius: float
    color: Tuple[int, int, int]
    alpha: float = 1.0
    label: str = ""


@dataclass
class Particle:
    x: float
    y: float
    vx: float
    vy: float
    color: Tuple[int, int, int]
    size: float
    life: float = 1.0


class VisualMode:
    PERFORMANCE_MINIMAL = 0   # 1: Sade / Performans
    BALANCED_STUDIO = 1       # 2: Dengeli AR Stüdyo
    CINEMATIC_STAGE = 2       # 3: Sinematik Sahne
    CYBER_NEON_ONLY = 3       # 4: Sadece Neon (Gizlilik Modu)
    RTX_AI_CONCERT_STAGE = 4  # 5: RTX AI Konser Sahnesi (Arka Plan Silme + Lazer + HDR Bloom)

    NAMES = [
        "1: SADE / PERFORMANS (Max FPS)",
        "2: DENGELI AR STUDYO",
        "3: SINEMATIK SAHNE (Full VFX)",
        "4: SADECE NEON (Hayalet Mod)",
        "5: RTX AI KONSER SAHNESI (AI GreenScreen + HDR Bloom)",
    ]


class VFXRenderer:
    def __init__(self, width: int = 1280, height: int = 720) -> None:
        self.width = width
        self.height = height
        self.visual_mode: int = VisualMode.BALANCED_STUDIO
        self.shockwaves: List[Shockwave] = []
        self.particles: List[Particle] = []
        self.stage_pulse: float = 0.0
        self.last_hit_note: str = "---"
        self.last_hit_color: Tuple[int, int, int] = (0, 225, 255)
        self.start_time = time.perf_counter()

        pygame.font.init()
        self.font_xs = pygame.font.SysFont("consolas", 14, bold=True)
        self.font_sm = pygame.font.SysFont("segoeui", 16, bold=True)
        self.font_md = pygame.font.SysFont("segoeui", 22, bold=True)
        self.font_lg = pygame.font.SysFont("segoeui", 34, bold=True)

        # RTX AI Segmenter (Gerçek zamanlı arka plan ayırma)
        self.segmenter: Optional[mp_vision.ImageSegmenter] = None
        self.last_seg_ms: int = 0
        self._init_rtx_segmenter()
        self._precompute_rtx_stage_template()

    def _init_rtx_segmenter(self) -> None:
        seg_path = get_resource_path(os.path.join("core", "selfie_segmenter.tflite"))
        if os.path.exists(seg_path):
            try:
                base_opts = mp_python.BaseOptions(model_asset_path=seg_path)
                opts = mp_vision.ImageSegmenterOptions(
                    base_options=base_opts,
                    running_mode=mp_vision.RunningMode.VIDEO,
                    output_category_mask=True,
                )
                self.segmenter = mp_vision.ImageSegmenter.create_from_options(opts)
            except Exception as e:
                print(f"[VFXRenderer] RTX AI Segmenter baslatilamadi: {e}")

    def _precompute_rtx_stage_template(self) -> None:
        """RTX Konser Sahnesi için sinematik深 (derin) stadyum/synthwave arka plan matrisi."""
        y_idx = np.linspace(0.0, 1.0, self.height, dtype=np.float32)[:, None]
        x_idx = np.linspace(-1.0, 1.0, self.width, dtype=np.float32)[None, :]

        # Üst kısım derin gece mavisi/mor, ufuk çizgisi parlak neon magenta/cyan
        horizon = np.exp(-((y_idx - 0.62) ** 2) / 0.018)
        r = np.clip(12 + 135 * horizon + 35 * (1.0 - y_idx), 0, 255).astype(np.uint8)
        g = np.clip(10 + 45 * horizon + 18 * y_idx, 0, 255).astype(np.uint8)
        b = np.clip(28 + 185 * horizon + 55 * (1.0 - np.abs(x_idx)), 0, 255).astype(np.uint8)

        bg = np.stack([np.broadcast_to(r, (self.height, self.width)),
                       np.broadcast_to(g, (self.height, self.width)),
                       np.broadcast_to(b, (self.height, self.width))], axis=-1).copy()

        # Perspektif Sahne Zemini Izgarası
        horizon_y = int(self.height * 0.62)
        for gy in range(horizon_y, self.height, 36):
            cv2.line(bg, (0, gy), (self.width, gy), (90, 35, 130), 1)
        for gx in range(-self.width, self.width * 2, 140):
            cv2.line(bg, (self.width // 2 + (gx - self.width // 2) // 4, horizon_y), (gx, self.height), (75, 40, 120), 1)

        self.rtx_stage_base_rgb = bg

    def cycle_visual_mode(self) -> str:
        self.visual_mode = (self.visual_mode + 1) % len(VisualMode.NAMES)
        if self.visual_mode == VisualMode.PERFORMANCE_MINIMAL:
            self.particles.clear()
            self.shockwaves.clear()
        return VisualMode.NAMES[self.visual_mode]

    def spawn_hit_vfx(
        self,
        x: int,
        y: int,
        color: Tuple[int, int, int],
        intensity: float = 0.8,
        label: str = "",
    ) -> None:
        if label:
            self.last_hit_note = label
        self.last_hit_color = color
        self.stage_pulse = min(1.0, intensity * 0.95)

        max_r = 65.0 if self.visual_mode == VisualMode.PERFORMANCE_MINIMAL else (145.0 * intensity + 50.0)
        self.shockwaves.append(
            Shockwave(x=x, y=y, radius=18.0, max_radius=max_r, color=color, alpha=1.0, label=label)
        )

        if self.visual_mode == VisualMode.PERFORMANCE_MINIMAL:
            return

        count = (
            12
            if self.visual_mode == VisualMode.BALANCED_STUDIO
            else int(34 * intensity + 10)
        )
        for _ in range(count):
            ang = random.uniform(0.0, math.tau)
            spd = random.uniform(130.0, 520.0) * intensity
            self.particles.append(
                Particle(
                    x=float(x),
                    y=float(y),
                    vx=math.cos(ang) * spd,
                    vy=math.sin(ang) * spd - 70.0,
                    color=color,
                    size=random.uniform(3.5, 8.0),
                    life=1.0,
                )
            )

    def render_camera_background(self, screen: pygame.Surface, bgr_mirrored: np.ndarray) -> None:
        """Seçilen görsel moda göre arka planı veya RTX AI Sahnesini çizer."""
        if self.visual_mode == VisualMode.CYBER_NEON_ONLY:
            screen.fill((8, 10, 18))
            grid_color = (22, 30, 52)
            for gx in range(0, self.width, 80):
                pygame.draw.line(screen, grid_color, (gx, 0), (gx, self.height), 1)
            for gy in range(0, self.height, 80):
                pygame.draw.line(screen, grid_color, (0, gy), (self.width, gy), 1)
            return

        rgb = cv2.cvtColor(bgr_mirrored, cv2.COLOR_BGR2RGB)

        if self.visual_mode == VisualMode.RTX_AI_CONCERT_STAGE and self.segmenter is not None:
            rgb = self._render_rtx_ai_stage(rgb)
        elif self.visual_mode == VisualMode.CINEMATIC_STAGE:
            rgb = (rgb.astype(np.uint16) * 140 // 255).astype(np.uint8)

        surf = pygame.surfarray.make_surface(np.transpose(rgb, (1, 0, 2)))
        screen.blit(surf, (0, 0))

    def _render_rtx_ai_stage(self, rgb_frame: np.ndarray) -> np.ndarray:
        """
        RTX AI Konser Sahnesi:
        1. Kullanıcının silüetini AI ile odadan ayırır.
        2. Arkaya vuruş şiddetiyle (stage_pulse) parlayan Lazerli Konser Sahnesi yerleştirir.
        3. Kullanıcının etrafına parlayan Neon Aura (Rim Light) çizer.
        """
        # Performans için segmentasyonu yarı çözünürlükte koşturup tam çözünürlüğe büyüt
        small_rgb = cv2.resize(rgb_frame, (320, 180), interpolation=cv2.INTER_LINEAR)
        mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=small_rgb)
        ts_ms = int((time.perf_counter() - self.start_time) * 1000)
        if ts_ms <= self.last_seg_ms:
            ts_ms = self.last_seg_ms + 1
        self.last_seg_ms = ts_ms

        seg_result = self.segmenter.segment_for_video(mp_img, ts_ms)
        mask_small = seg_result.category_mask.numpy_view()
        # Model çıktısında kişi maskesini yumuşat
        person_small = ((mask_small == 0) if np.mean(mask_small[60:140, 110:210]) < 0.5 else (mask_small > 0)).astype(np.uint8) * 255
        person_Small_blur = cv2.GaussianBlur(person_small, (7, 7), 0)
        mask_full = cv2.resize(person_Small_blur, (self.width, self.height), interpolation=cv2.INTER_LINEAR)

        # Dinamik Konser Sahnesi + Lazer Işınları
        stage = self.rtx_stage_base_rgb.copy()
        t_now = time.perf_counter() - self.start_time
        pulse_boost = int(self.stage_pulse * 120)

        # Sahne tavanından inen hareketli konser lazerleri
        for beam_i in range(5):
            bx_top = int(self.width * (0.15 + 0.175 * beam_i))
            sway = int(math.sin(t_now * 2.2 + beam_i * 1.3) * 220)
            bx_bot = bx_top + sway
            l_col = (
                min(255, self.last_hit_color[0] + pulse_boost),
                min(255, self.last_hit_color[1] + pulse_boost // 2),
                min(255, self.last_hit_color[2] + pulse_boost),
            )
            cv2.line(stage, (bx_top, 0), (bx_bot, self.height), l_col, 2 + int(self.stage_pulse * 5))

        # Oyuncu Aura Konturu (Neon Rim-Light)
        edges = cv2.Canny(mask_small, 60, 160)
        edges_dilated = cv2.dilate(edges, np.ones((3, 3), np.uint8), iterations=1)
        edges_full = cv2.resize(edges_dilated, (self.width, self.height), interpolation=cv2.INTER_NEAREST)

        alpha = (mask_full.astype(np.float32) / 255.0)[..., None]
        comp = (rgb_frame.astype(np.float32) * alpha + stage.astype(np.float32) * (1.0 - alpha)).astype(np.uint8)

        # Neon Aura rengini oyuncunun konturuna bas
        comp[edges_full > 0] = self.last_hit_color
        return comp

    def render_hands_and_vfx(
        self,
        screen: pygame.Surface,
        active_hands: List[HandPhysicsState],
        dt: float,
    ) -> None:
        # 1. El İskeleti & Işık İzleri
        for hand in active_hands:
            base_color = (0, 230, 255) if hand.label == "Left" else (255, 75, 195)
            hot_color = (255, 230, 80)

            if self.visual_mode != VisualMode.PERFORMANCE_MINIMAL and len(hand.trail) > 2:
                pts = list(hand.trail)
                for i in range(1, len(pts)):
                    ratio = i / len(pts)
                    c = (
                        int(base_color[0] * (1 - ratio) + hot_color[0] * ratio),
                        int(base_color[1] * (1 - ratio) + hot_color[1] * ratio),
                        int(base_color[2] * (1 - ratio) + hot_color[2] * ratio),
                    )
                    thickness = max(1, int(ratio * (13 if self.visual_mode == VisualMode.RTX_AI_CONCERT_STAGE else 9)))
                    # RTX modunda dış parlama (Additive Bloom Halo)
                    if self.visual_mode == VisualMode.RTX_AI_CONCERT_STAGE:
                        glow_c = (c[0] // 3, c[1] // 3, c[2] // 3)
                        pygame.draw.line(screen, glow_c, (pts[i - 1][0], pts[i - 1][1]), (pts[i][0], pts[i][1]), thickness + 8)
                    pygame.draw.line(screen, c, (pts[i - 1][0], pts[i - 1][1]), (pts[i][0], pts[i][1]), thickness)

            if self.visual_mode == VisualMode.PERFORMANCE_MINIMAL:
                if len(hand.landmarks_px) > 8:
                    tx, ty = hand.landmarks_px[8]
                    pygame.draw.circle(screen, base_color, (tx, ty), 12, 3)
                    pygame.draw.circle(screen, (255, 255, 255), (tx, ty), 4)
            else:
                for i1, i2 in HAND_CONNECTIONS:
                    p1 = hand.landmarks_px[i1]
                    p2 = hand.landmarks_px[i2]
                    pygame.draw.line(screen, base_color, p1, p2, 3 if self.visual_mode == VisualMode.RTX_AI_CONCERT_STAGE else 2)
                for idx, pt in enumerate(hand.landmarks_px):
                    r = 9 if idx in (4, 8, 12, 16, 20) else 4
                    col = hot_color if (idx == 8 and hand.speed > 1.2) else (255, 255, 255)
                    pygame.draw.circle(screen, col, pt, r)
                    pygame.draw.circle(screen, base_color, pt, r + 3, 2)

        # 2. Şok Dalgaları
        alive_waves = []
        for sw in self.shockwaves:
            sw.radius += (sw.max_radius - sw.radius) * min(1.0, dt * 11.0) + 125.0 * dt
            sw.alpha -= dt * 2.3
            if sw.alpha > 0.05:
                w_thick = max(1, int(sw.alpha * 7))
                if self.visual_mode == VisualMode.RTX_AI_CONCERT_STAGE:
                    pygame.draw.circle(
                        screen,
                        (sw.color[0] // 3, sw.color[1] // 3, sw.color[2] // 3),
                        (sw.x, sw.y),
                        int(sw.radius),
                        w_thick + 8,
                    )
                pygame.draw.circle(screen, sw.color, (sw.x, sw.y), int(sw.radius), w_thick)
                if sw.label:
                    lbl_surf = self.font_md.render(sw.label, True, (255, 255, 255))
                    screen.blit(lbl_surf, (sw.x - lbl_surf.get_width() // 2, int(sw.y - sw.radius - 28)))
                alive_waves.append(sw)
        self.shockwaves = alive_waves

        # 3. Partiküller
        if self.visual_mode != VisualMode.PERFORMANCE_MINIMAL:
            alive_particles = []
            for p in self.particles:
                p.x += p.vx * dt
                p.y += p.vy * dt
                p.vy += 420.0 * dt
                p.life -= dt * 1.85
                if p.life > 0.05:
                    r = max(1, int(p.size * p.life))
                    if self.visual_mode == VisualMode.RTX_AI_CONCERT_STAGE:
                        pygame.draw.circle(
                            screen,
                            (p.color[0] // 3, p.color[1] // 3, p.color[2] // 3),
                            (int(p.x), int(p.y)),
                            r + 4,
                        )
                    pygame.draw.circle(screen, p.color, (int(p.x), int(p.y)), r)
                    alive_particles.append(p)
            self.particles = alive_particles

        # 4. Sahne Nabzı
        if self.stage_pulse > 0.02:
            if self.visual_mode in (VisualMode.CINEMATIC_STAGE, VisualMode.CYBER_NEON_ONLY, VisualMode.RTX_AI_CONCERT_STAGE):
                border_col = (
                    int(min(255, self.last_hit_color[0] * self.stage_pulse)),
                    int(min(255, self.last_hit_color[1] * self.stage_pulse)),
                    int(min(255, self.last_hit_color[2] * self.stage_pulse)),
                )
                pygame.draw.rect(screen, border_col, (0, 0, self.width, self.height), int(8 * self.stage_pulse + 1))
            self.stage_pulse = max(0.0, self.stage_pulse - dt * 3.2)

    def render_top_hud(
        self,
        screen: pygame.Surface,
        instrument_names: List[str],
        current_inst_idx: int,
        scale_name: str,
        fps: float,
        looper_recording: bool,
        looper_event_count: int,
        looper_progress: float,
        play_mode_name: str = "HIBRIT (Nota + Akor)",
    ) -> List[Tuple[pygame.Rect, int]]:
        capsule_rects: List[Tuple[pygame.Rect, int]] = []

        top_bar = pygame.Surface((self.width, 74), pygame.SRCALPHA)
        top_bar.fill((10, 14, 26, 205))
        screen.blit(top_bar, (0, 0))
        pygame.draw.line(screen, (0, 210, 255), (0, 74), (self.width, 74), 2)

        n_inst = len(instrument_names)
        margin_x = 12
        mode_w = 152
        settings_w = 122
        gap = 6
        avail_w = self.width - 2 * margin_x - mode_w - settings_w - 2 * gap
        cap_w = (avail_w - gap * (n_inst - 1)) // n_inst

        for i, name in enumerate(instrument_names):
            rx = margin_x + i * (cap_w + gap)
            ry = 12
            rect = pygame.Rect(rx, ry, cap_w, 50)
            capsule_rects.append((rect, i))

            is_active = i == current_inst_idx
            bg_col = (0, 175, 230) if is_active else (26, 34, 56)
            border_col = (140, 245, 255) if is_active else (65, 85, 125)

            pygame.draw.rect(screen, bg_col, rect, border_radius=10)
            pygame.draw.rect(screen, border_col, rect, width=3 if is_active else 1, border_radius=10)

            txt = self.font_xs.render(f"[{i+1}] {name}", True, (255, 255, 255) if is_active else (185, 205, 230))
            screen.blit(txt, (rect.centerx - txt.get_width() // 2, rect.centery - txt.get_height() // 2))

        # Sağ Üst Yanı: [M] NOTA / AKOR MODU Butonu (98 = Nota/Akor Modu Değiştir)
        mode_rect = pygame.Rect(self.width - margin_x - settings_w - gap - mode_w, 12, mode_w, 50)
        capsule_rects.append((mode_rect, 98))
        pygame.draw.rect(screen, (20, 95, 85), mode_rect, border_radius=10)
        pygame.draw.rect(screen, (80, 250, 195), mode_rect, width=2, border_radius=10)
        short_mode = play_mode_name.split(" ")[0]
        m_txt = self.font_xs.render(f"[M] MOD: {short_mode}", True, (235, 255, 245))
        screen.blit(m_txt, (mode_rect.centerx - m_txt.get_width() // 2, mode_rect.centery - m_txt.get_height() // 2))

        # Sağ Üst: AYARLAR Butonu ([S] veya Tıkla)
        set_rect = pygame.Rect(self.width - margin_x - settings_w, 12, settings_w, 50)
        capsule_rects.append((set_rect, 99))  # 99 = Ayarlar Modalını Aç/Kapat
        pygame.draw.rect(screen, (55, 35, 95), set_rect, border_radius=10)
        pygame.draw.rect(screen, (210, 140, 255), set_rect, width=2, border_radius=10)
        s_txt = self.font_xs.render("[S] AYARLAR", True, (255, 235, 255))
        screen.blit(s_txt, (set_rect.centerx - s_txt.get_width() // 2, set_rect.centery - s_txt.get_height() // 2))

        bot_h = 54
        bot_y = self.height - bot_h
        bot_bar = pygame.Surface((self.width, bot_h), pygame.SRCALPHA)
        bot_bar.fill((10, 14, 26, 210))
        screen.blit(bot_bar, (0, bot_y))
        pygame.draw.line(screen, (50, 80, 130), (0, bot_y), (self.width, bot_y), 1)

        left_info = f"[M] Mod: {play_mode_name}  |  [N] Nota Dili  |  [T] Sarki Rehberi  |  [G] Gam: {scale_name[:22]}"
        l_surf = self.font_xs.render(left_info, True, (160, 230, 255))
        screen.blit(l_surf, (18, bot_y + 18))

        loop_x = self.width - 490
        loop_w = 225
        loop_rect = pygame.Rect(loop_x, bot_y + 14, loop_w, 26)
        pygame.draw.rect(screen, (25, 32, 48), loop_rect, border_radius=6)
        prog_w = int(loop_w * looper_progress)
        prog_col = (255, 65, 95) if looper_recording else (0, 220, 150)
        if prog_w > 2:
            pygame.draw.rect(screen, prog_col, (loop_x, bot_y + 14, prog_w, 26), border_radius=6)
        pygame.draw.rect(screen, (110, 140, 180), loop_rect, 1, border_radius=6)

        loop_status = "REC" if looper_recording else f"LOOP ({looper_event_count})"
        lt_surf = self.font_xs.render(f"[L] {loop_status} | [C] Sil", True, (255, 255, 255))
        screen.blit(lt_surf, (loop_x + 10, bot_y + 19))

        fps_col = (80, 255, 140) if fps >= 45 else ((255, 210, 60) if fps >= 28 else (255, 80, 80))
        right_info = f"Nota: {self.last_hit_note:<4} | {int(fps)} FPS | REAL WAV"
        r_surf = self.font_xs.render(right_info, True, fps_col)
        screen.blit(r_surf, (self.width - r_surf.get_width() - 18, bot_y + 18))

        return capsule_rects

    def render_settings_modal(
        self,
        screen: pygame.Surface,
        camera_index: int,
        camera_status: str,
        output_dev_name: str,
        input_dev_name: str,
        master_vol: float,
        sensitivity: float,
        scale_name: str,
        naming_mode_name: str = "DO-RE-MI (Solfej)",
    ) -> Dict[str, pygame.Rect]:
        buttons: Dict[str, pygame.Rect] = {}

        dim = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        dim.fill((6, 8, 16, 215))
        screen.blit(dim, (0, 0))

        mw, mh = 780, 580
        mx = (self.width - mw) // 2
        my = (self.height - mh) // 2
        panel = pygame.Rect(mx, my, mw, mh)

        pygame.draw.rect(screen, (18, 24, 42), panel, border_radius=18)
        pygame.draw.rect(screen, (0, 215, 255), panel, width=3, border_radius=18)

        title = self.font_lg.render("SISTEM VE OYUN AYARLARI (SETTINGS)", True, (0, 235, 255))
        screen.blit(title, (mx + 32, my + 20))

        close_btn = pygame.Rect(mx + mw - 125, my + 18, 100, 40)
        buttons["close"] = close_btn
        pygame.draw.rect(screen, (180, 45, 75), close_btn, border_radius=10)
        c_txt = self.font_sm.render("KAPAT [S]", True, (255, 255, 255))
        screen.blit(c_txt, (close_btn.centerx - c_txt.get_width() // 2, close_btn.centery - c_txt.get_height() // 2))

        rows = [
            ("camera", "1. Kamera Kaynagi:", f"Kamera #{camera_index} ({camera_status})", "Degistir >"),
            ("audio_out", "2. Hoparlor / Kulaklik:", f"{output_dev_name}", "Cihaz Degistir >"),
            ("test_sound", "3. Ses Cikis Testi:", "Hoparlorunuzden aninda bateri/akor sesi calar", "SESI TEST ET !"),
            ("note_naming", "4. Nota Gosterim Dili:", f"{naming_mode_name} (Do-Re-Mi / C-D-E)", "Dil Degistir [N] >"),
            ("visual_mode", "5. Gorunum / RTX Modu:", f"{VisualMode.NAMES[self.visual_mode]}", "Mod Degistir >"),
            ("sensitivity", "6. El Vurus Hassasiyeti:", f"%{int(sensitivity * 100)} (Dokunma / Vurus Esigi)", "Hassasiyet >"),
            ("volume", "7. Ana Ses Seviyesi:", f"%{int(master_vol * 100)}", "Ses Seviyesi >"),
            ("scale", "8. Muzik Gam Kilidi:", f"{scale_name[:36]}", "Gam Degistir >"),
        ]

        start_y = my + 78
        row_h = 56
        for idx, (key, label_txt, val_txt, btn_txt) in enumerate(rows):
            ry = start_y + idx * row_h
            row_rect = pygame.Rect(mx + 28, ry, mw - 56, 48)
            pygame.draw.rect(screen, (28, 36, 62), row_rect, border_radius=10)
            pygame.draw.rect(screen, (60, 85, 130), row_rect, width=1, border_radius=10)

            lbl_s = self.font_sm.render(label_txt, True, (170, 215, 255))
            screen.blit(lbl_s, (row_rect.x + 16, row_rect.y + 13))

            val_s = self.font_sm.render(val_txt, True, (255, 245, 150))
            screen.blit(val_s, (row_rect.x + 225, row_rect.y + 13))

            act_btn = pygame.Rect(row_rect.right - 168, row_rect.y + 6, 158, 36)
            buttons[key] = act_btn
            btn_col = (0, 175, 120) if key == "test_sound" else (0, 140, 210)
            pygame.draw.rect(screen, btn_col, act_btn, border_radius=8)
            pygame.draw.rect(screen, (180, 240, 255), act_btn, width=1, border_radius=8)
            b_s = self.font_xs.render(btn_txt, True, (255, 255, 255))
            screen.blit(b_s, (act_btn.centerx - b_s.get_width() // 2, act_btn.centery - b_s.get_height() // 2))

        footer = self.font_xs.render(
            "Ipucu: Ses gelmiyorsa '2. Hoparlor / Kulaklik' butonuna basarak aktif ses cihazinizi (SteelSeries / Hoparlor) secin.",
            True,
            (190, 210, 240),
        )
        screen.blit(footer, (mx + 32, my + mh - 32))
        return buttons
