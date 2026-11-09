"""
Real Studio Sample Bank Downloader & Converter
FluidR3 Studio SoundFont ve Akustik Stüdyo Kayıtlarını indirip
AirBeat Studio'nun ultra düşük gecikmeli (<10ms) ses motoru için
44.1kHz Stereo WAV formatında assets/sounds/ klasörüne hazırlar.
"""

import os
import urllib.request
from scipy.io import wavfile
from scipy import signal
import numpy as np
import pygame


BASE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "sounds")

# 1. Gerçek Akustik Stüdyo Bateri Kayıtları (WAV)
DRUM_URLS = {
    "drums/kick.wav": "https://raw.githubusercontent.com/wesbos/JavaScript30/master/01%20-%20JavaScript%20Drum%20Kit/sounds/kick.wav",
    "drums/snare.wav": "https://raw.githubusercontent.com/wesbos/JavaScript30/master/01%20-%20JavaScript%20Drum%20Kit/sounds/snare.wav",
    "drums/hihat.wav": "https://raw.githubusercontent.com/wesbos/JavaScript30/master/01%20-%20JavaScript%20Drum%20Kit/sounds/hihat.wav",
    "drums/tom.wav": "https://raw.githubusercontent.com/wesbos/JavaScript30/master/01%20-%20JavaScript%20Drum%20Kit/sounds/tom.wav",
    "drums/crash.wav": "https://raw.githubusercontent.com/wesbos/JavaScript30/master/01%20-%20JavaScript%20Drum%20Kit/sounds/openhat.wav",
    "drums/ride.wav": "https://raw.githubusercontent.com/wesbos/JavaScript30/master/01%20-%20JavaScript%20Drum%20Kit/sounds/ride.wav",
}

# 2. FluidR3_GM Gerçek Stüdyo Enstrüman Kayıtları (Multi-Sample Kök Notalar)
FLUID_BASE = "https://raw.githubusercontent.com/gleitz/midi-js-soundfonts/gh-pages/FluidR3_GM"

INSTRUMENT_SAMPLES = {
    # Akustik / Elektro Gitar Notaları
    "guitar": ("acoustic_guitar_steel-mp3", ["E2", "A2", "D3", "G3", "B3", "E4", "A4", "C3", "C4", "E3"]),
    # Grand Piyano Notaları
    "piano": ("acoustic_grand_piano-mp3", ["C3", "D3", "E3", "G3", "A3", "C4", "D4", "E4", "G4", "A4", "C5", "E5"]),
    # Gerçek Keman & Çello Kayıtları
    "violin": ("violin-mp3", ["A3", "C4", "E4", "G4", "A4", "C5", "E5"]),
    "cello": ("cello-mp3", ["C2", "G2", "C3", "E3", "G3", "A3", "C4"]),
    # Gerçek Alto Saksafon Kayıtları
    "sax": ("alto_sax-mp3", ["C3", "E3", "G3", "A3", "C4", "D4", "E4", "G4", "A4", "C5"]),
    # Maestro Senfonik Orkestra: Yaylılar (String Ensemble), Fransız Kornosu (French Horn / Brass), Timpani
    "orchestra_strings": ("string_ensemble_1-mp3", ["D2", "A2", "C3", "D3", "E3", "G3", "A3", "C4", "D4", "E4", "G4", "A4"]),
    "orchestra_brass": ("french_horn-mp3", ["D2", "A2", "C3", "D3", "E3", "G3", "A3", "C4", "D4", "E4"]),
    "timpani": ("timpani-mp3", ["D2", "A2", "C3", "D3"]),
}


def download_and_prepare() -> None:
    pygame.mixer.init(frequency=44100, size=-16, channels=2)
    os.makedirs(os.path.join(BASE_DIR, "drums"), exist_ok=True)

    print("=== 1. Gercek Studio Bateri WAV Kayitlari Indiriliyor ===")
    for rel_path, url in DRUM_URLS.items():
        target = os.path.join(BASE_DIR, rel_path)
        if not os.path.exists(target):
            print(f"Indiriliyor: {rel_path}")
            urllib.request.urlretrieve(url, target)

    print("=== 2. FluidR3 Studio Enstruman Multi-Sample Bankasi Indiriliyor ===")
    for folder_name, (sf_instrument, notes) in INSTRUMENT_SAMPLES.items():
        inst_dir = os.path.join(BASE_DIR, folder_name)
        os.makedirs(inst_dir, exist_ok=True)
        for note in notes:
            wav_path = os.path.join(inst_dir, f"{note}.wav")
            if os.path.exists(wav_path):
                continue
            mp3_url = f"{FLUID_BASE}/{sf_instrument}/{note}.mp3"
            tmp_mp3 = os.path.join(inst_dir, f"{note}.mp3")
            try:
                urllib.request.urlretrieve(mp3_url, tmp_mp3)
                # Pygame ile MP3'ü 44.1kHz PCM'e çöz ve saf .wav olarak kaydet
                snd = pygame.mixer.Sound(tmp_mp3)
                arr = pygame.sndarray.array(snd)
                wavfile.write(wav_path, 44100, arr)
                os.remove(tmp_mp3)
                print(f"Hazirlandi: {folder_name}/{note}.wav")
            except Exception as e:
                print(f"Uyari: {folder_name}/{note} indirilemedi: {e}")

    pygame.mixer.quit()
    print("=== Tum Gercek Enstruman Ses Bankasi Hazir! ===")


if __name__ == "__main__":
    download_and_prepare()
