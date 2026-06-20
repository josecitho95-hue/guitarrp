"""Etapa 1: Preproceso de audio.

En Fase 0 es mayormente passthrough: el transcriptor (Basic Pitch) carga y
remuestrea el audio internamente. Si librosa/soundfile estan disponibles, ofrece
conversion a WAV mono normalizado (util para Demucs o para inspeccion).
"""
from __future__ import annotations

import os


def to_wav_mono(in_path: str, out_path: str, target_sr: int = 44100) -> str:
    """Convierte a WAV mono normalizado si hay librosa+soundfile; si no, passthrough."""
    try:
        import librosa
        import soundfile as sf
    except ImportError:
        return in_path

    y, _ = librosa.load(in_path, sr=target_sr, mono=True)
    peak = float(abs(y).max()) if y.size else 0.0
    if peak > 0:
        y = y / peak * 0.97
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    sf.write(out_path, y, target_sr)
    return out_path
