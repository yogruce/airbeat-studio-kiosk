"""
Real Studio Multi-Sample Audio Engine v2 (Kesintisiz Sustain, Legato Crossfade & 64-Ses Polifoni)
Özellikler:
- Gerçek Stüdyo WAV Kayıtları (Drums, Grand Piano, Guitar, Violin, Cello, Alto Sax, Symphonic Strings, Brass, Timpani)
- Ping-Pong Crossfade Loop: Keman, Çello ve Saksafonda ses uzarken (sustain) sıfır çıtırdama (click-free infinite sustain).
- Akustik Rezonans Rezervuarı (Sustain Tail): El yön değiştirirken veya hareket ederken ses ASLA aniden kesilmez;
  elin hareketine göre uzar (sustain & vibrato) ve el durduğunda doğal akustik sönümlemeyle (1.4 sn) yumuşakça biter.
- Hem TEKİL NOTA (Solo) hem de AKOR (3-4 sesli Harmoni) çalma desteği.
"""

import os
import threading
import time
import warnings
from typing import Dict, List, Optional, Tuple
import numpy as np
from scipy.io import wavfile
from scipy.io.wavfile import WavFileWarning

warnings.filterwarnings("ignore", category=WavFileWarning)

try:
    import sounddevice as sd
    HAS_SOUNDDEVICE = True
except ImportError:
    HAS_SOUNDDEVICE = False

import pygame
from core.paths import get_resource_path


NOTE_TO_SEMITONE = {
    "C": 0, "C#": 1, "Db": 1, "D": 2, "D#": 3, "Eb": 3,
    "E": 4, "F": 5, "F#": 6, "Gb": 6, "G": 7, "G#": 8,
    "Ab": 8, "A": 9, "A#": 10, "Bb": 10, "B": 11,
}


def note_str_to_midi(note_str: str) -> int:
    note_str = note_str.strip()
    if len(note_str) >= 2 and note_str[-2] == "-":
        pitch = note_str[:-2]
        octave = -int(note_str[-1])
    else:
        pitch = note_str[:-1]
        octave = int(note_str[-1])
    return (octave + 1) * 12 + NOTE_TO_SEMITONE.get(pitch, 0)


class Voice:
    """Tek bir tetiklenmiş gerçek ses örneğini (WAV buffer) ve dinamik uzama (sustain) zarfını tutar."""
    def __init__(
        self,
        samples: np.ndarray,
        volume: float = 0.85,
        pan: float = 0.5,
        tag: str = "",
        sustain_loop: Optional[np.ndarray] = None,
    ) -> None:
        self.samples = samples
        self.length = len(self.samples)
        self.cursor = 0
        self.volume = float(np.clip(volume, 0.0, 1.4))
        self.left_gain = float(np.cos(pan * np.pi / 2.0) * self.volume)
        self.right_gain = float(np.sin(pan * np.pi / 2.0) * self.volume)
        self.tag = tag
        # El hareket ettikçe uzayan ses (sustain hold) için
        self.sustain_loop = sustain_loop
        self.sustain_cursor = 0
        self.hold_energy: float = 0.0  # > 0 ise el hareketiyle ses uzamaya devam eder


