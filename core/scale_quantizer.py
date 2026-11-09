"""
Scale Quantizer (Otomatik Gam Kilidi, Melodi Motoru & Do-Re-Mi / C-D-E Nota Gösterimi)
- Türkiye ve Avrupa standartlarına uygun SOLFEJ (Do, Re, Mi, Fa, Sol, La, Si) gösterimi varsayılandır.
- Kullanıcı [N] tuşuyla veya Ayarlar menüsünden:
  1) DO - RE - MI (Solfej - Türkçe)
  2) DO (C) - İkili Gösterim
  3) C - D - E (Uluslararası Harf)
  arasında anında geçiş yapabilir.
- Gerçek melodi çalabilmek için varsayılan mod SOLO NOTA (Melodi) ve varsayılan dizilim
  tam Do-Re-Mi-Fa-Sol-La-Si-Do dizisidir.
"""

from typing import Dict, List, Tuple


class PlayMode:
    """Enstrümanlar için Nota (Melodi) / Akor / Hibrit çalma modları."""
    NOTE_ONLY = 0     # SOLO NOTA / MELODİ Modu (Varsayılan - Gerçek melodi çalmak için)
    CHORD_ONLY = 1    # AKOR Modu (Ritim / Çoklu Ses Armoni)
    HYBRID = 2        # HİBRİT Mod (Hareket şekline veya el bölgesine göre hem Nota hem Akor)

    NAMES = [
        "MELODI (Solo Nota)",
        "AKOR (Chords)",
        "HIBRIT (Nota + Akor)",
    ]


class NoteNamingMode:
    """Nota İsimlendirme Sistemi (Do-Re-Mi vs C-D-E)."""
    SOLFEGE_TR = 0    # Do, Re, Mi, Fa, Sol, La, Si
    DUAL = 1          # Do(C), Re(D), Mi(E)...
    LETTER_EN = 2     # C, D, E, F, G, A, B

    NAMES = [
        "DO-RE-MI (Solfej)",
        "DO(C) (Ikili)",
        "C-D-E (Harf)",
    ]


