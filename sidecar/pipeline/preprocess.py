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

    NO intenta auto-corregir la octava de tempo (doblar/halvar): medido sobre un
    corpus (rock clásico + thrash), el doblado agresivo acertaba 1/7 canciones y
    arruinaba el resto — la octava de tempo es ambigua desde audio. librosa crudo
    acierta la mayoría de la música normal. Para el caso raro (thrash detectado a
    mitad, p.ej. Master of Puppets 103→206) usar el override `--bpm`. El tempo solo
    afecta la NOTACIÓN (compases), no el contenido de notas ni la métrica chroma.
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
        if not (30 <= bpm <= 300):
            return default
        return round(bpm, 1)
    except Exception:
        return default


def estimate_beats(audio_path: str, sr: int = 22050, target_bpm: float | None = None):
    """Rastrea los beats del audio. Devuelve (beat_times: np.ndarray, bpm).

    Permite cuantizar relativo a los beats reales (corrige el desfase de fase del
    grid fijo, que asume rejilla desde t=0). `target_bpm` (p.ej. el de
    estimate_tempo, ya corregido de half-time) sirve de referencia: si el pulso
    detectado está cerca de la mitad, se insertan beats intermedios para llegar a
    la rejilla real de negras (librosa suele detectar half-time en metal rápido).
    """
    import numpy as np
    try:
        import librosa
    except ImportError:
        return np.array([]), 120.0
    try:
        y, _ = librosa.load(audio_path, sr=sr, mono=True)
        if y.size == 0:
            return np.array([]), 120.0
        tempo, beats = librosa.beat.beat_track(y=y, sr=sr, units="time")
        bpm = float(tempo if not hasattr(tempo, "__len__") else tempo[0])
        beats = np.asarray(beats, dtype=float)
        if len(beats) < 2:
            return beats, round(bpm, 1)

        # Corrección half-time: duplicar beats si el pulso está a ~la mitad del
        # tempo de referencia (o, sin referencia, si la densidad de onsets es alta).
        double = False
        if target_bpm and target_bpm > 0:
            if abs(bpm * 2 - target_bpm) < 0.2 * target_bpm:
                double = True
        else:
            onset_env = librosa.onset.onset_strength(y=y, sr=sr)
            onsets = librosa.onset.onset_detect(y=y, sr=sr, onset_envelope=onset_env)
            onset_rate = len(onsets) / (len(y) / sr)
            double = 60 <= bpm <= 140 and onset_rate > 5.0
        if double:
            mids = (beats[:-1] + beats[1:]) / 2.0
            beats = np.sort(np.concatenate([beats, mids]))
            bpm *= 2
        return beats, round(bpm, 1)
    except Exception:
        return np.array([]), 120.0


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
