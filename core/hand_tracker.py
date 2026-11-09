"""
Hand Tracker & 10-Finger Multi-Touch Physics Engine
Google MediaPipe HandLandmarker (21 Eklem) kullanarak:
- Her iki elin 5 parmağının tamamını (Toplam 10 Parmak: Başparmak, İşaret, Orta, Yüzük, Serçe)
  BAĞIMSIZ hız (vx, vy), ivme ve vuruş (downstroke strike) fiziğiyle takip eder.
  Böylece Piyanoda aynı anda 5-10 tuşa basılabilir, Gitarda ve Saksafonda her parmak ayrı perdeye basabilir.
- Elin kavrama açısını (Grip Angle) ve sanal Baget / Yay / Baton uç noktasını (stick_tip_px) hesaplar.
"""

from collections import deque
from dataclasses import dataclass, field
import math
import os
import time
from typing import Deque, Dict, List, Tuple
import urllib.request

import cv2
import mediapipe as mp
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision as mp_vision
import numpy as np

from core.paths import get_resource_path


HAND_CONNECTIONS = [
    (0, 1), (1, 2), (2, 3), (3, 4),        # Başparmak
    (0, 5), (5, 6), (6, 7), (7, 8),        # İşaret parmağı
    (5, 9), (9, 10), (10, 11), (11, 12),   # Orta parmak
    (9, 13), (13, 14), (14, 15), (15, 16), # Yüzük parmağı
    (13, 17), (0, 17), (17, 18), (18, 19), (19, 20) # Serçe parmak & Avuç
]

FINGER_TIP_IDS = (4, 8, 12, 16, 20)
FINGER_NAMES = ("Thumb", "Index", "Middle", "Ring", "Pinky")


@dataclass
class FingerPhysicsState:
    """Tek bir parmak ucunun bağımsız konum, hız ve vuruş (tuş basma) fiziği."""
    finger_index: int  # 0=Başparmak, 1=İşaret, 2=Orta, 3=Yüzük, 4=Serçe
    landmark_id: int   # 4, 8, 12, 16, 20
    x: float = 0.5
    y: float = 0.5
    px: int = 640
    py: int = 360
    vx: float = 0.0
    vy: float = 0.0
    prev_vy: float = 0.0
    speed: float = 0.0
    is_extended: bool = True
    is_downstroke_strike: bool = False
    strike_velocity: float = 0.0
    last_strike_time: float = 0.0


@dataclass
class HandPhysicsState:
    label: str  # "Left" veya "Right" (Ayna görüntüsündeki gerçek kullanıcı eli)
    landmarks_norm: List[Tuple[float, float, float]] = field(default_factory=list)
    landmarks_px: List[Tuple[int, int]] = field(default_factory=list)

    # 5 Parmağın bağımsız fizik durumu (0..4 -> Başparmak..Serçe)
    fingers: List[FingerPhysicsState] = field(
        default_factory=lambda: [
            FingerPhysicsState(finger_index=i, landmark_id=lid)
            for i, lid in enumerate(FINGER_TIP_IDS)
        ]
    )

    # İşaret parmağı ucu (8), Avuç merkezi (9) ve Bilek (0) normalize koordinatları
    tip_x: float = 0.5
    tip_y: float = 0.5
    palm_x: float = 0.5
    palm_y: float = 0.5
    wrist_x: float = 0.5
    wrist_y: float = 0.5

    # Sanal Baget / Yay / Baton tutuş vektörü (Avuç içinden dışarı uzanan uç nokta)
    grip_angle: float = 0.0
    stick_tip_px: Tuple[int, int] = (640, 360)
    stick_tip_norm: Tuple[float, float] = (0.5, 0.5)
    stick_vy: float = 0.0
    stick_speed: float = 0.0

    # El genel hız vektörü (ekran birimi / saniye)
    vx: float = 0.0
    vy: float = 0.0
    speed: float = 0.0
    prev_vy: float = 0.0

    # El genel vuruş (Strike) tespiti
    is_downstroke_strike: bool = False
    strike_velocity: float = 0.0
    last_strike_time: float = 0.0

    # Açık parmak listesi ve sayısı (0-5)
    open_fingers: int = 0
    finger_extended_mask: List[bool] = field(default_factory=lambda: [False] * 5)

    # Başparmak ve İşaret parmağı kıstırma (Pinch / Pena tutuşu) mesafesi
    pinch_distance: float = 0.1
    is_pinching: bool = False

    # Işık izi (Light trail) geçmişi
    trail: Deque[Tuple[int, int, float]] = field(default_factory=lambda: deque(maxlen=18))
    last_seen: float = 0.0


