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



_DEFAULT_GUITAR_TUNING = {1: 64, 2: 59, 3: 55, 4: 50, 5: 45, 6: 40}


def _track_layout(tab_notes: list[TabNote], grid: float):
    """Agrupa las notas de una pista por slot de onset y calcula su duración en
    slots. Devuelve (events, ev_dur, sorted_slots)."""
    events: dict[int, list[TabNote]] = {}
    for tn in tab_notes:
        slot = int(round(tn.start / grid))
        events.setdefault(slot, []).append(tn)

    sorted_slots = sorted(events)
    ev_dur: dict[int, int] = {}
    for idx, slot in enumerate(sorted_slots):
        notes = events[slot]
        longest = max((tn.end - tn.start) for tn in notes) if notes else grid
        dur = max(1, int(round(longest / grid)))
        if idx + 1 < len(sorted_slots):
            dur = min(dur, sorted_slots[idx + 1] - slot)
        ev_dur[slot] = max(1, dur)
    return events, ev_dur, sorted_slots


def _total_slots(ev_dur, sorted_slots) -> int:
    if not sorted_slots:
        return 0
    last = sorted_slots[-1]
    return last + ev_dur[last]


def _fill_track_measures(track, headers, events, ev_dur, sorted_slots, n_measures):
    """Rellena track.measures con beats/silencios cuantizados, hasta n_measures."""
    track.measures = []
    for mi in range(n_measures):
        measure = M.Measure(track, headers[mi])
        voice = measure.voices[0]
        voice.beats = []

        m_start = mi * SLOTS_PER_MEASURE
        m_end = m_start + SLOTS_PER_MEASURE
        t = m_start
        while t < m_end:
            if t in events:
                notes = events[t]
                cap = m_end - t
                s, value, dotted = _largest_fit(ev_dur[t], cap)
                voice.beats.append(_make_beat(voice, value, dotted, notes))
                t += s
            else:
                next_slots = [s for s in sorted_slots if m_start <= s < m_end and s > t]
                gap_end = min(next_slots) if next_slots else m_end
                gap = gap_end - t
                for value, dotted in _decompose(gap, m_end - t):
                    voice.beats.append(_make_beat(voice, value, dotted, []))
                t = gap_end

        if not voice.beats:   # compas vacio -> silencio de redonda
            voice.beats.append(_make_beat(voice, 1, False, []))
        track.measures.append(measure)


def build_multitrack_song(instruments: list[dict], bpm: float = 120.0,
                          title: str = "Audio2Tab") -> M.Song:
    """Construye un Song con una pista por instrumento.

    `instruments`: lista de dicts {name, tuning, tab_notes, capo?, midi_program?}.
    Todas las pistas comparten las mismas cabeceras de compas; las más cortas se
    rellenan con silencios hasta el número de compases de la más larga.
    """
    song = M.Song()
    song.title = title
    song.artist = "Audio2Tab"
    song.tempo = int(round(bpm))
    template_ts = song.measureHeaders[0].timeSignature
    grid = (60.0 / bpm) / 4.0   # segundos por semicorchea

    layouts = []
    max_total = 0
    for inst in instruments:
        ev, evd, ss = _track_layout(inst["tab_notes"], grid)
        layouts.append((ev, evd, ss))
        max_total = max(max_total, _total_slots(evd, ss))
    n_measures = max(1, math.ceil(max_total / SLOTS_PER_MEASURE)) if max_total else 1

    song.measureHeaders = []
    for mi in range(n_measures):
        header = M.MeasureHeader()
        header.number = mi + 1
        header.timeSignature = template_ts
        song.measureHeaders.append(header)

    song.tracks = []
    for idx, (inst, (ev, evd, ss)) in enumerate(zip(instruments, layouts)):
        track = M.Track(song, idx + 1)
        track.name = inst.get("name", f"Track {idx + 1}")
        track.offset = inst.get("capo", 0)
        if inst.get("percussion"):
            # Pista de batería: canal MIDI 10 (idx 9), 6 cuerdas placeholder.
            # En estas notas `value` (=fret de la TabNote) es el nº MIDI de percusión.
            track.isPercussionTrack = True
            track.channel.channel = 9
            track.channel.effectChannel = 9
            track.strings = [M.GuitarString(i + 1, 0) for i in range(6)]
        else:
            tuning = inst.get("tuning") or _DEFAULT_GUITAR_TUNING
            track.strings = [M.GuitarString(i + 1, tuning[s])
                             for i, s in enumerate(sorted(tuning))]
            if inst.get("midi_program") is not None:
                try:
                    track.channel.instrument = int(inst["midi_program"])
                except Exception:
                    pass
        _fill_track_measures(track, song.measureHeaders, ev, evd, ss, n_measures)
        song.tracks.append(track)

    return song


def build_song(tab_notes: list[TabNote], bpm: float = 120.0, title: str = "Audio2Tab",
               tuning: dict[int, int] | None = None, capo: int = 0) -> M.Song:
    """Compatibilidad single-track: delega en build_multitrack_song."""
    return build_multitrack_song(
        [{"name": "Guitar", "tuning": tuning or _DEFAULT_GUITAR_TUNING,
          "tab_notes": tab_notes, "capo": capo}],
        bpm=bpm, title=title)


def write_gp(tab_notes: list[TabNote], out_path: str, bpm: float = 120.0,
             title: str = "Audio2Tab", tuning: dict[int, int] | None = None,
             capo: int = 0) -> str:
    ext = os.path.splitext(out_path)[1].lower()
    if ext not in _EXT_TO_VERSION:
        raise ValueError(f"Formato no soportado: {ext} (usa .gp5/.gp4/.gp3)")
    song = build_song(tab_notes, bpm=bpm, title=title, tuning=tuning, capo=capo)
    gp.write(song, out_path, version=_EXT_TO_VERSION[ext])
    return out_path


def write_multitrack_gp(instruments: list[dict], out_path: str, bpm: float = 120.0,
                        title: str = "Audio2Tab") -> str:
    ext = os.path.splitext(out_path)[1].lower()
    if ext not in _EXT_TO_VERSION:
        raise ValueError(f"Formato no soportado: {ext} (usa .gp5/.gp4/.gp3)")
    song = build_multitrack_song(instruments, bpm=bpm, title=title)
    gp.write(song, out_path, version=_EXT_TO_VERSION[ext])
    return out_path
