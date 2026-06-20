"""Etapa 4c: Detección de técnicas expresivas (Tier 1).

Analiza las notas digitadas (TabNote) y sus datos de pitch bend asociados para
marcar hammer-ons, pull-offs, slides, bends y vibrato.
"""
from __future__ import annotations

import numpy as np
from .types import TabNote


def detect_techniques(tab_notes: list[TabNote]) -> list[TabNote]:
    """Detecta y aplica técnicas de expresión sobre la lista de notas."""
    if not tab_notes:
        return []

    # 1. Ordenar notas por tiempo de inicio
    tab_notes = sorted(tab_notes, key=lambda tn: tn.start)

    # Agrupar notas por cuerda para análisis de legato/slides
    by_string: dict[int, list[TabNote]] = {i: [] for i in range(1, 7)}
    for tn in tab_notes:
        by_string[tn.string].append(tn)

    # Detectar Hammer-on / Pull-off (HOPO) y Slides
    for string, notes in by_string.items():
        for i in range(1, len(notes)):
            prev = notes[i - 1]
            curr = notes[i]

            # Si el inicio de la nota actual coincide muy cerca con el fin de la anterior
            # y el pitch es diferente (legato implícito)
            if 0.0 <= (curr.start - prev.end) <= 0.08 and curr.pitch != prev.pitch:
                fret_diff = abs(curr.fret - prev.fret)

                # Restricción física para slide: requiere que ambas notas sean pisadas (fret > 0).
                # Un salto de 2 a 6 trastes en la misma cuerda suele tocarse como slide.
                if 2 <= fret_diff <= 6 and prev.fret > 0 and curr.fret > 0:
                    curr.slide = True
                # Si es diferencia de 1 traste, o si involucra una cuerda al aire, es Hammer-on/Pull-off
                elif fret_diff == 1 or prev.fret == 0 or curr.fret == 0:
                    curr.hopo = True

    # Detectar Bends y Vibrato a partir de pitch bends
    for tn in tab_notes:
        # Fallback de vibrato por duración para notas largas
        if tn.duration >= 1.2:
            tn.vibrato = True

        if not tn.pitch_bends:
            continue

        # Extraer valores de pitch bend
        times = [t for t, v in tn.pitch_bends]
        values = [v for t, v in tn.pitch_bends]

        max_val = max(values)
        min_val = min(values)
        amplitude = max_val - min_val

        # 1. Detección de Bend
        # En MIDI estándar, rango bend = +/- 2 semitonos (8191 = +2 semitonos = 4 cuartos de tono)
        if max_val >= 1024:  # Al menos 1/4 de tono (50 cents)
            # quarters = int(round((val / 8191.0) * 4))
            quarters = int(round((max_val / 8191.0) * 4.0))
            if quarters >= 1:
                tn.bend_type = "bend"
                tn.bend_value = quarters

        # 2. Detección de Vibrato basado en oscilaciones
        # Si la amplitud de la oscilación es detectable pero no es un bend gigante (o está encima de él)
        if len(values) >= 5 and 150 <= amplitude <= 1500:
            # Contar cambios de dirección del pitch bend (picos y valles)
            diffs = np.diff(values)
            direction_changes = 0
            prev_sign = 0
            for d in diffs:
                if abs(d) > 10:  # Filtrar microruido
                    current_sign = np.sign(d)
                    if prev_sign != 0 and current_sign != prev_sign:
                        direction_changes += 1
                    prev_sign = current_sign

            # Si hay al menos 3 oscilaciones de pitch, clasificamos como vibrato
            if direction_changes >= 3:
                tn.vibrato = True

    return tab_notes
