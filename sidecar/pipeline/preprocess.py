"""Etapa 1: Preproceso de audio.

Carga/normaliza el audio y, opcionalmente, calibra la afinación (SH-01) para
cuadrarla a A=440 Hz antes de la transcripción.
"""
from __future__ import annotations

import os


def estimate_tuning_cents(in_path: str, sr: int = 22050) -> float:
    """Estima la desviación de afinación del audio en cents (0 = A440).

    Usa `librosa.estimate_tuning` (fracción de semitono) -> cents. Si librosa no
    está disponible, devuelve 0.0.
    """
    try:
        import librosa
    except ImportError:
        return 0.0
    y, _ = librosa.load(in_path, sr=sr, mono=True)
    if y.size == 0:
        return 0.0
    tuning = float(librosa.estimate_tuning(y=y, sr=sr))  # fracción de semitono
    return tuning * 100.0


def estimate_tempo(audio_path: str, sr: int = 22050, default: float = 120.0) -> float:
    """Estima el tempo global (BPM) del audio con librosa.

    Es una estimación (puede caer en mitad/doble del tempo real); sirve como
    valor por defecto, sobrescribible por el usuario. Si falta librosa o falla,
    devuelve `default`.
    """
    try:
        import librosa
    except ImportError:
        return default
    try:
        y, _ = librosa.load(audio_path, sr=sr, mono=True)
        if y.size == 0:
            return default
        tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
        bpm = float(tempo if not hasattr(tempo, "__len__") else tempo[0])
        return round(bpm, 1) if 30 <= bpm <= 300 else default
    except Exception:
        return default


def tempo_from_midi(midi_path: str, default: float = 120.0) -> float:
    """Lee el tempo de un MIDI (primer cambio de tempo)."""
    try:
        import pretty_midi
        pm = pretty_midi.PrettyMIDI(midi_path)
        _, tempi = pm.get_tempo_changes()
        if len(tempi):
            return round(float(tempi[0]), 1)
    except Exception:
        pass
    return default


def to_wav_mono(in_path: str, out_path: str, target_sr: int = 44100,
                calibrate: bool = False, max_correction_cents: float = 60.0) -> str:
    """Convierte a WAV mono normalizado; opcionalmente calibra la afinación (SH-01).

    `calibrate=True` estima la desviación de afinación y aplica un pitch-shift
    microscópico para cuadrarla a A440. Solo corrige desviaciones pequeñas
    (< `max_correction_cents`): una desviación grande suele ser una afinación
    alternativa intencional (p.ej. medio tono abajo), que NO se debe "arreglar".
    Si faltan librosa/soundfile, hace passthrough.
    """
    try:
        import librosa
        import soundfile as sf
    except ImportError:
        return in_path

    y, _ = librosa.load(in_path, sr=target_sr, mono=True)
    if calibrate and y.size:
        tuning = float(librosa.estimate_tuning(y=y, sr=target_sr))  # fracción de semitono
        cents = tuning * 100.0
        if 0 < abs(cents) <= max_correction_cents:
            y = librosa.effects.pitch_shift(y, sr=target_sr, n_steps=-tuning)

    peak = float(abs(y).max()) if y.size else 0.0
    if peak > 0:
        y = y / peak * 0.97
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    sf.write(out_path, y, target_sr)
    return out_path
