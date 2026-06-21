"""Orquestador del pipeline (reutilizado por CLI y sidecar).

Encadena las etapas y reporta progreso vía callback `on_progress(stage, pct)`.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Callable

from . import preprocess, separate, to_gp, to_tab, transcribe, techniques

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
    tuning: str = "standard"           # standard | drop_d
    capo: int = 0                      # traste del capo (0 = sin capo)
    onset_threshold: float = 0.5
    min_note_ms: float = 80.0
    from_midi: bool = False
    multi_instrument: bool = False    # guitarra + bajo en pistas separadas (requiere separate)
    stereo_guitars: bool = False      # 2 guitarras paneadas L/R (requiere multi_instrument)


def _stem_to_tab(stem_wav: str, params: PipelineParams, tuning: dict,
                 min_freq: float, max_freq: float, mt3_progress=None):
    """Transcribe un stem -> notas -> tablatura (con técnicas). Devuelve [] si vacío."""
    if params.transcriber == "mr_mt3":
        notes = transcribe.transcribe_mt3(
            stem_wav, model="mr_mt3", device=params.device, progress=mt3_progress)
    else:
        notes = transcribe.transcribe_audio(
            stem_wav, onset_threshold=params.onset_threshold,
            min_note_length_ms=params.min_note_ms, min_freq=min_freq, max_freq=max_freq)
    if not notes:
        return []
    tab = to_tab.assign_tab(notes, tuning=tuning, open_string_pref=params.open_string_pref)
    return techniques.detect_techniques(tab)


def _save_tab_json(work_dir: str, tab) -> None:
    import json
    data = [
        {"pitch": n.pitch, "start": n.start, "end": n.end, "velocity": n.velocity,
         "string": n.string, "fret": n.fret, "hopo": n.hopo, "slide": n.slide,
         "vibrato": n.vibrato, "bend_type": n.bend_type, "bend_value": n.bend_value}
        for n in tab
    ]
    with open(os.path.join(work_dir, "tab_notes.json"), "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


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

        stems = None
        if params.separate:
            prog("separating", 0.2)
            if params.multi_instrument and params.stereo_guitars:
                # Separa por canal desde el original estéreo (la versión mono ya
                # perdió el paneo). Recupera las 2 guitarras L/R.
                stems = separate.separate_stereo(input_path, work_dir, device=params.device)
            else:
                stems = separate.separate_all(wav, work_dir, device=params.device)

        out_path = os.path.splitext(out_path)[0] + "." + params.output_format.lstrip(".")
        guitar_tuning = to_tab.TUNINGS.get(params.tuning, to_tab.STANDARD_TUNING)
        guitar_dig = guitar_tuning
        if params.capo > 0:
            guitar_dig = {s: p + params.capo for s, p in guitar_tuning.items()}

        # --- Multi-instrumento: guitarra + bajo (+ batería) en pistas separadas ---
        if params.multi_instrument and stems and "bass" in stems:
            prog("transcribing", 0.4)

            def _gtr_prog(frac, msg):
                print(msg, flush=True)
                prog("transcribing", 0.4 + 0.15 * frac)

            def _bass_prog(frac, msg):
                print(msg, flush=True)
                prog("transcribing", 0.55 + 0.1 * frac)

            def _drum_prog(frac, msg):
                print(msg, flush=True)
                prog("transcribing", 0.65 + 0.13 * frac)

            # Guitarra(s): 2 pistas si hay canales paneados L/R, si no 1.
            guitar_insts = []
            if "guitar_l" in stems and "guitar_r" in stems:
                gl = _stem_to_tab(stems["guitar_l"], params, guitar_dig,
                                  transcribe.GUITAR_MIN_HZ, transcribe.GUITAR_MAX_HZ, _gtr_prog)
                gr = _stem_to_tab(stems["guitar_r"], params, guitar_dig,
                                  transcribe.GUITAR_MIN_HZ, transcribe.GUITAR_MAX_HZ, _gtr_prog)
                guitar_insts = [
                    {"name": "Guitar L", "tuning": guitar_tuning, "tab_notes": gl,
                     "capo": params.capo, "midi_program": 30},
                    {"name": "Guitar R", "tuning": guitar_tuning, "tab_notes": gr,
                     "capo": params.capo, "midi_program": 30},
                ]
            else:
                gt = _stem_to_tab(stems.get("guitar", wav), params, guitar_dig,
                                  transcribe.GUITAR_MIN_HZ, transcribe.GUITAR_MAX_HZ, _gtr_prog)
                guitar_insts = [{"name": "Guitar", "tuning": guitar_tuning, "tab_notes": gt,
                                 "capo": params.capo, "midi_program": 30}]

            prog("transcribing", 0.55)
            bass_tab = _stem_to_tab(stems["bass"], params, to_tab.BASS_TUNING,
                                    30.0, 500.0, _bass_prog)

            # Batería: solo mr_mt3 transcribe percusión (instrumentos is_drum).
            drum_tab = []
            if "drums" in stems:
                prog("transcribing", 0.65)
                drum_notes = transcribe.transcribe_mt3(
                    stems["drums"], model="mr_mt3", device=params.device,
                    drums_only=True, progress=_drum_prog)
                drum_tab = to_tab.assign_drums(drum_notes)

            guitar_total = sum(len(g["tab_notes"]) for g in guitar_insts)
            if not guitar_total and not bass_tab and not drum_tab:
                raise RuntimeError("No se detectaron notas en el audio.")

            prog("tabbing", 0.8)
            instruments = list(guitar_insts)
            instruments.append({"name": "Bass", "tuning": to_tab.BASS_TUNING,
                                "tab_notes": bass_tab, "midi_program": 33})
            if drum_tab:
                instruments.append({"name": "Drums", "tab_notes": drum_tab,
                                    "percussion": True})
            to_gp.write_multitrack_gp(instruments, out_path, bpm=bpm, title=title)
            _save_tab_json(work_dir, guitar_insts[0]["tab_notes"])
            prog("done", 1.0)
            n_total = guitar_total + len(bass_tab) + len(drum_tab)
            return {"output": out_path, "n_tab": n_total, "n_notes": n_total,
                    "bpm": round(bpm, 1), "tracks": [i["name"] for i in instruments]}

        # --- Single-track (guitarra) ---
        if stems:
            wav = stems.get("guitar", wav)
        prog("transcribing", 0.4)
        if params.transcriber == "mr_mt3":
            def _mt3_prog(frac, msg):
                print(msg, flush=True)
                prog("transcribing", 0.4 + 0.35 * frac)
            notes = transcribe.transcribe_mt3(
                wav, model="mr_mt3", device=params.device, progress=_mt3_prog)

        else:
            notes = transcribe.transcribe_audio(
                wav, onset_threshold=params.onset_threshold,
                min_note_length_ms=params.min_note_ms)

    if not notes:
        raise RuntimeError("No se detectaron notas en el audio.")

    prog("tabbing", 0.8)
    tuning_dict = to_tab.TUNINGS.get(params.tuning, to_tab.STANDARD_TUNING)
    digitizer_tuning = tuning_dict
    if params.capo > 0:
        digitizer_tuning = {string: pitch + params.capo for string, pitch in tuning_dict.items()}

    tab = to_tab.assign_tab(notes, tuning=digitizer_tuning, open_string_pref=params.open_string_pref)

    # Detectar técnicas expresivas (Tier 1)
    tab = techniques.detect_techniques(tab)

    out_path = os.path.splitext(out_path)[0] + "." + params.output_format.lstrip(".")
    to_gp.write_gp(tab, out_path, bpm=bpm, title=title, tuning=tuning_dict, capo=params.capo)
    _save_tab_json(work_dir, tab)

    prog("done", 1.0)
    return {"output": out_path, "n_notes": len(notes), "n_tab": len(tab), "bpm": round(bpm, 1)}
