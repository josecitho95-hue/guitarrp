"""Tests del núcleo añadido en la sesión de calidad (multipista, percusión,
batería, limpieza vocal, cuantización por beats, matriz de inhibición aprendida).

NO requieren modelos pesados ni audio. Ejecutar:
    python tests/test_multitrack.py
"""
from __future__ import annotations

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np  # noqa: E402
import guitarpro as gp  # noqa: E402

from sidecar.pipeline import inhibition, to_gp, to_tab, transcribe  # noqa: E402
from sidecar.pipeline.types import Note, TabNote  # noqa: E402


# --- Multipista ---

def test_multitrack_two_tracks():
    g = [TabNote(pitch=64, start=0.0, end=0.5, string=1, fret=0)]
    b = [TabNote(pitch=43, start=0.0, end=0.5, string=1, fret=0)]
    insts = [
        {"name": "Guitar", "tuning": to_tab.STANDARD_TUNING, "tab_notes": g},
        {"name": "Bass", "tuning": to_tab.BASS_TUNING, "tab_notes": b},
    ]
    song = to_gp.build_multitrack_song(insts, bpm=120, title="MT")
    assert len(song.tracks) == 2
    assert song.tracks[0].name == "Guitar"
    assert song.tracks[1].name == "Bass"
    assert len(song.tracks[0].strings) == 6
    assert len(song.tracks[1].strings) == 4
    assert song.tracks[1].strings[3].value == 28          # bajo: 4ª cuerda = Mi grave (E1)
    # todas las pistas comparten el mismo nº de compases
    assert len(song.tracks[0].measures) == len(song.tracks[1].measures)


def test_multitrack_roundtrip_gp5():
    g = [TabNote(pitch=64, start=0.0, end=0.5, string=1, fret=0)]
    b = [TabNote(pitch=43, start=0.0, end=0.5, string=1, fret=0)]
    insts = [
        {"name": "Guitar", "tuning": to_tab.STANDARD_TUNING, "tab_notes": g},
        {"name": "Bass", "tuning": to_tab.BASS_TUNING, "tab_notes": b},
    ]
    with tempfile.TemporaryDirectory() as d:
        out = os.path.join(d, "mt.gp5")
        to_gp.write_multitrack_gp(insts, out, bpm=120)
        song = gp.parse(out)
    assert [t.name for t in song.tracks] == ["Guitar", "Bass"]
    assert len(song.tracks[1].strings) == 4


# --- Pista de percusión ---

def test_percussion_track():
    drums = [TabNote(pitch=36, start=0.0, end=0.2, string=1, fret=36),
             TabNote(pitch=38, start=0.0, end=0.2, string=2, fret=38)]
    insts = [{"name": "Drums", "tab_notes": drums, "percussion": True}]
    song = to_gp.build_multitrack_song(insts, bpm=120)
    t = song.tracks[0]
    assert t.isPercussionTrack is True
    assert t.channel.channel == 9                          # canal MIDI 10
    values = [n.value for m in t.measures for v in m.voices for b in v.beats for n in b.notes]
    assert 36 in values and 38 in values                   # value = nº MIDI de percusión


# --- assign_drums ---

def test_assign_drums_simultaneous_distinct_strings():
    notes = [Note(pitch=36, start=0.0, end=0.1),           # bombo
             Note(pitch=38, start=0.0, end=0.1),           # caja
             Note(pitch=42, start=0.005, end=0.1)]         # hi-hat (≈ simultáneo)
    tab = to_tab.assign_drums(notes)
    assert len(tab) == 3
    assert len({t.string for t in tab}) == 3               # slots distintos
    assert {t.fret for t in tab} == {36, 38, 42}           # fret = nº percusión


def test_assign_drums_caps_six_hits():
    notes = [Note(pitch=35 + i, start=0.0, end=0.1) for i in range(8)]
    tab = to_tab.assign_drums(notes)
    assert len(tab) == 6                                   # máx 6 golpes simultáneos
    assert all(1 <= t.string <= 6 for t in tab)


# --- Limpieza vocal monofónica ---

def test_monophonic_cleanup_one_note_per_window():
    notes = [Note(pitch=60, start=0.0, end=0.5),
             Note(pitch=64, start=0.02, end=0.3),          # solapa con la anterior
             Note(pitch=67, start=1.0, end=1.5)]
    mono = transcribe.monophonic_cleanup(notes, win=0.08)
    assert len(mono) == 2
    assert mono[0].pitch == 60                             # se conserva la más larga
    assert mono[0].end <= mono[1].start                    # sin solapes


def test_monophonic_cleanup_empty():
    assert transcribe.monophonic_cleanup([]) == []


# --- Cuantización relativa a beats ---

