"""Sidecar FastAPI local de Audio2Tab (Fase 2).

API mínima (F1-F4): crear job, consultar estado/progreso, descargar resultado.
Pensado para correr en 127.0.0.1 lanzado por el shell de escritorio (Fase 3).
"""
from __future__ import annotations

import os
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from . import config, db
from . import queue as jobqueue
from .pipeline.runner import PipelineParams
from .schemas import JobCreated, JobStatus


@asynccontextmanager
async def lifespan(app: FastAPI):
    config.ensure_dirs()
    db.init_db()
    yield
    jobqueue.shutdown()


app = FastAPI(title="Audio2Tab Sidecar", version="0.2.0", lifespan=lifespan)


@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok"}


@app.post("/jobs", response_model=JobCreated)
async def create_job(
    file: UploadFile = File(...),
    transcriber: str = Form("mr_mt3"),
    separate: bool = Form(False),
    device: str = Form("cpu"),
    bpm: float = Form(120.0),
    output_format: str = Form("gp5"),
    calibrate_tuning: bool = Form(False),
    open_string_pref: str = Form("media"),
    from_midi: bool = Form(False),
) -> JobCreated:
    job_id = uuid.uuid4().hex[:12]
    jd = config.job_dir(job_id)
    os.makedirs(jd, exist_ok=True)

    in_name = os.path.basename(file.filename or "input")
    in_path = os.path.join(jd, in_name)
    with open(in_path, "wb") as f:
        f.write(await file.read())

    params = PipelineParams(
        transcriber=transcriber, separate=separate, device=device, bpm=bpm,
        output_format=output_format, calibrate_tuning=calibrate_tuning,
        open_string_pref=open_string_pref, from_midi=from_midi,
    )
    db.create_job(job_id, in_path, params.__dict__)
    out_path = os.path.join(jd, f"output.{output_format.lstrip('.')}")
    jobqueue.submit(job_id, in_path, out_path, params, jd)
    return JobCreated(id=job_id)


@app.get("/jobs", response_model=list)
def list_jobs() -> list:
    return db.list_jobs()


@app.get("/jobs/{job_id}", response_model=JobStatus)
def job_status(job_id: str) -> JobStatus:
    j = db.get_job(job_id)
    if not j:
        raise HTTPException(status_code=404, detail="job no encontrado")
    return JobStatus(
        id=j["id"], status=j["status"], stage=j.get("stage"),
        progress=j.get("progress") or 0.0, output_path=j.get("output_path"),
        n_notes=j.get("n_notes"), error=j.get("error"),
    )


@app.get("/jobs/{job_id}/result")
def job_result(job_id: str):
    j = db.get_job(job_id)
    if not j:
        raise HTTPException(status_code=404, detail="job no encontrado")
    if j["status"] != "done" or not j.get("output_path"):
        raise HTTPException(status_code=409, detail=f"job no completado (estado: {j['status']})")
    out = j["output_path"]
    if not os.path.exists(out):
        raise HTTPException(status_code=410, detail="artefacto no disponible")
    return FileResponse(out, filename=os.path.basename(out),
                        media_type="application/octet-stream")
