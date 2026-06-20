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
        # NOTA: NO aplicamos vibrato por duración sin evidencia de pitch bend.
        # El fallback anterior (>= 1.2s) generaba demasiados falsos positivos.

        if not tn.pitch_bends:
            continue

        # Filtrar micro-ruido: solo considerar pitch bends con valor absoluto > 50
        significant_bends = [(t, v) for t, v in tn.pitch_bends if abs(v) > 50]
        if not significant_bends:
            continue

        # Extraer valores de pitch bend
        times = [t for t, v in significant_bends]
        values = [v for t, v in significant_bends]

        max_val = max(values)
        min_val = min(values)
        amplitude = max_val - min_val

        # 1. Detección de Bend — requiere umbral alto y mínimo de puntos
        # El umbral anterior (1024) era demasiado bajo y generaba 34% de falsos
        # positivos con Basic Pitch. Subimos a 2500 (~medio tono real) y
        # exigimos al menos 3 puntos significativos para confirmar que es un
        # bend intencional y no ruido espectral.
        if max_val >= 2500 and len(significant_bends) >= 3:
            quarters = int(round((max_val / 8191.0) * 4.0))
            if quarters >= 1:
                tn.bend_type = "bend"
                tn.bend_value = quarters

        # 2. Detección de Vibrato basado en oscilaciones
        # Requiere >= 6 puntos significativos y >= 4 cambios de dirección
        if len(values) >= 6 and 200 <= amplitude <= 1500:
            diffs = np.diff(values)
            direction_changes = 0
            prev_sign = 0
            for d in diffs:
                if abs(d) > 30:  # Filtrar microruido (subido de 10 a 30)
                    current_sign = np.sign(d)
                    if prev_sign != 0 and current_sign != prev_sign:
                        direction_changes += 1
                    prev_sign = current_sign

                if direction_changes >= 4:
                    tn.vibrato = True

    # --- Tier 2: Palm Mute ---
    for tn in tab_notes:
        # Notas cortas (< 120 ms) con dinámica/ataque claro (velocity >= 75)
        # en cuerdas graves (4, 5, 6) — palm mute es mucho más frecuente ahí.
        # Excluir notas con ligadura o vibrato.
        if (tn.duration < 0.12 and tn.velocity >= 75
                and tn.string >= 4
                and not tn.hopo and not tn.slide and not tn.vibrato):
            tn.palm_mute = True

    # --- Tier 2: Armónicos Naturales ---
    # Solo marcar armónicos en contextos muy específicos: nota aislada (sin
    # notas cercanas en la misma cuerda), velocidad moderada-baja, y duración
    # larga. Esto evita marcar trastes 5/7/12 en riffs rápidos como armónicos.
    for tn in tab_notes:
        # Un armónico natural suena más largo y débil que una nota pisada normal
        if tn.hopo or tn.slide or tn.vibrato or tn.bend_type:
            continue  # notas con otros efectos no son armónicos
        if tn.velocity > 80:
            continue  # armónicos naturales son generalmente suaves
        if tn.duration < 0.6:
            continue  # armónicos resuenan más largo que notas normales

        open_pitch = tn.pitch - tn.fret
        # Armónico en traste 12
        if tn.fret == 12 and tn.duration >= 0.8:
            tn.harmonic = "natural"
        # Armónico en traste 7 (pitch = open + 19)
        elif (tn.fret == 7 or (tn.pitch == open_pitch + 19 and tn.fret == 19)):
            tn.fret = 7
            tn.harmonic = "natural"
        # Armónico en traste 5 (pitch = open + 24)
        elif (tn.fret == 5 or (tn.pitch == open_pitch + 24 and tn.fret == 24)):
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

