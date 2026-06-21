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
        pb_list = [(float(pb.time), int(pb.pitch)) for pb in getattr(inst, "pitch_bends", [])]
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


def _mt3_result_to_pm(result):
    """Normaliza la salida de mdl.transcribe (PrettyMIDI o mido.MidiFile)."""
    if hasattr(result, "instruments"):
        return result
    import os
    import tempfile

    import pretty_midi
    tmp = os.path.join(tempfile.gettempdir(), "a2t_mt3_out.mid")
    result.save(tmp)
    return pretty_midi.PrettyMIDI(tmp)


def transcribe_mt3(audio_path: str, model: str = "mr_mt3",
                   guitar_only: bool = False, time_scale: float | None = None,
                   device: str | None = None, chunk_s: float = 30.0,
                   overlap_s: float = 2.0, progress=None) -> list[Note]:
    """Transcribe con la familia MT3 (mt3-infer). Auto-descarga checkpoint.

    Path A SOTA. Requiere los shims de `_mt3_compat` para correr el T5 vendorizado
    sobre transformers 5.x. `mr_mt3` es el que funciona de forma fiable en el stack
    actual (yourmt3 tiene incompatibilidades profundas; mt3_pytorch falla al clonar
    en Windows). `guitar_only=True` filtra a programas de guitarra (24-31).
    `time_scale` corrige la deriva temporal del conversor (ver MT3_TIME_SCALE).

    El audio se procesa en bloques de `chunk_s` segundos con `overlap_s` de solape
    de contexto (descartado al empalmar) para dar visibilidad de progreso/ETA y
    acotar el pico de VRAM en canciones largas. `progress(frac, msg)` se llama por
    bloque; si es None, se imprime a stdout.
    """
    import time as _time

    import librosa

    from . import _mt3_compat
    from .gpu import get_device

    _mt3_compat.apply()
    if time_scale is None:
        time_scale = MT3_TIME_SCALE.get(model, 1.0)

    if device is None:
        device = get_device()

    if model not in _MT3_MODELS:
        from mt3_infer import load_model
        _MT3_MODELS[model] = load_model(model, device=device)
    mdl = _MT3_MODELS[model]

    sr = 16000
    y, _ = librosa.load(audio_path, sr=sr, mono=True)
    dur = len(y) / sr

    # Un solo bloque si la pista cabe holgadamente; si no, trocear con solape.
    step = max(chunk_s, 1.0)
    win = step + max(overlap_s, 0.0)
    starts = [0.0] if dur <= win else [i * step for i in range(int(dur // step) + 1)]
    n_chunks = len(starts)

    out: list[Note] = []
    t0 = _time.time()
    for ci, s0 in enumerate(starts):
        s1 = min(s0 + win, dur)
        seg = y[int(s0 * sr):int(s1 * sr)]
        if len(seg) < int(0.1 * sr):
            continue
        pm = _mt3_result_to_pm(mdl.transcribe(seg, sr=sr))
        # Limite del nucleo de este bloque: descartar notas del solo solape (las
        # cubre el siguiente bloque desde su nucleo). El ultimo bloque se queda todo.
        core_end = (s1 - s0) if ci == n_chunks - 1 else step
        for inst in pm.instruments:
            if getattr(inst, "is_drum", False):
                continue
            if guitar_only and not (24 <= getattr(inst, "program", 0) <= 31):
                continue
            for n in inst.notes:
                if float(n.start) >= core_end:
                    continue
                out.append(Note(
                    pitch=int(n.pitch),
                    start=(s0 + float(n.start)) * time_scale,
                    end=(s0 + float(n.end)) * time_scale,
                    velocity=int(n.velocity),
                ))
        done = ci + 1
        elapsed = _time.time() - t0
        eta = (elapsed / done) * (n_chunks - done)
        msg = (f"[mt3] bloque {done}/{n_chunks} "
               f"({s0:.0f}-{s1:.0f}s de {dur:.0f}s) "
               f"| {elapsed:.0f}s transcurridos, ETA ~{eta:.0f}s")
        if progress is not None:
            progress(done / n_chunks, msg)
        else:
            print(msg, flush=True)

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
