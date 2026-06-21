"""Compara dos archivos Guitar Pro por CONTENIDO de notas (chroma), tolerante a
desalineacion de tempo.

Metodo:
  1. Convierte cada GP a notas (pitch MIDI, onset/offset en segundos), respetando
     mapa de tempo (cambios de tempo) y metricas de compas variables.
  2. Normaliza cada linea de tiempo a [0, 1] dividiendo por la duracion total.
  3. Construye un vector chroma de 12 clases de altura por ventana temporal,
     ponderado por duracion, y promedia la similitud coseno entre ventanas.

Tambien reporta la similitud chroma global (sin ventanas) como referencia.

Uso:
  python scripts/compare_gp.py REF.gp3 EST.gp5 [--ref-tracks 0,1] [--est-tracks 0]
                               [--windows 200]
"""
from __future__ import annotations

import argparse
import math

import guitarpro as gp

QUARTER = gp.Duration.quarterTime  # 960 ticks por negra


def measure_ticks(header) -> int:
    num = header.timeSignature.numerator
    den = header.timeSignature.denominator.value
    return int(num * (QUARTER * 4 / den))


def build_tempo_map(song) -> list[tuple[int, float]]:
    """Lista (global_tick, bpm) ordenada. Escanea la pista 0 buscando cambios."""
    tmap = [(0, float(song.tempo))]
    track = song.tracks[0]
    gtick = 0
    for m in track.measures:
        mstart = gtick
        for v in m.voices:
            btick = mstart
            for beat in v.beats:
                mt = beat.effect.mixTableChange
                if mt and mt.tempo is not None:
                    tmap.append((btick, float(mt.tempo.value)))
                btick += beat.duration.time
            break  # solo la primera voz para el mapa de tempo
        gtick += measure_ticks(m.header)
    tmap.sort()
    # deduplicar por tick conservando el ultimo
    dedup = {}
    for t, bpm in tmap:
        dedup[t] = bpm
    return sorted(dedup.items())


def tick_to_seconds(tick: int, tmap: list[tuple[int, float]]) -> float:
    secs = 0.0
    for i, (t0, bpm) in enumerate(tmap):
        t1 = tmap[i + 1][0] if i + 1 < len(tmap) else math.inf
        if tick <= t0:
            break
        seg_end = min(tick, t1)
        seg_ticks = seg_end - t0
        secs += (seg_ticks / QUARTER) * (60.0 / bpm)
        if tick <= t1:
            break
    return secs


def extract_notes(song, track_indices: list[int]) -> list[tuple[float, float, int]]:
    """Devuelve [(onset_s, dur_s, midi_pitch)] de las pistas indicadas."""
    tmap = build_tempo_map(song)
    out = []
    for ti in track_indices:
        track = song.tracks[ti]
        gtick = 0
        for m in track.measures:
            mstart = gtick
            for v in m.voices:
                btick = mstart
                for beat in v.beats:
                    if beat.notes:
                        onset = tick_to_seconds(btick, tmap)
                        end = tick_to_seconds(btick + beat.duration.time, tmap)
                        for n in beat.notes:
                            # NoteType: normal=1, tie=2, dead=3, rest? Saltar tie/dead.
                            if n.type.name not in ("normal",):
                                continue
                            out.append((onset, max(end - onset, 1e-3), n.realValue))
                    btick += beat.duration.time
            gtick += measure_ticks(m.header)
    out.sort()
    return out


def chroma_windows(notes, n_windows: int, weight_by_duration: bool):
    """Matriz n_windows x 12 de chroma normalizado por ventana, en tiempo [0,1]."""
    if not notes:
        return [[0.0] * 12 for _ in range(n_windows)]
    total = max(n[0] + n[1] for n in notes)
    mat = [[0.0] * 12 for _ in range(n_windows)]
    for onset, dur, pitch in notes:
        pos = onset / total if total > 0 else 0.0
        w = min(int(pos * n_windows), n_windows - 1)
        weight = dur if weight_by_duration else 1.0
        mat[w][pitch % 12] += weight
    return mat


def cosine(a, b) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return float("nan")
    return dot / (na * nb)


def windowed_similarity(ref_notes, est_notes, n_windows, weight_by_duration):
    rm = chroma_windows(ref_notes, n_windows, weight_by_duration)
    em = chroma_windows(est_notes, n_windows, weight_by_duration)
    sims = []
    for r, e in zip(rm, em):
        if sum(r) == 0 and sum(e) == 0:
            continue  # ambos silencio: no penaliza
        c = cosine(r, e)
        if not math.isnan(c):
            sims.append(c)
        else:
            sims.append(0.0)  # uno suena, el otro no
    return sum(sims) / len(sims) if sims else 0.0


