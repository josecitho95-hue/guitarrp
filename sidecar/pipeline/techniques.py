"""Etapa 4c: Detección de técnicas expresivas (Tiers 1, 2 y 3).

Analiza las notas digitadas (TabNote) y sus datos de pitch bend asociados para
marcar hammer-ons/pull-offs, slides, bends y vibrato (Tier 1), palm mutes y armónicos
naturales (Tier 2), y sugerencias de tapping y sweep picking (Tier 3).
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

    # Agrupar notas por cuerda para análisis de legato/slides y tapping
    by_string: dict[int, list[TabNote]] = {i: [] for i in range(1, 7)}
    for tn in tab_notes:
        by_string[tn.string].append(tn)

    # --- Tier 1: Hammer-on / Pull-off (HOPO) y Slides ---
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

    # --- Tier 1: Bends y Vibrato a partir de pitch bends ---
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
        if max_val >= 1024:  # Al menos 1/4 de tono (50 cents)
            quarters = int(round((max_val / 8191.0) * 4.0))
            if quarters >= 1:
                tn.bend_type = "bend"
                tn.bend_value = quarters

        # 2. Detección de Vibrato basado en oscilaciones
        if len(values) >= 5 and 150 <= amplitude <= 1500:
            diffs = np.diff(values)
            direction_changes = 0
            prev_sign = 0
            for d in diffs:
                if abs(d) > 10:  # Filtrar microruido
                    current_sign = np.sign(d)
                    if prev_sign != 0 and current_sign != prev_sign:
                        direction_changes += 1
                    prev_sign = current_sign

            if direction_changes >= 3:
                tn.vibrato = True

    # --- Tier 2: Palm Mute ---
    for tn in tab_notes:
        # Notas muy cortas (< 150 ms) con dinámica/ataque claro (velocity >= 70)
        # y que no tengan ligadura o vibrato
        if tn.duration < 0.15 and tn.velocity >= 70 and not tn.hopo and not tn.slide and not tn.vibrato:
            tn.palm_mute = True

    # --- Tier 2: Armónicos Naturales ---
    for tn in tab_notes:
        open_pitch = tn.pitch - tn.fret
        # Armónico en traste 12 (pitch = open + 12, se escribe en traste 12)
        if tn.fret == 12:
            if tn.duration >= 0.8 and not tn.hopo and not tn.slide:
                tn.harmonic = "natural"
        # Armónico en traste 7 (pitch = open + 19, a veces transcrito/digitado como traste 19)
        elif tn.fret == 7 or (tn.pitch == open_pitch + 19 and tn.fret == 19):
            tn.fret = 7
            tn.harmonic = "natural"
        # Armónico en traste 5 (pitch = open + 24, a veces transcrito/digitado como traste 24)
        elif tn.fret == 5 or (tn.pitch == open_pitch + 24 and tn.fret == 24):
            tn.fret = 5
            tn.harmonic = "natural"

    # --- Tier 3: Tapping (Sugerencia) ---
    for string, notes in by_string.items():
        for i in range(1, len(notes)):
            prev = notes[i - 1]
            curr = notes[i]
            if curr.hopo:
                fret_diff = abs(curr.fret - prev.fret)
                # Salto muy grande en legato (>= 8 trastes) o hammer-on en traste alto (>= 12)
                # desde cuerda al aire (fret 0)
                if fret_diff >= 8 or (curr.fret >= 12 and prev.fret == 0):
                    curr.tapping = True
                    curr.hopo = False  # El tapping prevalece visualmente

    # --- Tier 3: Sweep Picking (Sugerencia) ---
    # Buscamos cadenas de notas consecutivas en cuerdas adyacentes con onsets rápidos (< 120 ms)
    sweep_chains: list[list[TabNote]] = []
    current_chain: list[TabNote] = []

    for i in range(len(tab_notes)):
        if not current_chain:
            current_chain.append(tab_notes[i])
            continue

        prev = current_chain[-1]
        curr = tab_notes[i]
        time_diff = curr.start - prev.start
        string_diff = curr.string - prev.string

        if 0.01 <= time_diff <= 0.12 and abs(string_diff) == 1:
            if len(current_chain) >= 2:
                # Comprobar si se mantiene la dirección (cuerdas incrementando o decrementando)
                expected_direction = current_chain[1].string - current_chain[0].string
                if np.sign(string_diff) == np.sign(expected_direction):
                    current_chain.append(curr)
                else:
                    if len(current_chain) >= 3:
                        sweep_chains.append(current_chain)
                    current_chain = [prev, curr]
            else:
                current_chain.append(curr)
        else:
            if len(current_chain) >= 3:
                sweep_chains.append(current_chain)
            current_chain = [curr]

    if len(current_chain) >= 3:
        sweep_chains.append(current_chain)

    for chain in sweep_chains:
        # String decreciente (6 -> 5 -> 4) -> hacia cuerdas más finas -> rasgueo hacia abajo (DOWN)
        # String creciente (3 -> 4 -> 5) -> hacia cuerdas más gruesas -> rasgueo hacia arriba (UP)
        direction = "down" if chain[1].string < chain[0].string else "up"
        for tn in chain:
            tn.sweep = direction

    return tab_notes

