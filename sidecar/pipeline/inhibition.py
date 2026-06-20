"""Etapa 4b: Matriz de inhibición / restricción física (Fase 1).

Modela qué combinaciones y transiciones cuerda/traste son físicamente tocables y
ergonómicas. Se usa como coste de re-ranking en el DP de digitación (to_tab).

Dos fuentes posibles:
  1. Matriz aprendida de un corpus (DadaGP/GuitarSet): co-ocurrencia de pares
     (cuerda, traste). Se carga desde `models/inhibition.npz` si existe.
  2. Modelo físico-ergonómico heurístico (por defecto): no requiere datos.

La interfaz pública (`chord_feasible`, `chord_cost`, `transition_cost`) es estable
para que to_tab no dependa de la fuente.
"""
from __future__ import annotations

import os

# Restricciones físicas duras
MAX_CHORD_SPAN = 5        # trastes entre la nota más baja y más alta pisadas
MAX_FINGERS = 4           # dedos disponibles (sin contar cejilla improvisada)

# Pesos ergonómicos del coste (re-ranking, no restricción dura)
W_SPAN = 0.40             # acordes compactos preferidos
W_HEIGHT = 0.10           # preferir parte baja del mástil
W_STRING_SKIP = 0.25      # penalizar cuerdas saltadas (difícil de mutear)
W_OPEN_BONUS = 0.08       # cuerdas al aire facilitan
W_MOVE = 1.00             # movimiento de mano entre eventos

_LEARNED = None           # cache de matriz aprendida (si se carga)


def _fretted(assignment):
    return [f for _, f in assignment if f > 0]


def chord_feasible(assignment) -> bool:
    """Restricción DURA: ¿es físicamente posible este conjunto simultáneo?"""
    strings = [s for s, _ in assignment]
    if len(set(strings)) != len(strings):
        return False                      # dos notas en la misma cuerda
    fretted = _fretted(assignment)
    if fretted:
        span = max(fretted) - min(fretted)
        if span > MAX_CHORD_SPAN:
            return False                  # alcance imposible
        if len(fretted) > MAX_FINGERS:
            return False                  # más notas pisadas que dedos
    return True


# SH-02: bonificación a cuerdas al aire configurable por job.
OPEN_STRING_BONUS = {"alta": 0.30, "media": W_OPEN_BONUS, "baja": 0.0}


def chord_cost(assignment, open_bonus: float | None = None) -> float:
    """Coste ergonómico (blando) de tocar este evento.

    `open_bonus` ajusta la preferencia por cuerdas al aire (SH-02); si es None usa
    el valor por defecto del módulo.
    """
    if open_bonus is None:
        open_bonus = W_OPEN_BONUS
    fretted = _fretted(assignment)
    cost = 0.0
    if fretted:
        cost += W_SPAN * (max(fretted) - min(fretted))
        cost += W_HEIGHT * (sum(fretted) / len(fretted))
    # cuerdas saltadas: huecos entre cuerdas usadas
    strings = sorted(s for s, _ in assignment)
    if len(strings) >= 2:
        gaps = (strings[-1] - strings[0]) - (len(strings) - 1)
        cost += W_STRING_SKIP * max(0, gaps)
    cost -= open_bonus * sum(1 for _, f in assignment if f == 0)
    # ajuste por matriz aprendida, si está disponible
    learned = _load_learned()
    if learned is not None:
        cost += _learned_penalty(assignment, learned)
    return cost


def hand_position(assignment) -> float:
    fretted = _fretted(assignment)
    return sum(fretted) / len(fretted) if fretted else 0.0


def transition_cost(prev_assignment, assignment) -> float:
    """Coste de mover la mano de un evento al siguiente."""
    return W_MOVE * abs(hand_position(assignment) - hand_position(prev_assignment))


# --- Hook para matriz aprendida de corpus (opcional) ---

def _load_learned():
    global _LEARNED
    if _LEARNED is not None:
        return _LEARNED if _LEARNED is not False else None
    path = os.path.join("models", "inhibition.npz")
    if not os.path.exists(path):
        _LEARNED = False
        return None
    try:
        import numpy as np
        data = np.load(path)
        _LEARNED = {k: data[k] for k in data.files}
    except Exception:
        _LEARNED = False
        return None
    return _LEARNED


def _learned_penalty(assignment, learned) -> float:
    """Penalización por baja co-ocurrencia de pares (cuerda,traste) en el corpus.

    Espera `pair_logprob[string-1, fret]` (mayor = más común/tocable).
    """
    import numpy as np
    lp = learned.get("pair_logprob")
    if lp is None:
        return 0.0
    pen = 0.0
    for s, f in assignment:
        if 1 <= s <= lp.shape[0] and 0 <= f < lp.shape[1]:
            pen += -float(lp[s - 1, f]) * 0.05
    return pen
