"""Etapa de re-procesamiento por región (Fase 5).

Permite al usuario seleccionar un rango de compases y volver a transcribir
o re-digitalizar únicamente esa sección de audio/MIDI con nuevos parámetros,
empalmando el resultado en la tablatura original.
"""
from __future__ import annotations

import json
import os
import sys

from . import to_gp, to_tab, transcribe, techniques
from .types import TabNote, Note
from .runner import PipelineParams


def reprocess_region(
    work_dir: str,
    original_input_path: str,
    bpm: float,
    original_params: dict,
    start_measure: int,
    end_measure: int,
    overrides: dict,
) -> dict:
    """Re-procesa una región de compases y empalma los resultados en la tablatura existente."""
    # 1. Combinar parámetros originales con sobrescrituras
    merged_params_dict = {**original_params, **overrides}
    params = PipelineParams(**merged_params_dict)

    # 2. Calcular los límites de tiempo para los compases seleccionados (1-based)
    slots_per_measure = 16
    grid = (60.0 / bpm) / 4.0  # segundos por semicorchea
    start_time = (start_measure - 1) * slots_per_measure * grid
    end_time = end_measure * slots_per_measure * grid
    duration = end_time - start_time

    # 3. Definir afinaciones de digitación
    tuning_dict = to_tab.TUNINGS.get(params.tuning, to_tab.STANDARD_TUNING)
    digitizer_tuning = tuning_dict
    if params.capo > 0:
        digitizer_tuning = {string: pitch + params.capo for string, pitch in tuning_dict.items()}

    kept_notes: list[TabNote] = []

    # 4. Transcribir y digitalizar la región
    if params.from_midi:
        print(f"[reprocess] Procesando desde MIDI: {start_time:.2f}s - {end_time:.2f}s", file=sys.stderr)
        all_midi_notes = transcribe.notes_from_midi_file(original_input_path)
        # Seleccionar las notas del MIDI original que inician en el rango
        region_notes = [n for n in all_midi_notes if start_time <= n.start < end_time]
        region_tab = to_tab.assign_tab(region_notes, tuning=digitizer_tuning, open_string_pref=params.open_string_pref)
        kept_notes = region_tab
    else:
        # Resolver ruta del audio fuente
        audio_src = original_input_path
        base_name = os.path.splitext(os.path.basename(original_input_path))[0]
        isolated_path = os.path.join(work_dir, "htdemucs", base_name, "other.wav")
        input_wav_path = os.path.join(work_dir, "input.wav")

        if os.path.exists(isolated_path):
            audio_src = isolated_path
        elif os.path.exists(input_wav_path):
            audio_src = input_wav_path

        print(f"[reprocess] Procesando desde audio: {audio_src} ({start_time:.2f}s - {end_time:.2f}s)", file=sys.stderr)

        # Padding de pre-proceso (250 ms hacia atrás)
        padded_start_time = max(0.0, start_time - 0.25)
        cut_offset = start_time - padded_start_time
        padded_duration = duration + cut_offset

        # Cargar y cortar audio con librosa
        try:
            import librosa
            import soundfile as sf
        except ImportError:
            raise RuntimeError("Librosa/Soundfile no están instalados; no se puede re-procesar audio.")

        y, sr = librosa.load(audio_src, sr=44100, mono=True, offset=padded_start_time, duration=padded_duration)
        region_wav_path = os.path.join(work_dir, "region_temp.wav")
        sf.write(region_wav_path, y, sr)

        try:
            # Transcribir el fragmento cortado
            if params.transcriber == "mr_mt3":
                notes = transcribe.transcribe_mt3(region_wav_path, model="mr_mt3")
            else:
                notes = transcribe.transcribe_audio(
                    region_wav_path,
                    onset_threshold=params.onset_threshold,
                    min_note_length_ms=params.min_note_ms,
                )

            # Asignar digitación
            region_tab = to_tab.assign_tab(notes, tuning=digitizer_tuning, open_string_pref=params.open_string_pref)

            # Desplazar timestamps y filtrar notas dentro del padding
            for n in region_tab:
                actual_start = n.start + padded_start_time
                actual_end = n.end + padded_start_time
                # Permitimos una tolerancia de 20ms en el borde izquierdo para capturar ataques
                if (start_time - 0.02) <= actual_start < end_time:
                    # Forzar a límites exactos si caen levemente fuera por la tolerancia
                    n.start = max(start_time, actual_start)
                    n.end = actual_end
                    kept_notes.append(n)
        finally:
            if os.path.exists(region_wav_path):
                try:
                    os.remove(region_wav_path)
                except Exception:
                    pass

    # 5. Cargar tablatura previa para empalmar
    tab_notes_json_path = os.path.join(work_dir, "tab_notes.json")
    if not os.path.exists(tab_notes_json_path):
        raise FileNotFoundError("No se encontró el archivo de notas intermedias tab_notes.json. Debes transcribir primero.")

    with open(tab_notes_json_path, "r", encoding="utf-8") as f:
        old_notes_data = json.load(f)

    old_notes = [
        TabNote(
            pitch=d["pitch"],
            start=d["start"],
            end=d["end"],
            velocity=d["velocity"],
            string=d["string"],
            fret=d["fret"],
            hopo=d.get("hopo", False),
            slide=d.get("slide", False),
            vibrato=d.get("vibrato", False),
            bend_type=d.get("bend_type"),
            bend_value=d.get("bend_value", 0),
        )
        for d in old_notes_data
    ]

    # Eliminar notas del rango a re-procesar (excluyendo el margen)
    old_kept = [n for n in old_notes if not (start_time <= n.start < end_time)]

    # 6. Combinar y volver a ordenar
    merged_notes = old_kept + kept_notes
    merged_notes.sort(key=lambda n: n.start)

    # 7. Re-analizar técnicas expresivas (especialmente en los límites)
    merged_notes = techniques.detect_techniques(merged_notes)

    # 8. Guardar nuevo tab_notes.json
    new_notes_data = [
        {
            "pitch": n.pitch,
            "start": n.start,
            "end": n.end,
            "velocity": n.velocity,
            "string": n.string,
            "fret": n.fret,
            "hopo": n.hopo,
            "slide": n.slide,
            "vibrato": n.vibrato,
            "bend_type": n.bend_type,
            "bend_value": n.bend_value,
        }
        for n in merged_notes
    ]
    with open(tab_notes_json_path, "w", encoding="utf-8") as f:
        json.dump(new_notes_data, f, indent=2)

    # 9. Escribir archivo Guitar Pro actualizado
    out_format = params.output_format.lstrip(".")
    out_path = os.path.join(work_dir, f"output.{out_format}")
    title = os.path.splitext(os.path.basename(original_input_path))[0]
    to_gp.write_gp(merged_notes, out_path, bpm=bpm, title=title, tuning=tuning_dict, capo=params.capo)

    return {
        "output": out_path,
        "n_notes": len(merged_notes),
        "n_reprocessed": len(kept_notes),
    }
