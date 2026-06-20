"""Etapa 4: MIDI -> Tablatura (asignacion de cuerda/traste).

Algoritmo de programacion dinamica (Viterbi) que asigna a cada nota una posicion
(cuerda, traste) minimizando el coste total. El coste y las restricciones fisicas
los provee `inhibition` (etapa 4b), que actua como matriz de inhibicion: descarta
posiciones imposibles y penaliza las poco ergonomicas.

En Fase 0/1 sustituye a open-fret/Fretting-Transformer (sin pesos publicos).
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass

from . import inhibition
from .types import Note, TabNote

# Afinacion estandar: numero de cuerda -> nota MIDI al aire (1 = Mi agudo).
STANDARD_TUNING = {1: 64, 2: 59, 3: 55, 4: 50, 5: 45, 6: 40}

MAX_FRET = 22
ONSET_EPS = 0.035       # notas que empiezan dentro de esta ventana = acorde (s)
MAX_EVENT_OPTIONS = 24  # poda de asignaciones por evento


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


def _event_assignments(event: _Event, tuning: dict[int, int],
                       open_bonus: float | None = None) -> list[list[tuple[int, int]]]:
    """Asignaciones (cuerda, traste) factibles para las notas del evento.

    Filtra por la restriccion dura de `inhibition.chord_feasible` y ordena por
    coste ergonomico para podar las mejores opciones.
    """
    per_note = [_candidates(n.pitch, tuning) for n in event.notes]
    per_note = [c for c in per_note if c]      # descartar notas fuera de rango
    if not per_note:
        return []

    feasible: list[list[tuple[int, int]]] = []
    for combo in itertools.product(*per_note):
        asg = list(combo)
        if inhibition.chord_feasible(asg):
            feasible.append(asg)

    feasible.sort(key=lambda a: inhibition.chord_cost(a, open_bonus))
    return feasible[:MAX_EVENT_OPTIONS]


def _group_events(notes: list[Note]) -> list[_Event]:
    events: list[_Event] = []
    for note in sorted(notes, key=lambda n: n.start):
        if events and abs(note.start - events[-1].time) <= ONSET_EPS:
            events[-1].notes.append(note)
        else:
            events.append(_Event(time=note.start, notes=[note]))
    return events


def assign_tab(notes: list[Note], tuning: dict[int, int] | None = None,
               open_string_pref: str = "media") -> list[TabNote]:
    """Asigna (cuerda, traste) a cada nota via DP minimizando el coste total.

    `open_string_pref` (SH-02): "alta" | "media" | "baja" — preferencia por
    cuerdas al aire.
    """
    tuning = tuning or STANDARD_TUNING
    if not notes:
        return []

    open_bonus = inhibition.OPEN_STRING_BONUS.get(open_string_pref, inhibition.W_OPEN_BONUS)
    events = _group_events(notes)
    options = [_event_assignments(ev, tuning, open_bonus) for ev in events]

    n = len(events)
    best_cost = [dict() for _ in range(n)]   # idx_asignacion -> coste minimo
    back = [dict() for _ in range(n)]        # idx_asignacion -> idx previo

    for j, asg in enumerate(options[0]):
        best_cost[0][j] = inhibition.chord_cost(asg, open_bonus)
        back[0][j] = -1

    for i in range(1, n):
        if not options[i]:
            options[i] = options[i - 1][:1] if options[i - 1] else []
        for j, asg in enumerate(options[i]):
            base = inhibition.chord_cost(asg, open_bonus)
            best = None
            for pj, pcost in best_cost[i - 1].items():
                c = pcost + base + inhibition.transition_cost(options[i - 1][pj], asg)
                if best is None or c < best[0]:
                    best = (c, pj)
            if best is None:
                best = (base, -1)
            best_cost[i][j] = best[0]
            back[i][j] = best[1]

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
