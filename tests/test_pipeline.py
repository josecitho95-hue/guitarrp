"""Tests de humo del pipeline Audio2Tab (núcleo sin modelos pesados).

Cubren las etapas deterministas y rápidas: digitación (to_tab) + matriz de
inhibición (4b) + export Guitar Pro (to_gp) + carga MIDI. NO requieren torch,
basic-pitch ni mt3-infer, así que corren en segundos.

Ejecutar:  python -m pytest tests/ -q      (o)   python tests/test_pipeline.py
"""
from __future__ import annotations

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import guitarpro as gp  # noqa: E402

from sidecar.pipeline import inhibition, to_gp, to_tab  # noqa: E402
from sidecar.pipeline.types import Note, TabNote  # noqa: E402


def _scale_notes():
    scale = [60, 62, 64, 65, 67, 69, 71, 72]
    return [Note(pitch=p, start=i * 0.5, end=i * 0.5 + 0.45) for i, p in enumerate(scale)]


def _emajor_chord(t=0.0):
    return [Note(pitch=p, start=t, end=t + 0.9) for p in (40, 47, 52, 56, 59, 64)]


# --- Inhibición (etapa 4b) ---

def test_inhibition_rejects_same_string():
    # dos notas en la misma cuerda (1ª): imposible
    assert not inhibition.chord_feasible([(1, 0), (1, 5)])


def test_inhibition_rejects_oversized_span():
    # span > MAX_CHORD_SPAN entre trastes pisados
    big = [(6, 1), (1, 1 + inhibition.MAX_CHORD_SPAN + 2)]
    assert not inhibition.chord_feasible(big)


def test_inhibition_accepts_open_chord():
    # Mi mayor abierto: cada nota en cuerda distinta, span chico
    emaj = [(6, 0), (5, 2), (4, 2), (3, 1), (2, 0), (1, 0)]
    assert inhibition.chord_feasible(emaj)


# --- Digitación (etapa 4) ---

def test_assign_tab_monophonic_in_range():
    tab = to_tab.assign_tab(_scale_notes())
    assert len(tab) == 8
    for tn in tab:
        assert 1 <= tn.string <= 6
        assert 0 <= tn.fret <= to_tab.MAX_FRET
        # la posición debe reproducir la altura pedida
        assert to_tab.STANDARD_TUNING[tn.string] + tn.fret == tn.pitch


def test_assign_tab_emajor_is_playable_open_shape():
    tab = to_tab.assign_tab(_emajor_chord())
    assert len(tab) == 6
    by_string = {tn.string: tn.fret for tn in tab}
    # forma abierta canónica de Mi mayor
    assert by_string == {6: 0, 5: 2, 4: 2, 3: 1, 2: 0, 1: 0}


def test_assign_tab_never_produces_impossible_events():
    import collections
    notes = _scale_notes() + _emajor_chord(t=4.0)
    tab = to_tab.assign_tab(notes)
    events = collections.defaultdict(list)
    for tn in tab:
        events[round(tn.start, 3)].append((tn.string, tn.fret))
    for asg in events.values():
        assert inhibition.chord_feasible(asg)


# --- Export Guitar Pro (etapa 5) ---

def _roundtrip(ext: str):
    tab = to_tab.assign_tab(_scale_notes())
    with tempfile.TemporaryDirectory() as d:
        out = os.path.join(d, f"t{ext}")
        to_gp.write_gp(tab, out, bpm=120, title="Test")
        song = gp.parse(out)
    n = sum(len(b.notes) for m in song.tracks[0].measures
            for v in m.voices[:1] for b in v.beats)
    assert n == len(tab), f"{ext}: {n} notas escritas != {len(tab)}"
    assert song.tempo == 120
    assert len(song.tracks[0].strings) == 6


def test_export_gp5():
    _roundtrip(".gp5")


def test_export_gp4():
    _roundtrip(".gp4")


def test_export_gp3():
    _roundtrip(".gp3")


def test_techniques_legato_and_slides():
    from sidecar.pipeline import techniques
    # Crear dos notas consecutivas en la misma cuerda (1) con diferencia de 1 traste -> HOPO
    n1 = TabNote(pitch=64, start=0.0, end=0.45, string=1, fret=0)
    n2 = TabNote(pitch=65, start=0.46, end=0.9, string=1, fret=1) # start - end = 0.01 <= 0.08

    # Crear dos notas consecutivas con salto de 4 trastes -> Slide (fret > 0 para ambas)
    n3 = TabNote(pitch=66, start=1.0, end=1.45, string=1, fret=2)
    n4 = TabNote(pitch=70, start=1.46, end=1.9, string=1, fret=6) # 6 - 2 = 4 (slide)

    tab = techniques.detect_techniques([n1, n2, n3, n4])
    assert tab[1].hopo is True
    assert tab[1].slide is False
    assert tab[3].slide is True
    assert tab[3].hopo is False


def test_techniques_bend_and_vibrato():
    from sidecar.pipeline import techniques
    # Nota con pitch bends oscilantes -> vibrato
    pb = [(i * 0.05, 500 if i % 2 == 0 else 100) for i in range(10)] # oscilación entre 100 y 500
    n1 = TabNote(pitch=60, start=0.0, end=0.8, string=2, fret=1, pitch_bends=pb)

    # Nota con pitch bend alto -> bend (8191 = 2 semitonos = 4 quarters)
    pb_bend = [(0.0, 0), (0.2, 8191)]
    n2 = TabNote(pitch=60, start=1.0, end=1.8, string=2, fret=1, pitch_bends=pb_bend)

    tab = techniques.detect_techniques([n1, n2])
    assert tab[0].vibrato is True
    assert tab[1].bend_type == "bend"
    assert tab[1].bend_value == 4 # 2 semitonos = 4 quarters


def test_capo_and_tuning_export():
    with tempfile.TemporaryDirectory() as d:
        out = os.path.join(d, "tuning_test.gp5")
        tuning = {1: 64, 2: 59, 3: 55, 4: 50, 5: 45, 6: 38}
        tn = TabNote(pitch=45, start=0.0, end=1.0, string=6, fret=7)

        to_gp.write_gp([tn], out, bpm=120, title="TuningTest", tuning=tuning, capo=2)
        song = gp.parse(out)

        track = song.tracks[0]
        assert track.offset == 2
        assert track.strings[5].value == 38 # Drop D


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
