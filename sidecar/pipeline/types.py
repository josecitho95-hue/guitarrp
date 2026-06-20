"""Tipos de datos compartidos del pipeline Audio2Tab (Fase 0)."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Note:
    """Nota transcrita (salida de la etapa audio->MIDI)."""

    pitch: int          # número de nota MIDI (60 = C4)
    start: float        # segundos
    end: float          # segundos
    velocity: int = 96

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)


@dataclass
class TabNote(Note):
    """Nota con digitación asignada (salida de la etapa MIDI->Tab)."""

    string: int = 1     # 1..6  (1 = Mi agudo, 6 = Mi grave, como en Guitar Pro)
    fret: int = 0
