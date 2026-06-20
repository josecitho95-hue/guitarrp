"""Etapa 5: Tablatura -> archivo Guitar Pro (.gp5/.gp4/.gp3).

Cuantiza los tiempos de las notas a una rejilla de semicorcheas (mapa
nota->compas/beat) y construye un objeto Song de PyGuitarPro. La cuantizacion
es deliberadamente sencilla para Fase 0: cada onset se ajusta a la rejilla y se
representa con una unica duracion estandar; los huecos se rellenan con silencios.
"""
from __future__ import annotations

import math
import os

import guitarpro as gp
from guitarpro import models as M

from .types import TabNote

# (slots de semicorchea, valor de duracion GP, con puntillo)
# valor GP: 1=redonda 2=blanca 4=negra 8=corchea 16=semicorchea
_DURATIONS = [
    (16, 1, False),   # redonda
    (12, 2, True),    # blanca con puntillo
    (8, 2, False),    # blanca
    (6, 4, True),     # negra con puntillo
    (4, 4, False),    # negra
    (3, 8, True),     # corchea con puntillo
    (2, 8, False),    # corchea
    (1, 16, False),   # semicorchea
]
SLOTS_PER_MEASURE = 16   # 4/4 con rejilla de semicorcheas

_EXT_TO_VERSION = {
    ".gp3": (3, 0, 0),
    ".gp4": (4, 0, 0),
    ".gp5": (5, 1, 0),
}


def _largest_fit(slots: int, cap: int) -> tuple[int, int, bool]:
    """Mayor duracion representable que cabe en min(slots, cap)."""
    limit = min(slots, cap)
    for s, value, dotted in _DURATIONS:
        if s <= limit:
            return s, value, dotted
    return 1, 16, False


def _decompose(slots: int, cap: int) -> list[tuple[int, bool]]:
    """Descompone una duracion (en slots) en una lista de (valor, puntillo)."""
    out = []
    remaining = slots
    while remaining > 0:
        s, value, dotted = _largest_fit(remaining, cap)
        out.append((value, dotted))
        remaining -= s
    return out


def _make_beat(voice, value: int, dotted: bool, tab_notes: list[TabNote]):
    """Crea un Beat con notas y sus respectivos efectos (Tiers 1, 2 y 3)."""
    beat = M.Beat(voice)
    beat.duration = M.Duration(value=value, isDotted=dotted)
    if tab_notes:
        beat.status = M.BeatStatus.normal
        # RNF-01 / Robustez: si hay varias notas en la misma cuerda en este beat cuantizado,
        # conservar únicamente la de mayor velocidad y menor tiempo de inicio para no corromper el archivo GP5.
        seen_strings = set()
        unique_notes = []
        for tn in sorted(tab_notes, key=lambda x: (-x.velocity, x.start)):
            if tn.string not in seen_strings:
                seen_strings.add(tn.string)
                unique_notes.append(tn)

        # Ordenar por cuerda para consistencia
        unique_notes.sort(key=lambda x: x.string)

        for tn in unique_notes:
            note = M.Note(beat)
            note.value = tn.fret
            note.string = tn.string
            note.velocity = tn.velocity
            note.type = M.NoteType.normal

            # Aplicar efectos (Tier 1)
            if tn.hopo:
                note.effect.hammer = True
            if tn.slide:
                note.effect.slides = [M.SlideType.legatoSlideTo]
            if tn.vibrato:
                note.effect.vibrato = True
            if tn.bend_type and tn.bend_value > 0:
                note.effect.bend = M.BendEffect(
                    type=M.BendType.bend,
                    value=int(round(tn.bend_value)),
                    points=[
                        M.BendPoint(position=0, value=0),
                        M.BendPoint(position=6, value=int(round(tn.bend_value))),
                        M.BendPoint(position=12, value=int(round(tn.bend_value))),
                    ]
                )

            # Aplicar efectos (Tier 2)
            if getattr(tn, "palm_mute", False):
                note.effect.palmMute = True
            if getattr(tn, "harmonic", None) == "natural":
                note.effect.harmonic = M.NaturalHarmonic()

            beat.notes.append(note)

        # Aplicar efectos de beat (Tier 3)
        if any(getattr(tn, "tapping", False) for tn in unique_notes):
            beat.effect.slapEffect = M.SlapEffect.tapping

        # Sweep stroke (barrido de púa)
        sweep_dir = next((getattr(tn, "sweep", None) for tn in unique_notes if getattr(tn, "sweep", None)), None)
        if sweep_dir == "down":
            beat.effect.stroke = M.BeatStroke(direction=M.BeatStrokeDirection.down, value=4)
        elif sweep_dir == "up":
            beat.effect.stroke = M.BeatStroke(direction=M.BeatStrokeDirection.up, value=4)
    else:
        beat.status = M.BeatStatus.rest
    return beat



