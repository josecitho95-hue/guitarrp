"""Orquestador del pipeline (reutilizado por CLI y sidecar).

Encadena las etapas y reporta progreso vía callback `on_progress(stage, pct)`.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Callable

from . import preprocess, separate, to_gp, to_tab, transcribe

ProgressCb = Callable[[str, float], None]

# Etiquetas de estado (coinciden con los estados del job del sidecar)
STAGES = ("queued", "preprocess", "separating", "transcribing", "tabbing", "done", "error")


@dataclass
class PipelineParams:
    transcriber: str = "mr_mt3"        # "mr_mt3" (SOTA) | "basic_pitch"
    separate: bool = False             # aislar guitarra con Demucs
    device: str = "cpu"                # dispositivo Demucs: cpu | cuda
    auto_bpm: bool = True              # detectar el tempo automáticamente
    bpm: float = 120.0                 # usado solo si auto_bpm=False (override)
    output_format: str = "gp5"         # gp5 | gp4 | gp3
    calibrate_tuning: bool = False     # SH-01: cuadrar a A440
    open_string_pref: str = "media"    # SH-02: alta | media | baja
    onset_threshold: float = 0.5
    min_note_ms: float = 80.0
    from_midi: bool = False


def run_pipeline(input_path: str, out_path: str, params: PipelineParams,
                 work_dir: str, on_progress: ProgressCb | None = None) -> dict:
    """Ejecuta el pipeline completo y escribe el archivo Guitar Pro.

    Devuelve un dict con la ruta de salida y conteos. Lanza excepción si falla.
    """
    def prog(stage: str, pct: float) -> None:
        if on_progress:
            on_progress(stage, pct)

    os.makedirs(work_dir, exist_ok=True)
    title = os.path.splitext(os.path.basename(input_path))[0]

    if params.from_midi:
        prog("transcribing", 0.4)
        notes = transcribe.notes_from_midi_file(input_path)
        bpm = preprocess.tempo_from_midi(input_path) if params.auto_bpm else params.bpm
    else:
        prog("preprocess", 0.05)
        wav = preprocess.to_wav_mono(
            input_path, os.path.join(work_dir, "input.wav"),
            calibrate=params.calibrate_tuning)
        # Tempo automático del audio (override manual si auto_bpm=False).
        bpm = preprocess.estimate_tempo(wav) if params.auto_bpm else params.bpm

        if params.separate:
            prog("separating", 0.2)
            wav = separate.separate_guitar(wav, work_dir, device=params.device)

        prog("transcribing", 0.4)
        if params.transcriber == "mr_mt3":
            notes = transcribe.transcribe_mt3(wav, model="mr_mt3")
        else:
            notes = transcribe.transcribe_audio(
                wav, onset_threshold=params.onset_threshold,
                min_note_length_ms=params.min_note_ms)

    if not notes:
        raise RuntimeError("No se detectaron notas en el audio.")

    prog("tabbing", 0.8)
    tab = to_tab.assign_tab(notes, open_string_pref=params.open_string_pref)

    out_path = os.path.splitext(out_path)[0] + "." + params.output_format.lstrip(".")
    to_gp.write_gp(tab, out_path, bpm=bpm, title=title)

    prog("done", 1.0)
    return {"output": out_path, "n_notes": len(notes), "n_tab": len(tab), "bpm": round(bpm, 1)}