def dtw_similarity(ref_notes, est_notes, n_windows, weight_by_duration):
    """Alinea las dos secuencias chroma con DTW y promedia la similitud coseno
    a lo largo del camino optimo. Tolerante a estiramiento/compresion temporal
    local (cambios de tempo, secciones a distinta velocidad)."""
    rm = chroma_windows(ref_notes, n_windows, weight_by_duration)
    em = chroma_windows(est_notes, n_windows, weight_by_duration)
    # quitar ventanas vacias al inicio/fin (silencio de relleno)
    def trim(mat):
        s = 0
        while s < len(mat) and sum(mat[s]) == 0:
            s += 1
        e = len(mat)
        while e > s and sum(mat[e - 1]) == 0:
            e -= 1
        return mat[s:e]
    rm, em = trim(rm), trim(em)
    if not rm or not em:
        return 0.0
    n, m = len(rm), len(em)
    # coste local = 1 - cosine (0 = identico)
    INF = float("inf")
    prev = [INF] * (m + 1)
    prev[0] = 0.0
    # acumular similitud por celda en el camino via backtrack ligero:
    # guardamos solo la matriz de coste y reconstruimos similitud promedio
    cost = [[0.0] * m for _ in range(n)]
    for i in range(n):
        for j in range(m):
            c = cosine(rm[i], em[j])
            cost[i][j] = c if not math.isnan(c) else 0.0
    # DTW sobre (1 - sim)
    D = [[INF] * (m + 1) for _ in range(n + 1)]
    D[0][0] = 0.0
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            local = 1.0 - cost[i - 1][j - 1]
            D[i][j] = local + min(D[i - 1][j], D[i][j - 1], D[i - 1][j - 1])
    # backtrack para contar pasos y similitud acumulada
    i, j = n, m
    sims = []
    while i > 0 and j > 0:
        sims.append(cost[i - 1][j - 1])
        choices = [(D[i - 1][j - 1], i - 1, j - 1),
                   (D[i - 1][j], i - 1, j),
                   (D[i][j - 1], i, j - 1)]
        _, i, j = min(choices)
    return sum(sims) / len(sims) if sims else 0.0


def global_chroma_sim(ref_notes, est_notes, weight_by_duration):
    def hist(notes):
        h = [0.0] * 12
        for onset, dur, pitch in notes:
            h[pitch % 12] += dur if weight_by_duration else 1.0
        return h
    return cosine(hist(ref_notes), hist(est_notes))


def parse_tracks(arg, song, default_guitars=True):
    if arg:
        return [int(x) for x in arg.split(",")]
    # default: todas las pistas cuyo nombre parezca guitarra
    idx = []
    for i, t in enumerate(song.tracks):
        name = (t.name or "").lower()
        if "gtr" in name or "guit" in name:
            idx.append(i)
    return idx or [0]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ref")
    ap.add_argument("est")
    ap.add_argument("--ref-tracks", default="")
    ap.add_argument("--est-tracks", default="")
    ap.add_argument("--windows", type=int, default=200)
    ap.add_argument("--count", action="store_true",
                    help="ponderar por conteo de notas en vez de duracion")
    args = ap.parse_args()

    ref_song = gp.parse(args.ref)
    est_song = gp.parse(args.est)
    ref_tracks = parse_tracks(args.ref_tracks, ref_song)
    est_tracks = parse_tracks(args.est_tracks, est_song)
    wbd = not args.count

    ref_notes = extract_notes(ref_song, ref_tracks)
    est_notes = extract_notes(est_song, est_tracks)

    ref_dur = max((n[0] + n[1] for n in ref_notes), default=0)
    est_dur = max((n[0] + n[1] for n in est_notes), default=0)

    print(f"REF: {args.ref}")
    print(f"  pistas {ref_tracks} -> {len(ref_notes)} notas, {ref_dur:.1f}s")
    print(f"EST: {args.est}")
    print(f"  pistas {est_tracks} -> {len(est_notes)} notas, {est_dur:.1f}s")
    print()

    win = windowed_similarity(ref_notes, est_notes, args.windows, wbd)
    dtw = dtw_similarity(ref_notes, est_notes, args.windows, wbd)
    glob = global_chroma_sim(ref_notes, est_notes, wbd)
    print(f"Similitud chroma DTW (tolerante a timing):           {dtw*100:.1f}%")
    print(f"Similitud chroma por ventana ({args.windows} ventanas, rigida): {win*100:.1f}%")
    print(f"Similitud chroma global (distribucion):              {glob*100:.1f}%")


if __name__ == "__main__":
    main()
