"""Configuración del sidecar."""
from __future__ import annotations

import os

# Carpeta de datos del usuario (artefactos, BD). Sobrescribible por entorno.
DATA_DIR = os.environ.get(
    "AUDIO2TAB_DATA",
    os.path.join(os.path.expanduser("~"), ".audio2tab"),
)
JOBS_DIR = os.path.join(DATA_DIR, "jobs")
DB_PATH = os.path.join(DATA_DIR, "jobs.db")

HOST = os.environ.get("AUDIO2TAB_HOST", "127.0.0.1")
PORT = int(os.environ.get("AUDIO2TAB_PORT", "8765"))


def ensure_dirs() -> None:
    os.makedirs(JOBS_DIR, exist_ok=True)


def job_dir(job_id: str) -> str:
    return os.path.join(JOBS_DIR, job_id)