def test_make_to_slot_beats_vs_grid():
    beats = np.array([0.0, 0.5, 1.0, 1.5])                 # negras a 120 BPM
    to_slot = to_gp._make_to_slot(beats, 120.0)
    assert to_slot(0.0) == 0
    assert to_slot(0.5) == 4                               # 1 beat = 4 semicorcheas
    assert to_slot(1.0) == 8
    # sin beats -> grid fijo: (60/120)/4 = 0.125 s/slot
    grid_slot = to_gp._make_to_slot(None, 120.0)
    assert grid_slot(0.5) == 4


# --- Cuantización con tresillos (galope) ---

def _gtr(notes):
    return [{"name": "G", "tuning": to_tab.STANDARD_TUNING, "tab_notes": notes}]


def test_triplets_detected_in_triplet_mode():
    # 3 tresillos de corchea por beat a 120 BPM (beat=0.5s -> 0.1667s c/u).
    notes = []
    for beat in range(4):
        for k in range(3):
            t = beat * 0.5 + k * (0.5 / 3)
            notes.append(TabNote(pitch=60, start=t, end=t + 0.15, string=2, fret=1))
    song = to_gp.build_multitrack_song(_gtr(notes), bpm=120, triplets=True)
    n_trip = sum(1 for m in song.tracks[0].measures for v in m.voices for b in v.beats
                 if b.duration.tuplet and b.duration.tuplet.enters == 3)
    assert n_trip >= 9                                  # la mayoría de los 12 son tresillos


def test_straight_stays_straight_in_triplet_mode():
    # 16ths rectas a 120 BPM (0.125s c/u) -> el sesgo evita falsos tresillos.
    notes = [TabNote(pitch=60, start=i * 0.125, end=i * 0.125 + 0.1, string=2, fret=1)
             for i in range(8)]
    song = to_gp.build_multitrack_song(_gtr(notes), bpm=120, triplets=True)
    n_trip = sum(1 for m in song.tracks[0].measures for v in m.voices for b in v.beats
                 if b.duration.tuplet and b.duration.tuplet.enters == 3)
    assert n_trip == 0


def test_no_measure_overflow_in_triplet_mode():
    # Mezcla de un compás de tresillos + uno de 16ths: ningún compás debe desbordar
    # (los beats deben sumar exactamente la redonda; si no, GP los pinta en rojo).
    notes = []
    for beat in range(4):                                  # compás 1: tresillos
        for k in range(3):
            t = beat * 0.5 + k * (0.5 / 3)
            notes.append(TabNote(pitch=60, start=t, end=t + 0.1, string=2, fret=1))
    for i in range(16):                                    # compás 2: semicorcheas
        t = 2.0 + i * 0.125
        notes.append(TabNote(pitch=62, start=t, end=t + 0.08, string=2, fret=3))
    song = to_gp.build_multitrack_song(_gtr(notes), bpm=120, triplets=True)
    whole = 4 * gp.Duration.quarterTime                    # 4/4 = 4 negras
    for m in song.tracks[0].measures:
        for v in m.voices:
            if v.beats:
                assert abs(sum(b.duration.time for b in v.beats) - whole) <= 1


def test_no_tuplets_in_straight_mode():
    notes = [TabNote(pitch=60, start=i * (0.5 / 3), end=i * (0.5 / 3) + 0.1, string=2, fret=1)
             for i in range(6)]
    song = to_gp.build_multitrack_song(_gtr(notes), bpm=120, triplets=False)
    n_trip = sum(1 for m in song.tracks[0].measures for v in m.voices for b in v.beats
                 if b.duration.tuplet and b.duration.tuplet.enters == 3)
    assert n_trip == 0


# --- Matriz de inhibición aprendida ---

def test_learned_inhibition_penalizes_rare_positions():
    orig = inhibition._LEARNED
    try:
        lp = np.full((6, 24), -6.0, dtype=np.float32)      # todo raro
        lp[0, 0] = -1.0                                     # (cuerda 1, traste 0) muy común
        inhibition._LEARNED = {"pair_logprob": lp}
        c_common = inhibition.chord_cost([(1, 0)])
        c_rare = inhibition.chord_cost([(1, 5)])
        assert c_common < c_rare                            # posición común = menor coste
    finally:
        inhibition._LEARNED = orig


def test_inhibition_no_matrix_is_neutral():
    orig = inhibition._LEARNED
    try:
        inhibition._LEARNED = False                        # fuerza "sin matriz"
        # el coste debe seguir siendo finito y la posición al aire barata
        assert inhibition.chord_cost([(1, 0)]) < inhibition.chord_cost([(1, 12)])
    finally:
        inhibition._LEARNED = orig


# --- Runner standalone (sin pytest) ---

if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS  {t.__name__}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"FAIL  {t.__name__}: {type(exc).__name__}: {exc}")
    print(f"\n{len(tests) - failed}/{len(tests)} tests OK")
    sys.exit(1 if failed else 0)
