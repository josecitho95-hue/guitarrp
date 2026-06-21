"""Detecta y muestra la estructura (riffs repetidos) de una transcripción.

Usa los beats reales del audio + las notas de un GP. Demuestra el cimiento de UX-04
("arregla un riff una vez, propágalo a sus repeticiones").

Uso:
    python scripts/detect_structure.py CANCION.gp5 AUDIO.mp3 [--tracks 0,1]
"""
from __future__ import annotations

import argparse
import json

import guitarpro as gp

from compare_gp import extract_notes
from sidecar.pipeline import preprocess, structure


class _N:
    def __init__(self, start, pitch):
        self.start = start
        self.pitch = pitch


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("gp")
    ap.add_argument("audio")
    ap.add_argument("--tracks", default="0")
    ap.add_argument("--out", help="Guardar structure.json")
    args = ap.parse_args()

    tracks = [int(x) for x in args.tracks.split(",")]
    song = gp.parse(args.gp)
    notes = [_N(o, p) for (o, _d, p) in extract_notes(song, tracks)]

    bpm = preprocess.estimate_tempo(args.audio)
    beats, _ = preprocess.estimate_beats(args.audio, target_bpm=bpm)
    st = structure.detect_structure(notes, beats)

    n_bars = len(st["bars"])
    n_rep = st["n_repeated_clusters"]
    in_rep = sum(1 for b in st["bars"] if b["cluster"] >= 0)
    print(f"Compases: {n_bars} | clusters de riffs repetidos: {n_rep}")
    print(f"Compases que pertenecen a un riff repetido: {in_rep} "
          f"({100 * in_rep // max(n_bars, 1)}%)")
    print("\nTop riffs (cluster: nº de repeticiones):")
    for c in sorted(st["clusters"], key=lambda c: -c["size"])[:8]:
        bars = c["bars"]
        print(f"  riff #{c['id']}: {c['size']} repeticiones  "
              f"(compases {bars[0]}..{bars[-1]})")

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(st, f, indent=2)
        print(f"\nEstructura guardada -> {args.out}")


if __name__ == "__main__":
    main()
