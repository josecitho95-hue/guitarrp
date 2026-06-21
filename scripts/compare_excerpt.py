"""Compara un FRAGMENTO transcrito contra el GP oficial completo por subsecuencia.

Como el fragmento (ej. 80s del riff) no esta alineado en segundos absolutos con
el oficial (intros/repeticiones difieren), deslizamos el chroma del fragmento
sobre todo el oficial a resolucion fija de tiempo y reportamos la MEJOR
coincidencia (y donde cae). Asume que localmente fragmento y oficial van al mismo
tempo (cierto dentro de una seccion del mismo recording).

Uso:
  python scripts/compare_excerpt.py OFICIAL.gp3 EXCERPT.gp5 [--ref-tracks 0,1]
                                    [--est-tracks 0] [--res 0.5]
"""
from __future__ import annotations

import argparse
import math

import guitarpro as gp

from compare_gp import extract_notes, cosine, parse_tracks  # noqa: E402


def chroma_frames(notes, res: float, total: float | None = None):
    """Frames de 12 clases en tiempo ABSOLUTO, ponderados por duracion."""
    if not notes:
        return []
    if total is None:
        total = max(n[0] + n[1] for n in notes)
    nf = int(math.ceil(total / res)) + 1
    frames = [[0.0] * 12 for _ in range(nf)]
    for onset, dur, pitch in notes:
        f = int(onset / res)
        if 0 <= f < nf:
            frames[f][pitch % 12] += dur
    return frames


def best_subsequence(ref_frames, est_frames):
    """Desliza est sobre ref; devuelve (mejor_sim, offset_frames)."""
    n, m = len(ref_frames), len(est_frames)
    if m == 0 or n < m:
        return 0.0, 0
    # indices de frames del fragmento con contenido (ignorar silencios)
    nz = [j for j in range(m) if sum(est_frames[j]) > 0]
    if not nz:
        return 0.0, 0
    best, best_off = -1.0, 0
    for off in range(0, n - m + 1):
        sims = []
        for j in nz:
            r = ref_frames[off + j]
            if sum(r) == 0:
                sims.append(0.0)
                continue
            c = cosine(r, est_frames[j])
            sims.append(c if not math.isnan(c) else 0.0)
        avg = sum(sims) / len(sims)
        if avg > best:
            best, best_off = avg, off
    return best, best_off


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ref")
    ap.add_argument("est")
    ap.add_argument("--ref-tracks", default="")
    ap.add_argument("--est-tracks", default="")
    ap.add_argument("--res", type=float, default=0.5)
    args = ap.parse_args()

    ref_song = gp.parse(args.ref)
    est_song = gp.parse(args.est)
    ref_tracks = parse_tracks(args.ref_tracks, ref_song)
    est_tracks = parse_tracks(args.est_tracks, est_song)

    ref_notes = extract_notes(ref_song, ref_tracks)
    est_notes = extract_notes(est_song, est_tracks)

    ref_frames = chroma_frames(ref_notes, args.res)
    est_frames = chroma_frames(est_notes, args.res)

    print(f"REF: {args.ref}  pistas {ref_tracks} -> {len(ref_notes)} notas")
    print(f"EST: {args.est}  pistas {est_tracks} -> {len(est_notes)} notas, "
          f"{len(est_frames)*args.res:.0f}s")
    print()

    sim, off = best_subsequence(ref_frames, est_frames)
    t0 = off * args.res
    t1 = t0 + len(est_frames) * args.res
    # similitud global (distribucion de clases) como referencia
    def hist(notes):
        h = [0.0] * 12
        for _, dur, p in notes:
            h[p % 12] += dur
        return h
    glob = cosine(hist(ref_notes), hist(est_notes))

    print(f"Mejor coincidencia por subsecuencia: {sim*100:.1f}%")
    print(f"  (el fragmento encaja en el oficial en ~{t0:.0f}-{t1:.0f}s)")
    print(f"Similitud chroma global (distribucion): {glob*100:.1f}%")


if __name__ == "__main__":
    main()
