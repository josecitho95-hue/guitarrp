"""Etapa 3: Audio -> MIDI (notas).

Fase 0 usa Basic Pitch (Spotify) como transcriptor por defecto: ligero, corre en
CPU y es fiable de instalar. Los modelos SOTA (High-Res, YourMT3+) se enchufan en
Fase 1 detras de la misma interfaz `transcribe_audio() -> list[Note]`.
"""
from __future__ import annotations

from .types import Note

# Rango util de la guitarra (Hz) para filtrar espurios.
GUITAR_MIN_HZ = 70.0
GUITAR_MAX_HZ = 1400.0


def notes_from_pretty_midi(pm) -> list[Note]:
    out: list[Note] = []
    for inst in pm.instruments:
        if getattr(inst, "is_drum", False):
            continue
        for n in inst.notes:
            out.append(Note(pitch=int(n.pitch), start=float(n.start),
                            end=float(n.end), velocity=int(n.velocity)))
    out.sort(key=lambda n: (n.start, n.pitch))
    return out


def notes_from_midi_file(path: str) -> list[Note]:
    import pretty_midi
    return notes_from_pretty_midi(pretty_midi.PrettyMIDI(path))


def transcribe_audio(audio_path: str, onset_threshold: float = 0.5,
                     min_note_length_ms: float = 80.0) -> list[Note]:
    """Transcribe un archivo de audio a notas usando Basic Pitch."""
    try:
        from basic_pitch.inference import predict
        from basic_pitch import ICASSP_2022_MODEL_PATH
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "Basic Pitch no esta instalado. Instala con: pip install basic-pitch\n"
            "O usa --from-midi para saltar la etapa de transcripcion."
        ) from exc

    _, midi_data, _ = predict(
        audio_path,
        ICASSP_2022_MODEL_PATH,
        onset_threshold=onset_threshold,
        minimum_note_length=min_note_length_ms,
        minimum_frequency=GUITAR_MIN_HZ,
        maximum_frequency=GUITAR_MAX_HZ,
    )
    return notes_from_pretty_midi(midi_data)
