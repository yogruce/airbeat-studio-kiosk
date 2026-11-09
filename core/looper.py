"""
Tek Kişilik Orkestra (4 Bar Live Looper)
Kullanıcının çaldığı tek seferlik vuruşları (Bateri, Gitar akoru, Piyano notası, Maestro vuruşu)
4 Bar'lık (varsayılan 8 saniye = 120 BPM) bir döngü üzerinde zaman damgasıyla kaydeder
ve her turda otomatik olarak yeniden çalar. Kullanıcı üst üste katmanlar (Overdub) ekleyebilir.
"""

from dataclasses import dataclass
import time
from typing import Callable, Dict, List


@dataclass
class LoopEvent:
    offset_sec: float
    event_type: str  # "drum", "guitar", "piano", "maestro"
    payload: Dict
    last_triggered_cycle: int = -1


class LiveLooper:
    def __init__(self, loop_duration: float = 8.0) -> None:
        self.loop_duration = loop_duration  # 120 BPM'de 4 Bar = 8.0 saniye
        self.events: List[LoopEvent] = []
        self.is_recording: bool = False
        self.is_playing: bool = True
        self.start_time: float = time.perf_counter()

    def toggle_record(self) -> bool:
        if not self.is_recording and len(self.events) == 0:
            # İlk kayıt başlıyorsa bar başlangıcını sıfırla
            self.start_time = time.perf_counter()
        self.is_recording = not self.is_recording
        return self.is_recording

    def clear(self) -> None:
        self.events.clear()
        self.is_recording = False
        self.start_time = time.perf_counter()

    def get_progress(self) -> float:
        """0.0 ile 1.0 arasında mevcut döngü ilerlemesini döndürür."""
        elapsed = time.perf_counter() - self.start_time
        return (elapsed % self.loop_duration) / self.loop_duration

    def record_event(self, event_type: str, payload: Dict) -> None:
        if not self.is_recording:
            return
        now = time.perf_counter()
        elapsed = now - self.start_time
        cycle = int(elapsed // self.loop_duration)
        offset = elapsed % self.loop_duration
        self.events.append(
            LoopEvent(
                offset_sec=offset,
                event_type=event_type,
                payload=payload,
                last_triggered_cycle=cycle,  # Kaydedildiği anda zaten çalındığı için aynı turda tekrar çalma
            )
        )

    def update(self, replay_callback: Callable[[str, Dict], None]) -> None:
        if not self.is_playing or not self.events:
            return
        now = time.perf_counter()
        elapsed = now - self.start_time
        cycle = int(elapsed // self.loop_duration)
        offset = elapsed % self.loop_duration

        for ev in self.events:
            if ev.last_triggered_cycle < cycle and offset >= ev.offset_sec:
                ev.last_triggered_cycle = cycle
                replay_callback(ev.event_type, ev.payload)
