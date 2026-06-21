"""Evalúa la calidad de la DIGITACIÓN (cuerda/traste) contra el GP oficial.

Aísla la decisión de digitación de la transcripción: toma las notas reales del
oficial (pitch + tiempo), las pasa por nuestro `assign_tab` y mide qué % coincide
con la cuerda/traste que el oficial realmente usa. Compara con y sin la matriz de
inhibición data-driven (`models/inhibition.npz`).

Uso:
    python scripts/eval_fretting.py "OFICIAL.gp3" [--track 0]
"""
from __future__ import annotations

import argparse

import guitarpro as gp

from compare_gp import build_tempo_map, tick_to_seconds, measure_ticks  # noqa: E402
from sidecar.pipeline import inhibition, to_tab
from sidecar.pipeline.types import Note


def extract_official(song, track_idx: int):
    """[(pitch, onset_s, string, fret)] de una pista, con tiempo real."""
    tmap = build_tempo_map(song)
    track = song.tracks[track_idx]
    out = []
    gtick = 0
    for m in track.measures:
        mstart = gtick
        for v in m.voices:
            btick = mstart
            for beat in v.beats:
                if beat.notes:
                    onset = tick_to_seconds(btick, tmap)
                    for n in beat.notes:
                        if n.type.name == "normal":
                            out.append((int(n.realValue), onset, int(n.string), int(n.value)))
                btick += beat.duration.time
        gtick += measure_ticks(m.header)
    return out


def agreement(official, use_matrix: bool):
    # Controlar la matriz aprendida vía el cache del módulo.
    inhibition._LEARNED = None if use_matrix else False
    if use_matrix:
        inhibition._load_learned()

    notes = [Note(pitch=p, start=t, end=t + 0.25) for (p, t, _, _) in official]
    tab = to_tab.assign_tab(notes, tuning=to_tab.STANDARD_TUNING)

    # Emparejar por (pitch, onset) — assign_tab conserva pitch/start.
    ours = {}
    for tn in tab:
        ours[(tn.pitch, round(tn.start, 3))] = (tn.string, tn.fret)

    exact = strok = total = 0
    for (p, t, s_off, f_off) in official:
        key = (p, round(t, 3))
        if key not in ours:
            continue
        total += 1
        s_our, f_our = ours[key]
        if s_our == s_off:
            strok += 1
            if f_our == f_off:
                exact += 1
    return exact, strok, total


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ref")
    ap.add_argument("--track", type=int, default=0)
    args = ap.parse_args()

    song = gp.parse(args.ref)
    official = extract_official(song, args.track)
    print(f"Oficial pista {args.track}: {len(official)} notas\n")

    for use in (False, True):
        ex, sk, tot = agreement(official, use)
        tag = "CON matriz data-driven" if use else "SIN matriz (heurística)"
        if tot:
            print(f"{tag}:")
            print(f"  acuerdo cuerda+traste: {100*ex/tot:.1f}%  ({ex}/{tot})")
            print(f"  acuerdo de cuerda:     {100*sk/tot:.1f}%")


if __name__ == "__main__":
    main()