class HandTracker:
    MODEL_URL = (
        "https://storage.googleapis.com/mediapipe-models/"
        "hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task"
    )

    def __init__(self, width: int = 1280, height: int = 720) -> None:
        self.width = width
        self.height = height
        self.model_path = get_resource_path(os.path.join("core", "hand_landmarker.task"))
        self._ensure_model()

        base_options = mp_python.BaseOptions(model_asset_path=self.model_path)
        options = mp_vision.HandLandmarkerOptions(
            base_options=base_options,
            running_mode=mp_vision.RunningMode.VIDEO,
            num_hands=2,
            min_hand_detection_confidence=0.50,
            min_hand_presence_confidence=0.50,
            min_tracking_confidence=0.50,
        )
        self.landmarker = mp_vision.HandLandmarker.create_from_options(options)

        self.hands_state: Dict[str, HandPhysicsState] = {
            "Left": HandPhysicsState(label="Left"),
            "Right": HandPhysicsState(label="Right"),
        }
        self.sensitivity: float = 1.30  # Vuruş hassasiyeti çarpanı (0.5 - 2.0)
        self.prev_time = time.perf_counter()
        self.start_ts = time.perf_counter()
        self.last_mp_ms: int = 0

    def _ensure_model(self) -> None:
        if not os.path.exists(self.model_path):
            print("[HandTracker] MediaPipe HandLandmarker modeli indiriliyor...")
            urllib.request.urlretrieve(self.MODEL_URL, self.model_path)

    def process_frame(self, bgr_mirrored: np.ndarray) -> Dict[str, HandPhysicsState]:
        """Ayna (mirrored) BGR kareyi işler, 10 parmağın ve her iki elin hız/vuruş fiziğini günceller."""
        now = time.perf_counter()
        dt = max(0.004, min(0.1, now - self.prev_time))
        self.prev_time = now

        h, w, _ = bgr_mirrored.shape
        self.width, self.height = w, h

        rgb = cv2.cvtColor(bgr_mirrored, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)

        ts_ms = int((now - self.start_ts) * 1000)
        if ts_ms <= self.last_mp_ms:
            ts_ms = self.last_mp_ms + 1
        self.last_mp_ms = ts_ms

        result = self.landmarker.detect_for_video(mp_image, ts_ms)

        detected_labels = set()
        if result.hand_landmarks and result.handedness:
            # Eğer iki el algılandıysa X konumuna göre sol/sağ atamasını güçlendir
            pairs = list(zip(result.hand_landmarks, result.handedness))
            if len(pairs) == 2:
                x0 = pairs[0][0][0].x
                x1 = pairs[1][0][0].x
                if x0 <= x1:
                    ordered = [("Left", pairs[0][0]), ("Right", pairs[1][0])]
                else:
                    ordered = [("Left", pairs[1][0]), ("Right", pairs[0][0])]
                for user_hand, lm_list in ordered:
                    detected_labels.add(user_hand)
                    self._update_hand_physics(self.hands_state[user_hand], lm_list, dt, now, w, h)
            else:
                for lm_list, handedness_list in pairs:
                    raw_cat = handedness_list[0].category_name
                    user_hand = "Right" if raw_cat == "Left" else "Left"
                    if user_hand in detected_labels:
                        user_hand = "Left" if user_hand == "Right" else "Right"
                    detected_labels.add(user_hand)
                    self._update_hand_physics(self.hands_state[user_hand], lm_list, dt, now, w, h)

        # Kameradan çıkan ellerin hızını yumuşakça sönümle
        for lbl, st in self.hands_state.items():
            if lbl not in detected_labels:
                st.is_downstroke_strike = False
                st.vx *= 0.6
                st.vy *= 0.6
                st.speed *= 0.6
                for fg in st.fingers:
                    fg.is_downstroke_strike = False
                    fg.vx *= 0.5
                    fg.vy *= 0.5
                    fg.speed *= 0.5
                if now - st.last_seen > 0.25 and len(st.trail) > 0:
                    st.trail.popleft()

        return self.hands_state

    def _update_hand_physics(
        self,
        state: HandPhysicsState,
        lm_list,
        dt: float,
        now: float,
        w: int,
        h: int,
    ) -> None:
        norms = [(lm.x, lm.y, lm.z) for lm in lm_list]
        pxs = [(int(lm.x * w), int(lm.y * h)) for lm in lm_list]

        new_tip_x, new_tip_y, _ = norms[8]   # İşaret parmağı ucu
        new_palm_x, new_palm_y, _ = norms[9] # Orta parmak kökü / Avuç merkezi
        new_wrist_x, new_wrist_y, _ = norms[0]

        was_recently_seen = (now - state.last_seen) < 0.25

        if was_recently_seen:
            raw_vx = (new_tip_x - state.tip_x) / dt
            raw_vy = (new_tip_y - state.tip_y) / dt
            state.prev_vy = state.vy
            state.vx = 0.40 * state.vx + 0.60 * raw_vx
            state.vy = 0.40 * state.vy + 0.60 * raw_vy
            state.speed = float(np.hypot(state.vx, state.vy))
        else:
            state.vx = 0.0
            state.vy = 0.0
            state.speed = 0.0
            state.prev_vy = 0.0

        state.tip_x, state.tip_y = new_tip_x, new_tip_y
        state.palm_x, state.palm_y = new_palm_x, new_palm_y
        state.wrist_x, state.wrist_y = new_wrist_x, new_wrist_y
        state.landmarks_norm = norms
        state.landmarks_px = pxs

        # Açık parmak maskesini hesapla (5 parmak için True/False)
        ext_mask = self._compute_extended_fingers_mask(norms)
        state.finger_extended_mask = ext_mask
        state.open_fingers = sum(1 for m in ext_mask if m)

        # Pena tutuşu / Kıstırma (Başparmak 4 ile İşaret 8 arası mesafe)
        state.pinch_distance = float(np.hypot(norms[4][0] - norms[8][0], norms[4][1] - norms[8][1]))
        state.is_pinching = state.pinch_distance < 0.065

        # Sanal Baget / Yay / Baton açısı ve uç noktası:
        # Bilekten (0) işaret/orta parmak köküne (5 ve 9 ortası) giden vektör boyunca uzatılır
        knuckle_x = (norms[5][0] + norms[9][0]) * 0.5
        knuckle_y = (norms[5][1] + norms[9][1]) * 0.5
        dx = knuckle_x - new_wrist_x
        dy = knuckle_y - new_wrist_y
        angle = math.atan2(dy, dx)
        state.grip_angle = angle

        # Baget ucu: Avuç merkezinden tutuş yönünde ~155 piksel ilerisi
        stick_len_norm = 0.145
        st_nx = knuckle_x + math.cos(angle) * stick_len_norm
        st_ny = knuckle_y + math.sin(angle) * stick_len_norm
        prev_st_ny = state.stick_tip_norm[1]
        state.stick_tip_norm = (st_nx, st_ny)
        state.stick_tip_px = (int(st_nx * w), int(st_ny * h))
        if was_recently_seen:
            raw_st_vy = (st_ny - prev_st_ny) / dt
            state.stick_vy = 0.40 * state.stick_vy + 0.60 * raw_st_vy
            state.stick_speed = max(state.speed, abs(state.stick_vy))
        else:
            state.stick_vy = 0.0
            state.stick_speed = 0.0

        # 5 PARMAĞIN HER BİRİ İÇİN BAĞIMSIZ FİZİK & TUŞ VURUŞU GÜNCELLEMESİ
        thresh = 0.72 / max(0.4, self.sensitivity)
        for f_idx, lid in enumerate(FINGER_TIP_IDS):
            fg = state.fingers[f_idx]
            nx, ny, _ = norms[lid]
            if was_recently_seen:
                f_rvx = (nx - fg.x) / dt
                f_rvy = (ny - fg.y) / dt
                fg.prev_vy = fg.vy
                fg.vx = 0.38 * fg.vx + 0.62 * f_rvx
                fg.vy = 0.38 * fg.vy + 0.62 * f_rvy
                fg.speed = float(np.hypot(fg.vx, fg.vy))
            else:
                fg.vx = 0.0
                fg.vy = 0.0
                fg.prev_vy = 0.0
                fg.speed = 0.0

            fg.x, fg.y = nx, ny
            fg.px, fg.py = pxs[lid]
            fg.is_extended = ext_mask[f_idx]
            fg.is_downstroke_strike = False

            if (now - fg.last_strike_time) > 0.095:
                f_fast_down = fg.vy > thresh
                f_whip = (fg.prev_vy > thresh * 0.78) and (fg.vy < fg.prev_vy * 0.70)
                if f_fast_down or f_whip:
                    fg.is_downstroke_strike = True
                    peak_fv = max(fg.vy, fg.prev_vy)
                    fg.strike_velocity = float(np.clip((peak_fv - 0.35) / 2.0, 0.45, 1.0))
                    fg.last_strike_time = now

        # El genel vuruş (Strike) tespiti
        state.is_downstroke_strike = False
        if (now - state.last_strike_time) > 0.10:
            eff_vy = max(state.vy, state.stick_vy)
            fast_down = eff_vy > thresh
            whip_snap = (state.prev_vy > thresh * 0.78) and (state.vy < state.prev_vy * 0.68)
            if fast_down or whip_snap:
                state.is_downstroke_strike = True
                peak_v = max(eff_vy, state.prev_vy)
                state.strike_velocity = float(np.clip((peak_v - 0.35) / 2.1, 0.45, 1.0))
                state.last_strike_time = now

        state.last_seen = now

        # Işık izi (Light trail) ekle
        tip_px = pxs[8]
        state.trail.append((tip_px[0], tip_px[1], min(1.0, state.speed / 3.0)))

    @staticmethod
    def _compute_extended_fingers_mask(norms: List[Tuple[float, float, float]]) -> List[bool]:
        if len(norms) < 21:
            return [False] * 5
        mask = [False] * 5
        # Başparmak: ucu (4) ile serçe kökü (17) arasındaki mesafe
        thumb_dist = np.hypot(norms[4][0] - norms[17][0], norms[4][1] - norms[17][1])
        palm_width = np.hypot(norms[5][0] - norms[17][0], norms[5][1] - norms[17][1])
        mask[0] = bool(thumb_dist > palm_width * 1.18)

        # Diğer 4 parmak: uç (tip) bileğe (0), orta eklemden (PIP) daha uzaksa açıktır
        wrist_x, wrist_y, _ = norms[0]
        for idx, (tip_id, pip_id) in enumerate(((8, 6), (12, 10), (16, 14), (20, 18)), start=1):
            d_tip = np.hypot(norms[tip_id][0] - wrist_x, norms[tip_id][1] - wrist_y)
            d_pip = np.hypot(norms[pip_id][0] - wrist_x, norms[pip_id][1] - wrist_y)
            mask[idx] = bool(d_tip > d_pip * 1.06 and norms[tip_id][1] < norms[pip_id][1] + 0.04)
        return mask

    def get_active_hands(self, max_age: float = 0.16) -> List[HandPhysicsState]:
        now = time.perf_counter()
        return [st for st in self.hands_state.values() if (now - st.last_seen) <= max_age]
