"""Etapa 4 + 4b: MIDI -> Tablatura (asignacion de cuerda/traste).

Implementa un algoritmo de programacion dinamica (Viterbi) que asigna a cada
nota una posicion (cuerda, traste) minimizando el movimiento de la mano, con
restricciones fisicas que hacen las veces de "matriz de inhibicion" ligera:
  - una cuerda no puede tocar dos notas simultaneas,
  - el alcance (span) de trastes dentro de un acorde es limitado,
  - solo posiciones validas en el diapason.

En Fase 0 sustituye a open-fret/Fretting-Transformer (que no tiene pesos
publicos). Es el "fallback DP" descrito en el plan, elevado a opcion por defecto.
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass

from .types import Note, TabNote

# Afinacion estandar: numero de cuerda -> nota MIDI al aire (1 = Mi agudo).
STANDARD_TUNING = {1: 64, 2: 59, 3: 55, 4: 50, 5: 45, 6: 40}

MAX_FRET = 22
CHORD_SPAN = 5          # alcance maximo de trastes dentro de un acorde
ONSET_EPS = 0.035       # notas que empiezan dentro de esta ventana = acorde (s)

# Pesos del coste DP
W_MOVE = 1.0            # movimiento de mano entre eventos (en trastes)
W_HEIGHT = 0.10        # preferir posiciones bajas en el mastil
W_OPEN_BONUS = 0.05    # leve bonificacion a cuerdas al aire


@dataclass
class _Event:
    time: float
    notes: list[Note]                 # notas simultaneas (1 = monofonico)


def _candidates(pitch: int, tuning: dict[int, int]) -> list[tuple[int, int]]:
    """Posiciones (cuerda, traste) validas para una altura MIDI."""
    out = []
    for string, open_midi in tuning.items():
        fret = pitch - open_midi
        if 0 <= fret <= MAX_FRET:
            out.append((string, fret))
    return out


def _hand_pos(assignment: list[tuple[int, int]]) -> float:
    """Posicion de la mano = traste medio de los trastes pisados (>0)."""
    fretted = [f for _, f in assignment if f > 0]
    return sum(fretted) / len(fretted) if fretted else 0.0


def _event_assignments(event: _Event, tuning: dict[int, int]) -> list[list[tuple[int, int]]]:
    """Asignaciones factibles (cuerda, traste) para todas las notas del evento.

    Cada nota va a una cuerda distinta; respeta el span de acorde.
    Devuelve lista de asignaciones (una por nota, en el mismo orden que event.notes).
    """
    per_note = [_candidates(n.pitch, tuning) for n in event.notes]
    if any(len(c) == 0 for c in per_note):
        # alguna nota cae fuera del rango de la guitarra -> se omite del acorde
        per_note = [c for c in per_note if c]
        if not per_note:
            return []

    feasible: list[list[tuple[int, int]]] = []
    for combo in itertools.product(*per_note):
        strings = [s for s, _ in combo]
        if len(set(strings)) != len(strings):
            continue  # dos notas en la misma cuerda: imposible
        fretted = [f for _, f in combo if f > 0]
        if fretted and (max(fretted) - min(fretted)) > CHORD_SPAN:
            continue  # acorde inalcanzable
        feasible.append(list(combo))

    # Limitar explosion combinatoria en acordes densos: las mejores por compacidad.
    feasible.sort(key=lambda a: (_span(a), _hand_pos(a)))
    return feasible[:24]


def _span(assignment: list[tuple[int, int]]) -> int:
    fretted = [f for _, f in assignment if f > 0]
    return (max(fretted) - min(fretted)) if fretted else 0


def _intra_cost(assignment: list[tuple[int, int]]) -> float:
    cost = 0.0
    for _, fret in assignment:
        cost += W_HEIGHT * fret
        if fret == 0:
            cost -= W_OPEN_BONUS
    return cost


def _group_events(notes: list[Note]) -> list[_Event]:
    events: list[_Event] = []
    for note in sorted(notes, key=lambda n: n.start):
        if events and abs(note.start - events[-1].time) <= ONSET_EPS:
            events[-1].notes.append(note)
        else:
            events.append(_Event(time=note.start, notes=[note]))
    return events


def assign_tab(notes: list[Note], tuning: dict[int, int] | None = None) -> list[TabNote]:
    """Asigna (cuerda, traste) a cada nota via DP minimizando movimiento de mano."""
    tuning = tuning or STANDARD_TUNING
    if not notes:
        return []

    events = _group_events(notes)
    options = [_event_assignments(ev, tuning) for ev in events]

    # DP / Viterbi sobre las asignaciones de cada evento.
    n = len(events)
    best_cost = [dict() for _ in range(n)]   # idx_asignacion -> coste minimo
    back = [dict() for _ in range(n)]        # idx_asignacion -> idx previo

    for j, asg in enumerate(options[0]):
        best_cost[0][j] = _intra_cost(asg)
        back[0][j] = -1

    for i in range(1, n):
        if not options[i]:
            options[i] = options[i - 1][:1] if options[i - 1] else []
        for j, asg in enumerate(options[i]):
            hp = _hand_pos(asg)
            base = _intra_cost(asg)
            best = None
            for pj, pcost in best_cost[i - 1].items():
                move = abs(hp - _hand_pos(options[i - 1][pj]))
                c = pcost + base + W_MOVE * move
                if best is None or c < best[0]:
                    best = (c, pj)
            if best is None:
                best = (base, -1)
            best_cost[i][j] = best[0]
            back[i][j] = best[1]

    # Reconstruccion del camino optimo.
    if not best_cost[n - 1]:
        return []
    last = min(best_cost[n - 1], key=best_cost[n - 1].get)
    path = [0] * n
    path[n - 1] = last
    for i in range(n - 1, 0, -1):
        path[i - 1] = back[i][path[i]]
        if path[i - 1] < 0:
            path[i - 1] = 0

    tab_notes: list[TabNote] = []
    for i, ev in enumerate(events):
        asg = options[i][path[i]] if options[i] else []
        for note, (string, fret) in zip(ev.notes, asg):
            tab_notes.append(TabNote(
                pitch=note.pitch, start=note.start, end=note.end,
                velocity=note.velocity, string=string, fret=fret,
            ))
    tab_notes.sort(key=lambda t: (t.start, -t.string))
    return tab_notes
