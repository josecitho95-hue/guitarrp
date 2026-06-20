"""Tests de integración del CLI de Audio2Tab (Fase 4).

Ejecuta el script cli/transcribe.py como un subproceso para validar que la interfaz
por línea de comandos analiza, procesa y genera archivos con los parámetros correctos.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import guitarpro as gp

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_cli_basic():
    midi = os.path.join(ROOT, "samples", "riff.mid")
    assert os.path.exists(midi), "falta samples/riff.mid"

    with tempfile.TemporaryDirectory() as d:
        out = os.path.join(d, "cli_basic.gp5")
        cmd = [
            sys.executable,
            os.path.join(ROOT, "cli", "transcribe.py"),
            midi,
            "--from-midi",
            "-o", out,
            "--bpm", "120"
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        assert res.returncode == 0
        assert os.path.exists(out)

        song = gp.parse(out)
        assert song.tempo == 120
        track = song.tracks[0]
        assert track.offset == 0  # sin capo
        assert len(track.strings) == 6


def test_cli_advanced_parameters():
    midi = os.path.join(ROOT, "samples", "riff.mid")
    assert os.path.exists(midi), "falta samples/riff.mid"

    with tempfile.TemporaryDirectory() as d:
        out = os.path.join(d, "cli_advanced.gp5")
        cmd = [
            sys.executable,
            os.path.join(ROOT, "cli", "transcribe.py"),
            midi,
            "--from-midi",
            "-o", out,
            "--bpm", "144",
            "--tuning", "drop_d",
            "--capo", "4"
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        assert res.returncode == 0
        assert os.path.exists(out)

        song = gp.parse(out)
        assert song.tempo == 144
        track = song.tracks[0]
        assert track.offset == 4  # capo en traste 4
        # Afinación Drop D: DADGBE
        # Las notas correspondientes en MIDI son:
        # Cuerda 1: E (64)
        # Cuerda 2: B (59)
        # Cuerda 3: G (55)
        # Cuerda 4: D (50)
        # Cuerda 5: A (45)
        # Cuerda 6: D (38)
        assert track.strings[5].value == 38  # 6ª cuerda Drop D
        assert track.strings[4].value == 45
        assert track.strings[0].value == 64


if __name__ == "__main__":
    print("Corriendo tests del CLI...")
    test_cli_basic()
    print("PASS  test_cli_basic")
    test_cli_advanced_parameters()
    print("PASS  test_cli_advanced_parameters")
    print("\nTodos los tests del CLI pasaron con éxito.")
