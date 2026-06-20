"""Métricas de transcripción para el benchmark de Fase 1.

Usa mir_eval para F1 a nivel de nota (onset, y onset+offset). Tolerancia de
onset estándar de 50 ms.
"""
from __future__ import annotations

import numpy as np

from sidecar.pipeline.types import Note

ONSET_TOLERANCE = 0.05      # 50 ms


def _to_arrays(notes: list[Note]):
    if not notes:
        return np.zeros((0, 2)), np.zeros((0,))
    intervals = np.array([[n.start, max(n.end, n.start + 1e-3)] for n in notes])
    pitches = np.array([440.0 * 2 ** ((n.pitch - 69) / 12.0) for n in notes])
    return intervals, pitches


def note_onset_prf(ref: list[Note], est: list[Note], offset_ratio=None) -> dict:
    """Precisión/Recall/F1 de notas.

    offset_ratio=None -> solo onset+pitch (criterio estándar de AMT de guitarra).
    offset_ratio=0.2  -> exige también acierto de duración.
    """
    import mir_eval

    ref_i, ref_p = _to_arrays(ref)
    est_i, est_p = _to_arrays(est)
    if len(ref_i) == 0 or len(est_i) == 0:
        return {"precision": 0.0, "recall": 0.0, "f1": 0.0,
                "n_ref": len(ref_i), "n_est": len(est_i)}

    p, r, f, _ = mir_eval.transcription.precision_recall_f1_overlap(
        ref_i, ref_p, est_i, est_p,
        onset_tolerance=ONSET_TOLERANCE,
        offset_ratio=offset_ratio,
        pitch_tolerance=50.0,   # cents (~medio semitono)
    )
    return {"precision": float(p), "recall": float(r), "f1": float(f),
            "n_ref": len(ref_i), "n_est": len(est_i)}
