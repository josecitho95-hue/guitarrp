"""Genera la matriz de inhibición data-driven `models/inhibition.npz` a partir de
GuitarSet (anotación hexafónica: cada nota trae su cuerda real).

NO es entrenamiento: son estadísticas de uso de pares (cuerda, traste) sobre un
corpus de tablatura. `inhibition.py` las carga vía `_load_learned()` y penaliza
posiciones poco frecuentes/no idiomáticas en el DP de digitación.

Uso:
    python scripts/build_inhibition.py [--n N] [--out models/inhibition.npz]
"""
from __future__ import annotations

import argparse
import math
import os

import numpy as np

# Afinación estándar -> MIDI al aire por cuerda. Convención del proyecto:
# cuerda 1 = mi agudo (e), ... cuerda 6 = Mi grave (E). GuitarSet usa nombres.
STRING_TO_IDX = {"e": 1, "B": 2, "G": 3, "D": 4, "A": 5, "E": 6}
OPEN_MIDI = {1: 64, 2: 59, 3: 55, 4: 50, 5: 45, 6: 40}
N_STRINGS = 6
N_FRETS = 24          # 0..23
SMOOTHING = 1.0       # Laplace (evita log(0) en pares no vistos)


def build(n: int) -> np.ndarray:
    import mirdata
    gs = mirdata.initialize("guitarset")
    counts = np.zeros((N_STRINGS, N_FRETS), dtype=np.float64)

    ids = list(gs.track_ids)
    if n > 0:
        ids = ids[:n]
    used = 0
    for tid in ids:
        try:
            nd = gs.track(tid).notes   # dict {nombre_cuerda: NoteData}
        except Exception:
            continue
        if not isinstance(nd, dict):
            continue
        used += 1
        for sname, data in nd.items():
            s = STRING_TO_IDX.get(sname)
            if s is None or not hasattr(data, "pitches"):
                continue
            for pitch in data.pitches:
                fret = int(round(float(pitch))) - OPEN_MIDI[s]
                if 0 <= fret < N_FRETS:
                    counts[s - 1, fret] += 1.0

    counts += SMOOTHING
    pair_logprob = np.log(counts / counts.sum())
    print(f"GuitarSet: {used} pistas | notas contadas: {int(counts.sum() - SMOOTHING * counts.size)}")
    # diagnóstico: pares más y menos comunes
    flat = [(pair_logprob[s, f], s + 1, f) for s in range(N_STRINGS) for f in range(N_FRETS)]
    flat.sort(reverse=True)
    print("Más comunes (cuerda, traste):",
          [(s, f) for _, s, f in flat[:6]])
    return pair_logprob.astype(np.float32)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=0, help="Nº de pistas (0 = todas)")
    ap.add_argument("--out", default="models/inhibition.npz")
    args = ap.parse_args()

    pair_logprob = build(args.n)
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    np.savez(args.out, pair_logprob=pair_logprob)
    print(f"Matriz guardada -> {args.out}  shape={pair_logprob.shape}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
