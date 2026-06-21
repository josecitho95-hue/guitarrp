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

# Tabla de duraciones: (slots, valor_GP, puntillo, tuplet) — tuplet=None o (enters,times).
# valor GP: 1=redonda 2=blanca 4=negra 8=corchea 16=semicorchea 32=fusa.

# Rejilla RECTA (por defecto): semicorcheas, 16 slots/compás (4/4).
_DURATIONS_STRAIGHT = [
    (16, 1, False, None),   # redonda
    (12, 2, True, None),    # blanca con puntillo
    (8, 2, False, None),    # blanca
    (6, 4, True, None),     # negra con puntillo
    (4, 4, False, None),    # negra
    (3, 8, True, None),     # corchea con puntillo
    (2, 8, False, None),    # corchea
    (1, 16, False, None),   # semicorchea
]

# Rejilla con TRESILLOS (opt-in): 48 slots/compás (12/beat) -> soporta rectas Y tresillos.
# El galope del metal (The Trooper) son tresillos de corchea (4 slots).
_DURATIONS_TRIPLET = [
    (48, 1, False, None),       # redonda
    (36, 2, True, None),        # blanca con puntillo
    (24, 2, False, None),       # blanca
    (18, 4, True, None),        # negra con puntillo
    (16, 2, False, (3, 2)),     # tresillo de blanca
    (12, 4, False, None),       # negra
    (9, 8, True, None),         # corchea con puntillo
    (8, 4, False, (3, 2)),      # tresillo de negra
    (6, 8, False, None),        # corchea
    (4, 8, False, (3, 2)),      # tresillo de corchea (GALOPE)
    (3, 16, False, None),       # semicorchea
    (2, 16, False, (3, 2)),     # tresillo de semicorchea
    (1, 32, False, None),       # fusa (resto)
]

_GRID_STRAIGHT = {"slots_per_measure": 16, "subdiv": 4, "durations": _DURATIONS_STRAIGHT,
                  "avoid_one": False}
_GRID_TRIPLET = {"slots_per_measure": 48, "subdiv": 12, "durations": _DURATIONS_TRIPLET,
                 "avoid_one": True}

_EXT_TO_VERSION = {
    ".gp3": (3, 0, 0),
    ".gp4": (4, 0, 0),
    ".gp5": (5, 1, 0),
}


def _largest_fit(slots: int, cap: int, durations=_DURATIONS_STRAIGHT, avoid_one=False):
    """Mayor duracion que cabe en min(slots, cap). -> (slots,value,dotted,tuplet).
    Con `avoid_one` (rejilla de tresillos, 48/compás) evita dejar 1 slot suelto: en
    esa rejilla 1 slot no tiene figura limpia (el 32avo son 1.5 slots) y desbordaría
    el compás; se elige una figura menor para que el resto sea representable."""
    limit = min(slots, cap)
    for s, value, dotted, tup in durations:
        if s <= limit and not (avoid_one and (slots - s) == 1):
            return s, value, dotted, tup
    for s, value, dotted, tup in durations:        # fallback sin la restricción
        if s <= limit:
            return s, value, dotted, tup
    return 1, durations[-1][1], False, None


def _decompose(slots: int, cap: int, durations=_DURATIONS_STRAIGHT, avoid_one=False):
    """Descompone una duracion (en slots) en lista de (valor, puntillo, tuplet)."""
    out = []
    remaining = slots
    while remaining > 0:
        s, value, dotted, tup = _largest_fit(remaining, cap, durations, avoid_one)
        out.append((value, dotted, tup))
        remaining -= s
    return out


def _make_beat(voice, value: int, dotted: bool, tab_notes: list[TabNote], tuplet=None):
    """Crea un Beat con notas y sus respectivos efectos (Tiers 1, 2 y 3)."""
    beat = M.Beat(voice)
    beat.duration = M.Duration(value=value, isDotted=dotted)
    if tuplet:
        beat.duration.tuplet = M.Tuplet(enters=tuplet[0], times=tuplet[1])
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


def _make_beat_pos(beats, bpm: float):
    """Devuelve f(onset_segundos) -> posición en beats (float). Con `beats` (tiempos
    reales del audio) sigue el pulso real; sin ellos, grid fijo a `bpm`."""
    if beats is not None and len(beats) >= 2:
        import numpy as np
        idx = np.arange(len(beats), dtype=float)
        beats = np.asarray(beats, dtype=float)
        return lambda t: float(np.interp(t, beats, idx))
    sec_per_beat = 60.0 / bpm
    return lambda t: t / sec_per_beat


def _make_to_slot(beats, bpm: float, subdiv: int = 4):
    """onset_segundos -> slot (rejilla recta de `subdiv` por beat). Cuantiza relativo
    a los beats reales si se dan (corrige fase), si no usa grid fijo a `bpm`."""
    bp = _make_beat_pos(beats, bpm)
    return lambda t: int(round(bp(t) * subdiv))


