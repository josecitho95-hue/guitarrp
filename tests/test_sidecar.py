"""Test de integración del sidecar (Fase 2).

Usa el camino `from_midi` (rápido, sin modelos pesados) para ejercitar el ciclo
completo: crear job -> cola en proceso -> SQLite -> descargar resultado.
"""
from __future__ import annotations

import os
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# La carpeta de datos debe fijarse ANTES de importar el server (config lee env al importar).
os.environ.setdefault("AUDIO2TAB_DATA", tempfile.mkdtemp(prefix="a2t_test_"))

from fastapi.testclient import TestClient  # noqa: E402

from sidecar.server import app  # noqa: E402


def test_job_lifecycle_from_midi():
    midi = os.path.join(ROOT, "samples", "riff.mid")
    assert os.path.exists(midi), "falta samples/riff.mid"

    with TestClient(app) as client:
        assert client.get("/healthz").json()["status"] == "ok"

        with open(midi, "rb") as f:
            r = client.post(
                "/jobs",
                files={"file": ("riff.mid", f, "audio/midi")},
                data={"from_midi": "true", "output_format": "gp5", "bpm": "120"},
            )
        assert r.status_code == 200, r.text
        job_id = r.json()["id"]

        status = {}
        for _ in range(60):
            status = client.get(f"/jobs/{job_id}").json()
            if status["status"] in ("done", "error"):
                break
            time.sleep(0.5)

        assert status["status"] == "done", status
        assert status["n_notes"] == 14, status

        r = client.get(f"/jobs/{job_id}/result")
        assert r.status_code == 200
        assert r.content[:4] == b"FICH" or len(r.content) > 100  # GP file


if __name__ == "__main__":
    test_job_lifecycle_from_midi()
    print("PASS  test_job_lifecycle_from_midi")
