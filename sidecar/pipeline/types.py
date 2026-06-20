"""Tipos de datos compartidos del pipeline Audio2Tab (Fase 0)."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Note:
    """Nota transcrita (salida de la etapa audio->MIDI)."""

    pitch: int          # número de nota MIDI (60 = C4)
    start: float        # segundos
    end: float          # segundos
    velocity: int = 96
    pitch_bends: list[tuple[float, int]] = field(default_factory=list)

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)


@dataclass
class TabNote(Note):
    """Nota con digitación asignada (salida de la etapa MIDI->Tab)."""

    string: int = 1     # 1..6  (1 = Mi agudo, 6 = Mi grave, como en Guitar Pro)
    fret: int = 0
    hopo: bool = False
    slide: bool = False
    vibrato: bool = False
    bend_type: str | None = None
    bend_value: int = 0

