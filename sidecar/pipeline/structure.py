"""Detección de estructura: agrupa compases en clusters de riffs repetidos.

La detección de repetición FUNCIONA de forma fiable (a diferencia de *auto-corregir*
con ella, que borra variación legítima entre repeticiones — ver
`docs/ANALISIS_CALIDAD.md` §5). Por eso se expone como **datos** para:

  1. HITL "arregla un riff una vez, propágalo a sus repeticiones" (UX-04): cuando el
     usuario corrige un compás, la UI ofrece aplicar el cambio a los demás compases
     de su cluster.
  2. Etiquetado de secciones (qué se repite = verso/coro/riff).
  3. Mostrar la estructura en el visor.

Algoritmo: cuantizar notas a una rejilla de compás (vía los beats reales), firmar cada
compás por sus eventos (slot, clase de altura), y agrupar con emparejado tolerante
(±1 slot) — el ajuste que halló 34 clusters en Master of Puppets.
"""
from __future__ import annotations

from collections import defaultdict

SUBDIV = 4              # subdivisiones por beat (semicorcheas)
BEATS_PER_BAR = 4       # 4/4
_SLOTS_PER_BAR = SUBDIV * BEATS_PER_BAR


def _soft_sim(ea, eb, slot_tol: int = 1) -> float:
    """Fracción de eventos de `ea` con match en `eb` (±slot_tol slots, misma clase)."""
    if not ea or not eb:
        return 0.0
    bset = set(eb)
    matched = 0
    for sl, pc in ea:
        if any((sl + d, pc) in bset for d in range(-slot_tol, slot_tol + 1)):
            matched += 1
    return matched / len(ea)


def detect_structure(notes, beats, sim_thresh: float = 0.6,
                     min_instances: int = 3, slot_tol: int = 1) -> dict:
    """Detecta clusters de compases (riffs) repetidos.

    `notes`: iterable de objetos con `.start` (s) y `.pitch` (MIDI) — Note o TabNote.
    `beats`: tiempos de beat (lista/np.ndarray) de `preprocess.estimate_beats`.
    Devuelve dict serializable: {bars, clusters, n_repeated_clusters}. Cada barra trae
    su `cluster` (id ≥ 0 si pertenece a un riff repetido, -1 si es única).
    """
    import numpy as np

    if beats is None or len(beats) < 2 or not notes:
        return {"bars": [], "clusters": [], "n_repeated_clusters": 0}

    beats = np.asarray(beats, dtype=float)
    bidx = np.arange(len(beats), dtype=float)

    def to_slot(t: float) -> int:
        return int(round(float(np.interp(t, beats, bidx)) * SUBDIV))

    def bar_time(b: int):
        g0 = b * _SLOTS_PER_BAR
        t0 = float(np.interp(g0 / SUBDIV, bidx, beats))
        t1 = float(np.interp((g0 + _SLOTS_PER_BAR) / SUBDIV, bidx, beats))
        return t0, t1

    # Eventos (slot dentro del compás, clase de altura) por compás.
    bars = defaultdict(list)
    for n in notes:
        gs = to_slot(n.start)
        bars[gs // _SLOTS_PER_BAR].append((gs % _SLOTS_PER_BAR, int(n.pitch) % 12))
    bar_ids = sorted(bars)

    # Clustering greedy con emparejado tolerante (simétrico).
    clusters: list[list[int]] = []
    for b in bar_ids:
        best = None
        for ci, c in enumerate(clusters):
            rep = c[0]
            s = min(_soft_sim(bars[b], bars[rep], slot_tol),
                    _soft_sim(bars[rep], bars[b], slot_tol))
            if s >= sim_thresh and (best is None or s > best[1]):
                best = (ci, s)
        if best is not None:
            clusters[best[0]].append(b)
        else:
            clusters.append([b])

    # Solo los clusters con >= min_instances cuentan como "riff repetido".
    bar_cluster: dict[int, int] = {}
    out_clusters = []
    cid = 0
    for c in clusters:
        if len(c) >= min_instances:
            for b in c:
                bar_cluster[b] = cid
            out_clusters.append({"id": cid, "bars": c, "size": len(c)})
            cid += 1
        else:
            for b in c:
                bar_cluster[b] = -1

    bars_out = []
    for b in bar_ids:
        t0, t1 = bar_time(b)
        bars_out.append({
            "bar": b, "start_s": round(t0, 3), "end_s": round(t1, 3),
            "cluster": bar_cluster.get(b, -1), "n_notes": len(bars[b]),
        })

    return {"bars": bars_out, "clusters": out_clusters,
            "n_repeated_clusters": len(out_clusters)}


def bars_in_same_cluster(structure: dict, bar: int) -> list[int]:
    """Dado un compás, devuelve los demás compases de su cluster (para HITL
    "propagar corrección"). Lista vacía si la barra es única."""
    cl = next((b["cluster"] for b in structure["bars"] if b["bar"] == bar), -1)
    if cl < 0:
        return []
    cluster = next((c for c in structure["clusters"] if c["id"] == cl), None)
    return [b for b in cluster["bars"] if b != bar] if cluster else []