def build_song(tab_notes: list[TabNote], bpm: float = 120.0, title: str = "Audio2Tab",
               tuning: dict[int, int] | None = None, capo: int = 0) -> M.Song:
    song = M.Song()
    song.title = title
    song.artist = "Audio2Tab"
    song.tempo = int(round(bpm))
    track = song.tracks[0]
    track.name = "Guitar"
    track.offset = capo
    if tuning:
        for string_idx, midi in tuning.items():
            if 0 <= string_idx - 1 < len(track.strings):
                track.strings[string_idx - 1].value = midi

    grid = (60.0 / bpm) / 4.0   # segundos por semicorchea

    # Agrupar notas por slot de onset (acordes comparten slot).
    events: dict[int, list[TabNote]] = {}
    for tn in tab_notes:
        slot = int(round(tn.start / grid))
        events.setdefault(slot, []).append(tn)

    sorted_slots = sorted(events)
    if not sorted_slots:
        sorted_slots = [0]
        events[0] = []

    # Duracion (en slots) de cada evento, sin solaparse con el siguiente.
    ev_dur: dict[int, int] = {}
    for idx, slot in enumerate(sorted_slots):
        notes = events[slot]
        if notes:
            longest = max((tn.end - tn.start) for tn in notes)
            dur = max(1, int(round(longest / grid)))
        else:
            dur = 1
        if idx + 1 < len(sorted_slots):
            dur = min(dur, sorted_slots[idx + 1] - slot)
        ev_dur[slot] = max(1, dur)

    last_slot = sorted_slots[-1]
    total_slots = last_slot + ev_dur[last_slot]
    n_measures = max(1, math.ceil(total_slots / SLOTS_PER_MEASURE))

    # Plantilla de cabecera de compas (copia de la que trae Song por defecto).
    template_ts = song.measureHeaders[0].timeSignature

    song.measureHeaders = []
    track.measures = []

    slot_to_event = {s: events[s] for s in sorted_slots}

    for mi in range(n_measures):
        header = M.MeasureHeader()
        header.number = mi + 1
        header.timeSignature = template_ts
        song.measureHeaders.append(header)

        measure = M.Measure(track, header)
        voice = measure.voices[0]
        voice.beats = []

        m_start = mi * SLOTS_PER_MEASURE
        m_end = m_start + SLOTS_PER_MEASURE
        t = m_start

        while t < m_end:
            if t in slot_to_event:
                notes = slot_to_event[t]
                cap = m_end - t
                s, value, dotted = _largest_fit(ev_dur[t], cap)
                voice.beats.append(_make_beat(voice, value, dotted, notes))
                t += s
            else:
                # silencio hasta el proximo evento o fin de compas
                next_slots = [s for s in sorted_slots if m_start <= s < m_end and s > t]
                gap_end = min(next_slots) if next_slots else m_end
                gap = gap_end - t
                for value, dotted in _decompose(gap, m_end - t):
                    voice.beats.append(_make_beat(voice, value, dotted, []))
                t = gap_end

        if not voice.beats:   # compas vacio -> silencio de redonda
            voice.beats.append(_make_beat(voice, 1, False, []))

        track.measures.append(measure)

    return song


def write_gp(tab_notes: list[TabNote], out_path: str, bpm: float = 120.0,
             title: str = "Audio2Tab", tuning: dict[int, int] | None = None,
             capo: int = 0) -> str:
    ext = os.path.splitext(out_path)[1].lower()
    if ext not in _EXT_TO_VERSION:
        raise ValueError(f"Formato no soportado: {ext} (usa .gp5/.gp4/.gp3)")
    song = build_song(tab_notes, bpm=bpm, title=title, tuning=tuning, capo=capo)
    gp.write(song, out_path, version=_EXT_TO_VERSION[ext])
    return out_path