# Posiciones (fracción del beat) de cada subdivisión.
_STRAIGHT_FRACS = (0.0, 0.25, 0.5, 0.75)     # semicorcheas
_TRIPLET_FRACS = (0.0, 1.0 / 3, 2.0 / 3)     # tresillos de corchea


def _make_to_slot_triplet(beats, bpm: float, all_onsets, straight_bias: float = 1.1):
    """onset -> slot en rejilla de 48/compás (12/beat), decidiendo la subdivisión
    POR BEAT: cada beat es recto (semicorcheas) O tresillo, nunca mezclado (así un
    beat nunca produce huecos imposibles que desbordan el compás). Un beat es
    tresillo solo si sus onsets encajan claramente mejor en la rejilla de tresillo.
    """
    from collections import defaultdict
    bp = _make_beat_pos(beats, bpm)

    by_beat = defaultdict(list)
    for t in all_onsets:
        p = bp(t)
        by_beat[int(p)].append(p - int(p))

    def mean_err(fracs, grid):
        return sum(min(abs(f - g) for g in grid) for f in fracs) / len(fracs)

    is_trip: dict[int, bool] = {}
    for beat, fracs in by_beat.items():
        if len(fracs) < 2:
            is_trip[beat] = False                 # 1 onset no determina tresillo
            continue
        es = mean_err(fracs, _STRAIGHT_FRACS)
        et = mean_err(fracs, _TRIPLET_FRACS)
        is_trip[beat] = et * straight_bias < es   # tresillo solo si claramente mejor

    def to_slot(t: float) -> int:
        p = bp(t)
        beat = int(p)
        frac = p - beat
        if is_trip.get(beat):
            return beat * 12 + int(round(frac * 3)) * 4   # {0,4,8,12}
        return beat * 12 + int(round(frac * 4)) * 3       # {0,3,6,9,12}

    return to_slot


def _track_layout(tab_notes: list[TabNote], to_slot, to_slot_end=None, prefer_gap=False):
    """Agrupa las notas de una pista por slot de onset y calcula su duración en
    slots. `to_slot` (sesgado) ubica el onset; `to_slot_end` (sin sesgo) cuantiza el
    fin. `prefer_gap=True` (modo tresillos): la duración = brecha entre onsets
    (inter-onset), que sigue la rejilla fiable de onsets y evita falsos tresillos por
    notas staccato; las notas se sostienen hasta el siguiente onset."""
    to_slot_end = to_slot_end or to_slot
    events: dict[int, list[TabNote]] = {}
    for tn in tab_notes:
        slot = to_slot(tn.start)
        events.setdefault(slot, []).append(tn)

    sorted_slots = sorted(events)
    ev_dur: dict[int, int] = {}
    for idx, slot in enumerate(sorted_slots):
        notes = events[slot]
        has_next = idx + 1 < len(sorted_slots)
        gap = sorted_slots[idx + 1] - slot if has_next else None
        end_slot = max((to_slot_end(tn.end) for tn in notes), default=slot + 1) if notes else slot + 1
        end_dur = max(1, end_slot - slot)
        if prefer_gap and has_next:
            dur = gap
        elif has_next:
            dur = min(end_dur, gap)
        else:
            dur = end_dur
        ev_dur[slot] = max(1, dur)
    return events, ev_dur, sorted_slots


def _total_slots(ev_dur, sorted_slots) -> int:
    if not sorted_slots:
        return 0
    last = sorted_slots[-1]
    return last + ev_dur[last]


def _fill_track_measures(track, headers, events, ev_dur, sorted_slots, n_measures,
                         grid=_GRID_STRAIGHT):
    """Rellena track.measures con beats/silencios cuantizados, hasta n_measures."""
    spm = grid["slots_per_measure"]
    durs = grid["durations"]
    a1 = grid.get("avoid_one", False)
    track.measures = []
    for mi in range(n_measures):
        measure = M.Measure(track, headers[mi])
        voice = measure.voices[0]
        voice.beats = []

        m_start = mi * spm
        m_end = m_start + spm
        t = m_start
        while t < m_end:
            if t in events:
                notes = events[t]
                cap = m_end - t
                s, value, dotted, tup = _largest_fit(ev_dur[t], cap, durs, a1)
                voice.beats.append(_make_beat(voice, value, dotted, notes, tup))
                t += s
            else:
                next_slots = [s for s in sorted_slots if m_start <= s < m_end and s > t]
                gap_end = min(next_slots) if next_slots else m_end
                gap = gap_end - t
                for value, dotted, tup in _decompose(gap, m_end - t, durs, a1):
                    voice.beats.append(_make_beat(voice, value, dotted, [], tup))
                t = gap_end

        if not voice.beats:   # compas vacio -> silencio de redonda
            voice.beats.append(_make_beat(voice, 1, False, []))
        track.measures.append(measure)


