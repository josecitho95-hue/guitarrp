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
        pb_list = [(float(pb.time), int(pb.value)) for pb in getattr(inst, "pitch_bends", [])]
        for n in inst.notes:
            note_bends = [
                (t, v) for t, v in pb_list
                if n.start - 0.02 <= t <= n.end + 0.02
            ]
            out.append(Note(
                pitch=int(n.pitch), start=float(n.start),
                end=float(n.end), velocity=int(n.velocity),
                pitch_bends=note_bends
            ))
    out.sort(key=lambda n: (n.start, n.pitch))
    return out


def notes_from_midi_file(path: str) -> list[Note]:
    import pretty_midi
    return notes_from_pretty_midi(pretty_midi.PrettyMIDI(path))


def _basic_pitch_model():
    """Prefiere el modelo ONNX (evita TensorFlow y el conflicto de protobuf)."""
    from basic_pitch import ICASSP_2022_MODEL_PATH
    onnx = ICASSP_2022_MODEL_PATH.parent / "nmp.onnx"
    return str(onnx) if onnx.exists() else ICASSP_2022_MODEL_PATH


# --- YourMT3 (Path A SOTA) vía mt3-infer ---

_MT3_MODELS = {}


# Corrección de deriva temporal: mt3-infer 0.1.3 produce un MIDI con el eje de
# tiempo comprimido ~1% (error sistemático de frame-rate). Sin corregir, los onsets
# tardíos se salen de la ventana de 50 ms y el F1 colapsa. Constante empírica
# derivada sobre GuitarSet (generaliza por ser propiedad del conversor, no del audio).
MT3_TIME_SCALE = {"mr_mt3": 1.010}


def transcribe_mt3(audio_path: str, model: str = "mr_mt3",
                   guitar_only: bool = False, time_scale: float | None = None) -> list[Note]:
    """Transcribe con la familia MT3 (mt3-infer). Auto-descarga checkpoint.

    Path A SOTA. Requiere los shims de `_mt3_compat` para correr el T5 vendorizado
    sobre transformers 5.x. `mr_mt3` es el que funciona de forma fiable en el stack
    actual (yourmt3 tiene incompatibilidades profundas; mt3_pytorch falla al clonar
    en Windows). `guitar_only=True` filtra a programas de guitarra (24-31).
    `time_scale` corrige la deriva temporal del conversor (ver MT3_TIME_SCALE).
    """
    import os
    import tempfile

    import librosa

    from . import _mt3_compat
    from .gpu import get_device

    _mt3_compat.apply()
    if time_scale is None:
        time_scale = MT3_TIME_SCALE.get(model, 1.0)

    if model not in _MT3_MODELS:
        from mt3_infer import load_model
        _MT3_MODELS[model] = load_model(model, device=get_device())
    mdl = _MT3_MODELS[model]

    y, _ = librosa.load(audio_path, sr=16000, mono=True)
    result = mdl.transcribe(y, sr=16000)

    # La salida puede ser pretty_midi.PrettyMIDI o mido.MidiFile -> normalizar.
    if hasattr(result, "instruments"):
        pm = result
    else:
        tmp = os.path.join(tempfile.gettempdir(), "a2t_mt3_out.mid")
        result.save(tmp)
        import pretty_midi
        pm = pretty_midi.PrettyMIDI(tmp)

    out: list[Note] = []
    for inst in pm.instruments:
        if getattr(inst, "is_drum", False):
            continue
        if guitar_only and not (24 <= getattr(inst, "program", 0) <= 31):
            continue
        for n in inst.notes:
            out.append(Note(pitch=int(n.pitch), start=float(n.start) * time_scale,
                            end=float(n.end) * time_scale, velocity=int(n.velocity)))
    out.sort(key=lambda n: (n.start, n.pitch))
    return out


def transcribe_audio(audio_path: str, onset_threshold: float = 0.5,
                     min_note_length_ms: float = 80.0) -> list[Note]:
    """Transcribe un archivo de audio a notas usando Basic Pitch (backend ONNX)."""
    try:
        from basic_pitch.inference import predict
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "Basic Pitch no esta instalado. Instala con: pip install 'basic-pitch[onnx]'\n"
            "O usa --from-midi para saltar la etapa de transcripcion."
        ) from exc

    _, midi_data, _ = predict(
        audio_path,
        _basic_pitch_model(),
        onset_threshold=onset_threshold,
        minimum_note_length=min_note_length_ms,
        minimum_frequency=GUITAR_MIN_HZ,
        maximum_frequency=GUITAR_MAX_HZ,
    )
    return notes_from_pretty_midi(midi_data)