class ScaleQuantizer:
    NOTE_NAMES_EN = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
    NOTE_NAMES_TR = ['Do', 'Do#', 'Re', 'Re#', 'Mi', 'Fa', 'Fa#', 'Sol', 'Sol#', 'La', 'Si b', 'Si']

    SCALES: Dict[str, Dict] = {
        "Do Major / La Minor (Do-Re-Mi-Fa-Sol-La-Si Tam Melodi)": {
            "root": 60,  # C4 (Orta Do - Melodi çalmak için en doğal başlangıç!)
            "intervals": [
                0, 2, 4, 5, 7, 9, 11, 12,
                14, 16, 17, 19, 21, 23, 24, 26
            ],
            "piano_root": 48,  # Piyanoda Sol El Kalın Do (C3) + Sağ El Orta Do (C4-C5)
            "chords": [
                ("Do (C)",   [60, 64, 67, 72]),
                ("Sol (G)",  [55, 59, 62, 67]),
                ("La m (Am)",[57, 60, 64, 69]),
                ("Fa (F)",   [53, 57, 60, 65]),
                ("Re m (Dm)",[50, 53, 57, 62]),
                ("Mi m (Em)",[52, 55, 59, 64]),
            ],
        },
        "La Minor / Nihavend (Duygusal / Pop-Rock Melodi)": {
            "root": 57,  # A3 (La)
            "intervals": [
                0, 2, 3, 5, 7, 8, 10, 12,
                14, 15, 17, 19, 20, 22, 24, 26
            ],
            "piano_root": 45,
            "chords": [
                ("La m (Am)",[57, 60, 64, 69]),
                ("Fa (F)",   [53, 57, 60, 65]),
                ("Do (C)",   [60, 64, 67, 72]),
                ("Sol (G)",  [55, 59, 62, 67]),
                ("Re m (Dm)",[50, 53, 57, 62]),
                ("Mi m (Em)",[52, 55, 59, 64]),
            ],
        },
        "Hicaz / Anadolu Rock (Mi-Fa-Sol#-La-Si-Do-Re-Mi)": {
            "root": 52,  # E3 (Mi)
            "intervals": [
                0, 1, 4, 5, 7, 8, 10, 12,
                13, 16, 17, 19, 20, 22, 24, 25
            ],
            "piano_root": 52,
            "chords": [
                ("Mi (E)",   [52, 56, 59, 64]),
                ("Fa (F)",   [53, 57, 60, 65]),
                ("Re m (Dm)",[50, 53, 57, 62]),
                ("La m (Am)",[57, 60, 64, 69]),
                ("Sol (G)",  [55, 59, 62, 67]),
                ("Si m (Bm)",[47, 54, 59, 62]),
            ],
        },
        "Re Minor Epik (Film Muzigi / Senfonik Melodi)": {
            "root": 50,  # D3 (Re)
            "intervals": [
                0, 2, 3, 5, 7, 8, 10, 12,
                14, 15, 17, 19, 20, 22, 24, 26
            ],
            "piano_root": 50,
            "chords": [
                ("Re m (Dm)", [50, 57, 62, 65]),
                ("Si b (Bb)", [46, 53, 58, 62]),
                ("Sol m (Gm)",[43, 50, 55, 58]),
                ("La 7 (A7)", [45, 52, 57, 61]),
                ("Fa (F)",    [53, 57, 60, 65]),
                ("Do (C)",    [48, 55, 60, 64]),
            ],
        },
    }

    # Oyuncunun hemen deneyebileceği popüler gerçek melodi rehberleri (Solfej ve Harf karşılıklarıyla)
    MELODY_GUIDES: List[Tuple[str, str, str]] = [
        (
            "1. Neseli Ol (Ode to Joy)",
            "Mi - Mi - Fa - Sol  |  Sol - Fa - Mi - Re  |  Do - Do - Re - Mi  |  Mi - Re - Re",
            "E - E - F - G  |  G - F - E - D  |  C - C - D - E  |  E - D - D",
        ),
        (
            "2. Daha Dun Annemizin (Twinkle)",
            "Do - Do - Sol - Sol  |  La - La - Sol  |  Fa - Fa - Mi - Mi  |  Re - Re - Do",
            "C - C - G - G  |  A - A - G  |  F - F - E - E  |  D - D - C",
        ),
        (
            "3. Baris Manco - Gulpembe",
            "La - Si - Do - Re - Mi  |  Fa - Mi - Re - Do  |  Re - Do - Si - La",
            "A - B - C - D - E  |  F - E - D - C  |  D - C - B - A",
        ),
        (
            "4. Hatirla Sevgili",
            "Mi - Fa - Sol - La - Sol  |  Fa - Mi - Re - Fa - Mi  |  Re - Do - Si - La",
            "E - F - G - A - G  |  F - E - D - F - E  |  D - C - B - A",
        ),
    ]

    def __init__(self) -> None:
        self.scale_names: List[str] = list(self.SCALES.keys())
        self.current_index: int = 0
        # Gerçek melodi çalabilmek için varsayılan mod: MELODİ (Solo Nota)
        self.play_mode: int = PlayMode.NOTE_ONLY
        # Türkiye için varsayılan nota gösterimi: DO - RE - MI (Solfej)
        self.naming_mode: int = NoteNamingMode.SOLFEGE_TR
        self.melody_guide_idx: int = 0

    @property
    def current_scale_name(self) -> str:
        return self.scale_names[self.current_index]

    @property
    def current_scale(self) -> Dict:
        return self.SCALES[self.current_scale_name]

    @property
    def current_play_mode_name(self) -> str:
        return PlayMode.NAMES[self.play_mode]

    @property
    def current_naming_mode_name(self) -> str:
        return NoteNamingMode.NAMES[self.naming_mode]

    def cycle_play_mode(self) -> str:
        self.play_mode = (self.play_mode + 1) % len(PlayMode.NAMES)
        return self.current_play_mode_name

    def cycle_naming_mode(self) -> str:
        self.naming_mode = (self.naming_mode + 1) % len(NoteNamingMode.NAMES)
        return self.current_naming_mode_name

    def cycle_melody_guide(self) -> str:
        self.melody_guide_idx = (self.melody_guide_idx + 1) % len(self.MELODY_GUIDES)
        return self.MELODY_GUIDES[self.melody_guide_idx][0]

    def get_current_melody_guide(self) -> Tuple[str, str]:
        title, solfege_notes, letter_notes = self.MELODY_GUIDES[self.melody_guide_idx]
        notes_str = letter_notes if self.naming_mode == NoteNamingMode.LETTER_EN else solfege_notes
        return title, notes_str

    def next_scale(self) -> str:
        self.current_index = (self.current_index + 1) % len(self.scale_names)
        return self.current_scale_name

    @classmethod
    def midi_to_freq(cls, midi_note: float) -> float:
        return 440.0 * (2.0 ** ((midi_note - 69.0) / 12.0))

    def midi_to_name(self, midi_note: int, show_octave: bool = False) -> str:
        """Seçili nota gösterim moduna (Do-Re-Mi / Do(C) / C-D-E) göre nota ismini döndürür."""
        semi = int(round(midi_note)) % 12
        octave = (int(round(midi_note)) // 12) - 1
        en = self.NOTE_NAMES_EN[semi]
        tr = self.NOTE_NAMES_TR[semi]

        if self.naming_mode == NoteNamingMode.SOLFEGE_TR:
            return f"{tr}{octave}" if show_octave else tr
        elif self.naming_mode == NoteNamingMode.DUAL:
            return f"{tr}({en})"
        else:
            return f"{en}{octave}"

    def get_note_by_index(
        self,
        index: int,
        octave_shift: int = 0,
        for_piano: bool = False,
    ) -> Tuple[float, str, int]:
        """Gam içindeki indekse göre (frekans, seçili_dilde_nota_adı, midi_no) döndürür."""
        scale = self.current_scale
        intervals = scale["intervals"]
        clamped_idx = max(0, min(index, len(intervals) - 1))
        base_root = scale.get("piano_root", scale["root"]) if for_piano else scale["root"]
        midi_note = base_root + intervals[clamped_idx] + (octave_shift * 12)
        midi_note = max(28, min(96, midi_note))
        return self.midi_to_freq(midi_note), self.midi_to_name(midi_note), midi_note

    def get_diatonic_chord_by_index(
        self,
        index: int,
        octave_shift: int = 0,
        for_piano: bool = False,
    ) -> Tuple[str, List[int]]:
        """Herhangi bir gam basamağından uyumlu 3'lü Akor (Kök + 3'lü + 5'li) üretir."""
        scale = self.current_scale
        intervals = scale["intervals"]
        i0 = max(0, min(index, len(intervals) - 5))
        i1 = min(len(intervals) - 1, i0 + 2)
        i2 = min(len(intervals) - 1, i0 + 4)

        base_root = scale.get("piano_root", scale["root"]) if for_piano else scale["root"]
        root_midi = base_root + intervals[i0] + (octave_shift * 12)
        third_midi = base_root + intervals[i1] + (octave_shift * 12)
        fifth_midi = base_root + intervals[i2] + (octave_shift * 12)

        semi = root_midi % 12
        is_minor = (third_midi - root_midi) == 3
        if self.naming_mode == NoteNamingMode.LETTER_EN:
            r_lbl = self.NOTE_NAMES_EN[semi]
        else:
            r_lbl = self.NOTE_NAMES_TR[semi]
        chord_label = f"{r_lbl}m" if is_minor else f"{r_lbl}"
        return chord_label, [root_midi, third_midi, fifth_midi]

    def get_note_by_normalized_y(self, norm_y: float, octave_shift: int = 0) -> Tuple[float, str, int]:
        intervals = self.current_scale["intervals"]
        inverted_y = 1.0 - max(0.0, min(1.0, norm_y))
        idx = int(inverted_y * (len(intervals) - 1) + 0.5)
        return self.get_note_by_index(idx, octave_shift=octave_shift)

    def get_chords(self) -> List[Tuple[str, List[int]]]:
        return self.current_scale["chords"]
