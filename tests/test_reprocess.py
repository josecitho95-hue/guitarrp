"""Tests de integración para el re-procesamiento por región (Fase 5).

Valida el cálculo de los tiempos del rango, el filtrado de notas previas
y el correcto empalme y regeneración de archivos de salida de Guitar Pro.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import guitarpro as gp

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from sidecar.pipeline import reprocess, to_tab  # noqa: E402
from sidecar.pipeline.types import TabNote  # noqa: E402


def test_reprocess_region_midi():
    midi_path = os.path.join(ROOT, "samples", "riff.mid")
    assert os.path.exists(midi_path), "falta samples/riff.mid"

    with tempfile.TemporaryDirectory() as work_dir:
        # 1. Crear notas falsas iniciales y guardarlas en tab_notes.json
        # Vamos a simular que ya se transcribió y digitó la pieza.
        # Riff.mid tiene notas. Vamos a crear un tab_notes.json ficticio con 5 notas sencillas.
        initial_notes = [
            # Compás 1: t=0.0 a 2.0 (BPM 120 -> 1 compás = 2 segundos)
            {"pitch": 60, "start": 0.0, "end": 0.5, "velocity": 90, "string": 5, "fret": 3},
            {"pitch": 62, "start": 0.5, "end": 1.0, "velocity": 90, "string": 4, "fret": 0},
            # Compás 2: t=2.0 a 4.0
            {"pitch": 64, "start": 2.0, "end": 2.5, "velocity": 90, "string": 4, "fret": 2},
            {"pitch": 65, "start": 2.5, "end": 3.0, "velocity": 90, "string": 4, "fret": 3},
            # Compás 3: t=4.0 a 6.0
            {"pitch": 67, "start": 4.0, "end": 4.5, "velocity": 90, "string": 3, "fret": 0},
        ]
        
        tab_notes_path = os.path.join(work_dir, "tab_notes.json")
        with open(tab_notes_path, "w", encoding="utf-8") as f:
            json.dump(initial_notes, f)

        # 2. Configurar parámetros originales
        original_params = {
            "from_midi": True,
            "transcriber": "mr_mt3",
            "tuning": "standard",
            "capo": 0,
            "open_string_pref": "media",
            "output_format": "gp5",
        }

        # 3. Re-procesar únicamente el Compás 2 (de t=2.0s a t=4.0s)
        # Queremos sobrescribir la preferencia de cuerdas al aire a "alta"
        overrides = {
            "open_string_pref": "alta"
        }

        res = reprocess.reprocess_region(
            work_dir=work_dir,
            original_input_path=midi_path,
            bpm=120.0,
            original_params=original_params,
            start_measure=2,
            end_measure=2,
            overrides=overrides,
        )

        assert res["output"] == os.path.join(work_dir, "output.gp5")
        assert res["n_notes"] > 0
        assert os.path.exists(res["output"])

        # 4. Cargar el tab_notes.json generado y verificar que se combinaron las notas
        with open(tab_notes_path, "r", encoding="utf-8") as f:
            merged_notes = json.load(f)

        # Notas en compás 1 (t < 2.0) y compás 3 (t >= 4.0) deben permanecer intactas
        c1_notes = [n for n in merged_notes if n["start"] < 2.0]
        c3_notes = [n for n in merged_notes if n["start"] >= 4.0]
        
        assert len(c1_notes) == 2
        assert c1_notes[0]["pitch"] == 60
        assert c1_notes[1]["pitch"] == 62
        
        assert len(c3_notes) == 1
        assert c3_notes[0]["pitch"] == 67

        # Las notas del compás 2 deben haber sido reemplazadas por las notas reales extraídas del MIDI en esa sección.
        c2_notes = [n for n in merged_notes if 2.0 <= n["start"] < 4.0]
        assert len(c2_notes) > 0  # riff.mid tiene notas en el compás 2

        # 5. Parsear el archivo de salida de Guitar Pro para corroborar que es legible
        song = gp.parse(res["output"])
        assert song.tempo == 120
        assert song.title == "riff"


if __name__ == "__main__":
    print("Corriendo pruebas de re-procesado por región...")
    test_reprocess_region_midi()
    print("PASS  test_reprocess_region_midi")
    print("\nTodos los tests de re-procesado pasaron con éxito.")