def _write_tempo_map(song: M.Song, beats, base_bpm: float) -> None:
    """Escribe cambios de tempo por compás según el espaciado real de los beats,
    para que la reconstrucción a segundos siga el pulso del audio (incluye
    secciones más lentas/rápidas). Solo escribe cuando el tempo cambia >4%."""
    if beats is None or len(beats) < 2 or not song.tracks:
        return
    import numpy as np
    beats = np.asarray(beats, dtype=float)
    bpm = 60.0 / float(np.median(np.diff(beats)))
    song.tempo = int(round(max(30, min(300, bpm))))

    track = song.tracks[0]
    prev = song.tempo
    for mi, measure in enumerate(track.measures):
        b0, b1 = mi * 4, mi * 4 + 4
        if b1 >= len(beats):
            break
        seg = beats[b0:b1 + 1]
        if len(seg) < 2:
            continue
        local = 60.0 / float(np.median(np.diff(seg)))
        local = max(30, min(300, local))
        if abs(local - prev) / prev > 0.04:
            beats_in_m = measure.voices[0].beats if measure.voices else []
            if beats_in_m:
                mtc = M.MixTableChange()
                item = M.MixTableItem()
                item.value = int(round(local))
                item.allTracks = True
                mtc.tempo = item
                beats_in_m[0].effect.mixTableChange = mtc
            prev = local


def build_multitrack_song(instruments: list[dict], bpm: float = 120.0,
                          title: str = "Audio2Tab", beats=None,
                          triplets: bool = False) -> M.Song:
    """Construye un Song con una pista por instrumento.

    `instruments`: lista de dicts {name, tuning, tab_notes, capo?, midi_program?}.
    Todas las pistas comparten las mismas cabeceras de compas; las más cortas se
    rellenan con silencios hasta el número de compases de la más larga.
    `beats`: tiempos de beat reales del audio (opcional) para cuantización
    relativa a beats + mapa de tempo dinámico.
    `triplets`: si True usa rejilla de 48 slots/compás con soporte de tresillos
    (galope del metal); si False, rejilla recta de semicorcheas (por defecto).
    """
    grid = _GRID_TRIPLET if triplets else _GRID_STRAIGHT
    spm = grid["slots_per_measure"]
    song = M.Song()
    song.title = title
    song.artist = "Audio2Tab"
    song.tempo = int(round(bpm))
    template_ts = song.measureHeaders[0].timeSignature
    if triplets:
        # Decisión de subdivisión POR BEAT usando los onsets de todas las pistas
        # (así todas comparten la misma rejilla por beat y nada desborda).
        all_onsets = [tn.start for inst in instruments for tn in inst["tab_notes"]]
        to_slot = _make_to_slot_triplet(beats, bpm, all_onsets)
        to_slot_end = to_slot
    else:
        to_slot = _make_to_slot(beats, bpm, grid["subdiv"])
        to_slot_end = to_slot

    layouts = []
    max_total = 0
    for inst in instruments:
        ev, evd, ss = _track_layout(inst["tab_notes"], to_slot, to_slot_end,
                                    prefer_gap=triplets)
        layouts.append((ev, evd, ss))
        max_total = max(max_total, _total_slots(evd, ss))
    n_measures = max(1, math.ceil(max_total / spm)) if max_total else 1

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
        _fill_track_measures(track, song.measureHeaders, ev, evd, ss, n_measures, grid)
        song.tracks.append(track)

    _write_tempo_map(song, beats, bpm)
    return song


def build_song(tab_notes: list[TabNote], bpm: float = 120.0, title: str = "Audio2Tab",
               tuning: dict[int, int] | None = None, capo: int = 0,
               triplets: bool = False) -> M.Song:
    """Compatibilidad single-track: delega en build_multitrack_song."""
    return build_multitrack_song(
        [{"name": "Guitar", "tuning": tuning or _DEFAULT_GUITAR_TUNING,
          "tab_notes": tab_notes, "capo": capo}],
        bpm=bpm, title=title, triplets=triplets)


def write_gp(tab_notes: list[TabNote], out_path: str, bpm: float = 120.0,
             title: str = "Audio2Tab", tuning: dict[int, int] | None = None,
             capo: int = 0, triplets: bool = False) -> str:
    ext = os.path.splitext(out_path)[1].lower()
    if ext not in _EXT_TO_VERSION:
        raise ValueError(f"Formato no soportado: {ext} (usa .gp5/.gp4/.gp3)")
    song = build_song(tab_notes, bpm=bpm, title=title, tuning=tuning, capo=capo,
                      triplets=triplets)
    gp.write(song, out_path, version=_EXT_TO_VERSION[ext])
    return out_path


def write_multitrack_gp(instruments: list[dict], out_path: str, bpm: float = 120.0,
                        title: str = "Audio2Tab", beats=None,
                        triplets: bool = False) -> str:
    ext = os.path.splitext(out_path)[1].lower()
    if ext not in _EXT_TO_VERSION:
        raise ValueError(f"Formato no soportado: {ext} (usa .gp5/.gp4/.gp3)")
    song = build_multitrack_song(instruments, bpm=bpm, title=title, beats=beats,
                                 triplets=triplets)
    gp.write(song, out_path, version=_EXT_TO_VERSION[ext])
    return out_path
