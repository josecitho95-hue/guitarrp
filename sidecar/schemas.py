"""Modelos Pydantic del API del sidecar."""
from __future__ import annotations

from pydantic import BaseModel


class JobStatus(BaseModel):
    id: str
    status: str                      # queued | running | done | error
    stage: str | None = None         # etapa del pipeline
    progress: float = 0.0
    output_path: str | None = None
    n_notes: int | None = None
    bpm: float | None = None
    error: str | None = None


class JobCreated(BaseModel):
    id: str
    status: str = "queued"