class AudioEngine:
    SAMPLE_RATE = 44100
    BLOCK_SIZE = 512  # ~11.6ms düşük gecikme tamponu

    def __init__(self) -> None:
        self.voices: List[Voice] = []
        self.lock = threading.Lock()

        # Gerçek WAV Sample Bankaları
        self.drum_samples: Dict[str, np.ndarray] = {}
        self.multi_samples: Dict[str, List[Tuple[int, np.ndarray]]] = {}
        self.pitched_cache: Dict[Tuple[str, int], np.ndarray] = {}
        # Sonsuz pürüzsüz sustain için Ping-Pong Loop önbelleği
        self.seamless_loop_cache: Dict[Tuple[str, int], np.ndarray] = {}

        # Sürekli (Continuous) Enstrüman Motoru (Keman, Çello, Saksafon, Gitar Sustain, Maestro)
        self.cont_active: bool = False
        self.cont_timbre: str = "violin"
        self.cont_target_midi: int = 69
        self.cont_chord_midis: List[int] = []
        self.cont_target_vol: float = 0.0
        self.cont_current_vol: float = 0.0
        self.cont_sustain_reservoir: float = 0.0  # El dursa bile sesi aniden kesmeyen rezonans enerjisi
        self.cont_last_input_time: float = 0.0
        self.cont_vibrato_depth: float = 0.0
        self.cont_phase: float = 0.0
        self.cont_richness: float = 0.5

        # Legato (notadan notaya kesintisiz geçiş) için aktif ve önceki tamponlar
        self.cont_cursor: float = 0.0
        self.cont_prev_cursor: float = 0.0
        self.cont_crossfade: float = 1.0  # 0.0 -> 1.0 arası yumuşak nota geçişi
        self.cont_active_buf: Optional[np.ndarray] = None
        self.cont_prev_buf: Optional[np.ndarray] = None
        self.cont_harmony_bufs: List[np.ndarray] = []
        self.cont_harmony_cursors: List[float] = [0.0, 0.0, 0.0]
        self.cont_brass_buf: Optional[np.ndarray] = None
        self.cont_brass_cursor: float = 0.0

        self.mic_rms: float = 0.0
        self.output_devices: List[Tuple[int, str]] = []
        self.current_output_device_idx: int = 0
        self.input_devices: List[Tuple[int, str]] = []
        self.current_input_device_idx: int = 0
        self.master_volume: float = 1.0

        self._enumerate_audio_devices()
        self._load_real_studio_samples()

        self.stream: Optional[sd.OutputStream] = None
        self.input_stream: Optional[sd.InputStream] = None
        self.use_pygame_fallback = False
        self._start_audio_stream()

    def _enumerate_audio_devices(self) -> None:
        if not HAS_SOUNDDEVICE:
            self.output_devices = [(-1, "Varsayilan Sistem Sesi")]
            self.input_devices = [(-1, "Varsayilan Mikrofon")]
            return

        try:
            devs = sd.query_devices()
            default_in, default_out = sd.default.device
            seen_out_names = set()
            seen_in_names = set()

            if default_out is not None and default_out >= 0:
                d_info = devs[default_out]
                self.output_devices.append((default_out, f"Varsayilan: {d_info['name'][:34]}"))
                seen_out_names.add(d_info["name"][:22])

            for idx, d in enumerate(devs):
                name_short = d["name"][:34]
                key_prefix = d["name"][:22]
                if d["max_output_channels"] >= 2 and key_prefix not in seen_out_names and idx < 28:
                    self.output_devices.append((idx, name_short))
                    seen_out_names.add(key_prefix)
                if d["max_input_channels"] >= 1 and key_prefix not in seen_in_names and idx < 28:
                    self.input_devices.append((idx, name_short))
                    seen_in_names.add(key_prefix)
        except Exception as e:
            print(f"[AudioEngine] Cihaz listeleme hatasi: {e}")

        if not self.output_devices:
            self.output_devices = [(-1, "Varsayilan Hoparlor")]
        if not self.input_devices:
            self.input_devices = [(-1, "Varsayilan Mikrofon")]

    @property
    def current_output_name(self) -> str:
        return self.output_devices[self.current_output_device_idx][1]

    @property
    def current_input_name(self) -> str:
        return self.input_devices[self.current_input_device_idx][1]

    def cycle_output_device(self) -> str:
        self.current_output_device_idx = (self.current_output_device_idx + 1) % len(self.output_devices)
        self.restart_streams()
        self.trigger_drum("snare", velocity=0.9, pan=0.5)
        return self.current_output_name

    def cycle_input_device(self) -> str:
        self.current_input_device_idx = (self.current_input_device_idx + 1) % len(self.input_devices)
        self.restart_streams()
        return self.current_input_name

    def restart_streams(self) -> None:
        self.close()
        self._start_audio_stream()

    def _load_wav_mono_float(self, path: str) -> Optional[np.ndarray]:
        if not os.path.exists(path):
            return None
        try:
            sr, data = wavfile.read(path)
            if data.dtype == np.int16:
                arr = data.astype(np.float32) / 32768.0
            elif data.dtype == np.int32:
                arr = data.astype(np.float32) / 2147483648.0
            elif data.dtype == np.uint8:
                arr = (data.astype(np.float32) - 128.0) / 128.0
            else:
                arr = data.astype(np.float32)

            if arr.ndim == 2:
                arr = arr.mean(axis=1)

            if sr != self.SAMPLE_RATE and len(arr) > 10:
                new_len = int(len(arr) * self.SAMPLE_RATE / sr)
                x_old = np.linspace(0.0, 1.0, len(arr), dtype=np.float32)
                x_new = np.linspace(0.0, 1.0, new_len, dtype=np.float32)
                arr = np.interp(x_new, x_old, arr).astype(np.float32)

            peak = float(np.max(np.abs(arr)))
            if peak > 0.01:
                arr = (arr / peak) * 0.92
            return arr.astype(np.float32)
        except Exception as e:
            print(f"[AudioEngine] WAV okuma hatasi ({path}): {e}")
            return None

    def _load_real_studio_samples(self) -> None:
        sounds_root = get_resource_path(os.path.join("assets", "sounds"))

        drums_dir = os.path.join(sounds_root, "drums")
        for key in ("kick", "snare", "hihat", "tom", "crash", "ride"):
            wav_p = os.path.join(drums_dir, f"{key}.wav")
            arr = self._load_wav_mono_float(wav_p)
            if arr is not None:
                self.drum_samples[key] = arr

        for inst_folder in (
            "guitar",
            "piano",
            "violin",
            "cello",
            "sax",
            "orchestra_strings",
            "orchestra_brass",
            "timpani",
        ):
            inst_dir = os.path.join(sounds_root, inst_folder)
            bank: List[Tuple[int, np.ndarray]] = []
            if os.path.isdir(inst_dir):
                for fname in os.listdir(inst_dir):
                    if fname.lower().endswith(".wav"):
                        note_name = os.path.splitext(fname)[0]
                        midi_num = note_str_to_midi(note_name)
                        arr = self._load_wav_mono_float(os.path.join(inst_dir, fname))
                        if arr is not None:
                            bank.append((midi_num, arr))
            bank.sort(key=lambda x: x[0])
            self.multi_samples[inst_folder] = bank

        print(
            f"[AudioEngine] Gercek Studio Ses Bankasi Hazir: "
            f"{len(self.drum_samples)} Bateri WAV, "
            f"{sum(len(v) for v in self.multi_samples.values())} Enstruman Multi-Sample WAV."
        )

    def _get_pitched_sample(self, inst_name: str, target_midi: int) -> Optional[np.ndarray]:
        target_midi = int(np.clip(target_midi, 24, 96))
        cache_key = (inst_name, target_midi)
        if cache_key in self.pitched_cache:
            return self.pitched_cache[cache_key]

        bank = self.multi_samples.get(inst_name, [])
        if not bank:
            return None

        best_midi, base_arr = min(bank, key=lambda item: abs(item[0] - target_midi))
        semitone_diff = target_midi - best_midi

        if semitone_diff == 0:
            self.pitched_cache[cache_key] = base_arr
            return base_arr

        ratio = 2.0 ** (semitone_diff / 12.0)
        new_len = max(256, int(len(base_arr) / ratio))
        indices = np.linspace(0, len(base_arr) - 1, new_len, dtype=np.float32)
        idx_floor = np.floor(indices).astype(np.int32)
        idx_ceil = np.minimum(idx_floor + 1, len(base_arr) - 1)
        frac = indices - idx_floor
        pitched = (base_arr[idx_floor] * (1.0 - frac) + base_arr[idx_ceil] * frac).astype(np.float32)

        self.pitched_cache[cache_key] = pitched
        return pitched

    def _get_seamless_sustain_loop(self, inst_name: str, target_midi: int) -> Optional[np.ndarray]:
        """
        Sesin el hareketiyle kesintisiz uzaması (sustain) için WAV örneğinin gövde kısmından
        çıtırtısız (crossfaded ping-pong) sonsuz döngü tamponu üretir.
        """
        target_midi = int(np.clip(target_midi, 24, 96))
        key = (inst_name, target_midi)
        if key in self.seamless_loop_cache:
            return self.seamless_loop_cache[key]

        raw = self._get_pitched_sample(inst_name, target_midi)
        if raw is None or len(raw) < 2048:
            return raw

        s_start = int(len(raw) * 0.16)
        s_end = int(len(raw) * 0.76)
        body = raw[s_start:s_end].copy()
        if len(body) < 1024:
            body = raw.copy()

        # Seviye dengeleme (sustain boyunca sesin düşmemesi için)
        rms = float(np.sqrt(np.mean(np.square(body))) + 1e-5)
        body = np.clip((body / rms) * 0.30, -0.95, 0.95)

        # İleri + Geri (Ping-Pong) ve uçlarda pürüzsüz crossfade
        rev = body[::-1].copy()
        xfade = min(2048, len(body) // 4)
        fade_in = np.linspace(0.0, 1.0, xfade, dtype=np.float32)
        fade_out = 1.0 - fade_in

        part1 = body[xfade:-xfade]
        xf1 = body[-xfade:] * fade_out + rev[:xfade] * fade_in
        part2 = rev[xfade:-xfade]
        xf2 = rev[-xfade:] * fade_out + body[:xfade] * fade_in
        seamless = np.concatenate([part1, xf1, part2, xf2]).astype(np.float32)

        self.seamless_loop_cache[key] = seamless
        return seamless

    def _start_audio_stream(self) -> None:
        if HAS_SOUNDDEVICE:
            try:
                out_dev_id = self.output_devices[self.current_output_device_idx][0]
                out_arg = None if out_dev_id < 0 else out_dev_id
                self.stream = sd.OutputStream(
                    device=out_arg,
                    samplerate=self.SAMPLE_RATE,
                    blocksize=self.BLOCK_SIZE,
                    channels=2,
                    dtype="float32",
                    latency="low",
                    callback=self._audio_callback,
                )
                self.stream.start()
                try:
                    in_dev_id = self.input_devices[self.current_input_device_idx][0]
                    in_arg = None if in_dev_id < 0 else in_dev_id
                    self.input_stream = sd.InputStream(
                        device=in_arg,
                        samplerate=self.SAMPLE_RATE,
                        blocksize=1024,
                        channels=1,
                        dtype="float32",
                        callback=self._mic_callback,
                    )
                    self.input_stream.start()
                except Exception:
                    self.input_stream = None
                return
            except Exception as e:
                print(f"[AudioEngine] sounddevice baslatilamadi ({e}), pygame fallback kullaniliyor.")

        self.use_pygame_fallback = True
        pygame.mixer.pre_init(self.SAMPLE_RATE, -16, 2, 512)
        pygame.mixer.init()
        pygame.mixer.set_num_channels(64)

    def _mic_callback(self, indata: np.ndarray, frames: int, time_info, status) -> None:
        rms = float(np.sqrt(np.mean(np.square(indata))))
        self.mic_rms = 0.7 * self.mic_rms + 0.3 * min(1.0, rms * 18.0)

    def _audio_callback(self, outdata: np.ndarray, frames: int, time_info, status) -> None:
        outdata.fill(0.0)
        dt_block = frames / float(self.SAMPLE_RATE)

        # 1. Polifonik Sesler (Piyano, Gitar, Bateri) + El Hareketiyle Sustain Uzatma
        with self.lock:
            active_voices = []
            for v in self.voices:
                rem = v.length - v.cursor
                if rem > 0:
                    count = min(frames, rem)
                    chunk = v.samples[v.cursor : v.cursor + count]
                    outdata[:count, 0] += chunk * v.left_gain
                    outdata[:count, 1] += chunk * v.right_gain
                    v.cursor += count
                    if v.cursor < v.length or v.hold_energy > 0.02:
                        active_voices.append(v)
                elif v.hold_energy > 0.02 and v.sustain_loop is not None and len(v.sustain_loop) > 512:
                    # El hareket ettiği / tuşa basılı tutulduğu sürece sesi uzat!
                    loop_b = v.sustain_loop
                    l_len = len(loop_b)
                    idx = (v.sustain_cursor + np.arange(frames)) % l_len
                    v.sustain_cursor = (v.sustain_cursor + frames) % l_len
                    chunk = loop_b[idx] * v.hold_energy
                    outdata[:, 0] += chunk * v.left_gain
                    outdata[:, 1] += chunk * v.right_gain
                    v.hold_energy = max(0.0, v.hold_energy - dt_block * 1.1)
                    if v.hold_energy > 0.02:
                        active_voices.append(v)
            self.voices = active_voices

        # 2. Sürekli (Continuous) Keman, Çello, Saksafon, Gitar Sustain & Orkestra Motoru
        # Akustik Rezonans Rezervuarı sayesinde el anlık yavaşlasa bile ses ASLA küt diye kesilmez!
        if self.cont_active:
            self.cont_sustain_reservoir = max(self.cont_sustain_reservoir * 0.97, self.cont_target_vol)
        else:
            # El tamamen çekildiğinde doğal akustik sönümleme (~1.2 saniye yumuşak uzama)
            self.cont_sustain_reservoir = max(0.0, self.cont_sustain_reservoir - dt_block * 0.85)

        effective_target_v = max(self.cont_target_vol if self.cont_active else 0.0, self.cont_sustain_reservoir)

        if self.cont_current_vol > 0.001 or effective_target_v > 0.001:
            # Yumuşak ses zarfı (ani sıçrama veya kesilmeyi önler)
            slewed_target = self.cont_current_vol + (effective_target_v - self.cont_current_vol) * min(1.0, dt_block * 18.0)
            vol_env = np.linspace(self.cont_current_vol, slewed_target, frames, dtype=np.float32)
            self.cont_current_vol = float(vol_env[-1])

            buf = self.cont_active_buf
            if buf is not None and len(buf) > 512:
                l_len = len(buf)
                # El hareketine bağlı doğal Vibrato (frekans salınımı)
                self.cont_phase += dt_block * 5.8 * 2.0 * np.pi
                vib_rate = 1.0 + float(np.sin(self.cont_phase)) * self.cont_vibrato_depth * 0.014

                steps = np.arange(frames, dtype=np.float32) * vib_rate
                idx_f = (self.cont_cursor + steps) % l_len
                idx_i = idx_f.astype(np.int32)
                self.cont_cursor = float((self.cont_cursor + frames * vib_rate) % l_len)
                sig = buf[idx_i]

                # Legato nota değişimi sırasında önceki notayla yumuşak crossfade (çıtırtıyı %100 yok eder)
                if self.cont_crossfade < 1.0 and self.cont_prev_buf is not None and len(self.cont_prev_buf) > 512:
                    pl_len = len(self.cont_prev_buf)
                    p_idx = ((int(self.cont_prev_cursor) + np.arange(frames)) % pl_len)
                    self.cont_prev_cursor = float((int(self.cont_prev_cursor) + frames) % pl_len)
                    cf_end = min(1.0, self.cont_crossfade + dt_block * 14.0)
                    cf_vec = np.linspace(self.cont_crossfade, cf_end, frames, dtype=np.float32)
                    self.cont_crossfade = float(cf_end)
                    sig = sig * cf_vec + self.cont_prev_buf[p_idx] * (1.0 - cf_vec)

                # Eğer AKOR (Harmony) modundaysa diğer akor notalarını da karıştır
                if self.cont_harmony_bufs:
                    harm_mix = np.zeros(frames, dtype=np.float32)
                    for h_i, h_buf in enumerate(self.cont_harmony_bufs):
                        if h_buf is not None and len(h_buf) > 512:
                            hl = len(h_buf)
                            hc = self.cont_harmony_cursors[h_i % len(self.cont_harmony_cursors)]
                            h_idx = (int(hc) + np.arange(frames)) % hl
                            self.cont_harmony_cursors[h_i % len(self.cont_harmony_cursors)] = float((int(hc) + frames) % hl)
                            harm_mix += h_buf[h_idx] * 0.55
                    sig = sig * 0.65 + harm_mix

                sig = sig * vol_env * 0.90

                # Maestro modunda Fransız Kornosu (Brass) katmanı
                if self.cont_timbre == "orchestra" and self.cont_brass_buf is not None and self.cont_richness > 0.25:
                    b_buf = self.cont_brass_buf
                    b_len = len(b_buf)
                    b_idx = (int(self.cont_brass_cursor) + np.arange(frames)) % b_len
                    self.cont_brass_cursor = float((int(self.cont_brass_cursor) + frames) % b_len)
                    sig = sig + b_buf[b_idx] * vol_env * self.cont_richness * 0.70

                outdata[:, 0] += sig * 0.96
                outdata[:, 1] += sig * 1.04

        outdata *= self.master_volume
        np.tanh(outdata, out=outdata)

    # -------------------------------------------------------------------------
    # GERÇEK SAMPLE & SUSTAIN TETİKLEME METOTLARI
    # -------------------------------------------------------------------------
    def _play_buffer(
        self,
        samples: Optional[np.ndarray],
        volume: float = 0.85,
        pan: float = 0.5,
        tag: str = "",
        sustain_loop: Optional[np.ndarray] = None,
        hold_energy: float = 0.0,
    ) -> None:
        if samples is None or len(samples) == 0:
            return
        if not self.use_pygame_fallback:
            with self.lock:
                if len(self.voices) > 64:
                    self.voices.pop(0)
                v = Voice(samples, volume=volume, pan=pan, tag=tag, sustain_loop=sustain_loop)
                v.hold_energy = hold_energy
                self.voices.append(v)
        else:
            stereo = np.column_stack((samples * volume, samples * volume))
            pcm = (np.clip(stereo, -1.0, 1.0) * 32767).astype(np.int16)
            snd = pygame.sndarray.make_sound(pcm)
            snd.play()

    def extend_sustain_by_tag(self, tag_prefix: str, energy: float = 0.65) -> None:
        """El hareket ettikçe çalmakta olan Piyano veya Gitar notalarının sesini uzatır!"""
        with self.lock:
            for v in self.voices:
                if v.tag.startswith(tag_prefix):
                    v.hold_energy = max(v.hold_energy, float(np.clip(energy, 0.0, 0.95)))

    def trigger_drum(self, drum_type: str, velocity: float = 0.85, pan: float = 0.5) -> None:
        samples = self.drum_samples.get(drum_type)
        if samples is not None:
            self._play_buffer(samples, volume=velocity * 1.18, pan=pan, tag=f"drum_{drum_type}")

    def trigger_guitar_note(self, midi_note: int, velocity: float = 0.85, pan: float = 0.5) -> None:
        """Gitar Solo / Lead Modu için tekil tel notası + el hareketiyle uzayan sustain kuyruğu!"""
        s = self._get_pitched_sample("guitar", midi_note)
        loop_s = self._get_seamless_sustain_loop("guitar", midi_note)
        if s is not None:
            self._play_buffer(
                s,
                volume=velocity * 1.15,
                pan=pan,
                tag=f"guitar_{midi_note}",
                sustain_loop=loop_s,
                hold_energy=velocity * 0.55,
            )

    def trigger_guitar_chord(self, midi_notes: List[int], velocity: float = 0.85, upstroke: bool = False) -> None:
        """Gerçek çelik telli gitar kayıtlarını pena yönüne göre arpej (strum) ile çalar."""
        notes = list(reversed(midi_notes)) if upstroke else list(midi_notes)
        strum_gap = int(self.SAMPLE_RATE * 0.014)

        layers = []
        max_len = 0
        for idx, m in enumerate(notes):
            s = self._get_pitched_sample("guitar", m)
            if s is not None:
                start = idx * strum_gap
                layers.append((start, s))
                max_len = max(max_len, start + len(s))

        if max_len > 0:
            chord_buf = np.zeros(max_len, dtype=np.float32)
            for start, s in layers:
                chord_buf[start : start + len(s)] += s * 0.48
            root_loop = self._get_seamless_sustain_loop("guitar", notes[0]) if notes else None
            self._play_buffer(
                chord_buf,
                volume=velocity * 1.05,
                pan=0.5,
                tag="guitar_chord",
                sustain_loop=root_loop,
                hold_energy=velocity * 0.45,
            )

    def trigger_piano_note(self, freq: float, velocity: float = 0.85, pan: float = 0.5, key_id: int = -1) -> None:
        midi_note = int(round(69.0 + 12.0 * np.log2(max(20.0, freq) / 440.0)))
        samples = self._get_pitched_sample("piano", midi_note)
        loop_s = self._get_seamless_sustain_loop("piano", midi_note)
        self._play_buffer(
            samples,
            volume=velocity * 1.12,
            pan=pan,
            tag=f"piano_{key_id if key_id >= 0 else midi_note}",
            sustain_loop=loop_s,
            hold_energy=velocity * 0.50,
        )

    def trigger_piano_chord(self, midi_notes: List[int], velocity: float = 0.85, pan: float = 0.5, key_id: int = -1) -> None:
        """Piyano Akor Modunda tek dokunuşla zengin 3-4 sesli Grand Piano akoru çalar."""
        for idx, m in enumerate(midi_notes):
            s = self._get_pitched_sample("piano", m)
            loop_s = self._get_seamless_sustain_loop("piano", m) if idx == 0 else None
            note_pan = float(np.clip(pan + (idx - 1) * 0.08, 0.1, 0.9))
            self._play_buffer(
                s,
                volume=velocity * 0.78,
                pan=note_pan,
                tag=f"piano_{key_id if key_id >= 0 else m}",
                sustain_loop=loop_s,
                hold_energy=velocity * 0.45 if idx == 0 else 0.0,
            )

    def trigger_maestro_beat(self, midi_notes: List[int], velocity: float = 0.9, richness: float = 0.7) -> None:
        for i, m in enumerate(midi_notes):
            pan = 0.25 + 0.5 * (i / max(1, len(midi_notes) - 1))
            str_sample = self._get_pitched_sample("orchestra_strings", m)
            self._play_buffer(str_sample, volume=velocity * 0.58, pan=pan, tag="maestro_str")

            if richness > 0.35:
                brass_sample = self._get_pitched_sample("orchestra_brass", m)
                self._play_buffer(brass_sample, volume=velocity * richness * 0.52, pan=1.0 - pan, tag="maestro_brass")

        if richness > 0.50 and midi_notes:
            timp_sample = self._get_pitched_sample("timpani", midi_notes[0] - 12)
            self._play_buffer(timp_sample, volume=velocity * richness * 0.95, pan=0.35, tag="maestro_timp")

    def update_continuous(
        self,
        active: bool,
        freq: float = 440.0,
        volume: float = 0.0,
        timbre: str = "violin",
        richness: float = 0.5,
        chord_midis: Optional[List[int]] = None,
        vibrato: float = 0.2,
    ) -> None:
        """
        Gerçek Keman, Çello, Saksafon ve Senfoni Orkestrası kayıtlarını
        KESİNTİSİZ (Sustain Reservoir + Legato Crossfade) ve NOTA veya AKOR olarak çalar.
        """
        if not active or volume <= 0.01:
            self.cont_active = False
            self.cont_target_vol = 0.0
            return

        midi_note = int(round(69.0 + 12.0 * np.log2(max(20.0, freq) / 440.0)))
        folder_map = {
            "violin": "violin",
            "cello": "cello",
            "sax": "sax",
            "guitar": "guitar",
            "orchestra": "orchestra_strings",
        }
        inst_folder = folder_map.get(timbre, "violin")

        # Nota veya enstrüman değiştiğinde önceki tamponu sakla ve yumuşak Legato Crossfade başlat!
        if midi_note != self.cont_target_midi or timbre != self.cont_timbre or self.cont_active_buf is None:
            if self.cont_active_buf is not None and timbre == self.cont_timbre:
                self.cont_prev_buf = self.cont_active_buf
                self.cont_prev_cursor = self.cont_cursor
                self.cont_crossfade = 0.0
            self.cont_target_midi = midi_note
            self.cont_timbre = timbre
            self.cont_active_buf = self._get_seamless_sustain_loop(inst_folder, midi_note)
            if timbre == "orchestra":
                self.cont_brass_buf = self._get_seamless_sustain_loop("orchestra_brass", midi_note)

        # Akor (Harmony) modu aktifse ek ses katmanlarını hazırla
        if chord_midis and len(chord_midis) > 1:
            if chord_midis != self.cont_chord_midis:
                self.cont_chord_midis = list(chord_midis)
                self.cont_harmony_bufs = []
                for cm in chord_midis[1:3]:
                    hb = self._get_seamless_sustain_loop(inst_folder, cm)
                    if hb is not None:
                        self.cont_harmony_bufs.append(hb)
        else:
            self.cont_chord_midis = []
            self.cont_harmony_bufs = []

        self.cont_active = True
        self.cont_target_vol = float(np.clip(volume, 0.0, 1.0))
        self.cont_sustain_reservoir = max(self.cont_sustain_reservoir, self.cont_target_vol)
        self.cont_richness = float(np.clip(richness, 0.0, 1.0))
        self.cont_vibrato_depth = float(np.clip(vibrato, 0.0, 1.0))
        self.cont_last_input_time = time.perf_counter()

    def stop_all_continuous(self) -> None:
        self.cont_active = False
        self.cont_target_vol = 0.0
        self.cont_sustain_reservoir = 0.0
        with self.lock:
            for v in self.voices:
                v.hold_energy = 0.0

    def close(self) -> None:
        if self.stream is not None:
            try:
                self.stream.stop()
                self.stream.close()
            except Exception:
                pass
            self.stream = None
        if self.input_stream is not None:
            try:
                self.input_stream.stop()
                self.input_stream.close()
            except Exception:
                pass
            self.input_stream = None
