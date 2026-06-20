"""Cola de trabajos en proceso.

Un único worker (ThreadPoolExecutor max_workers=1) serializa los jobs: con 8 GB
de VRAM no se pueden correr dos pipelines pesados a la vez. Actualiza el estado
del job en SQLite a medida que avanza.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from . import db
from .pipeline.runner import PipelineParams, run_pipeline

_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="a2t-worker")


def submit(job_id: str, input_path: str, out_path: str,
           params: PipelineParams, work_dir: str) -> None:
    _executor.submit(_run, job_id, input_path, out_path, params, work_dir)


def _run(job_id: str, input_path: str, out_path: str,
         params: PipelineParams, work_dir: str) -> None:
    def on_progress(stage: str, pct: float) -> None:
        status = "done" if stage == "done" else "running"
        db.update_job(job_id, status=status, stage=stage, progress=pct)

    try:
        db.update_job(job_id, status="running", stage="preprocess", progress=0.01)
        result = run_pipeline(input_path, out_path, params, work_dir, on_progress)
        db.update_job(job_id, status="done", stage="done", progress=1.0,
                      output_path=result["output"], n_notes=result["n_notes"])
    except Exception as exc:  # noqa: BLE001
        db.update_job(job_id, status="error", stage="error", error=str(exc))


def shutdown() -> None:
    _executor.shutdown(wait=False, cancel_futures=True)
