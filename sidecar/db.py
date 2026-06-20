"""Almacén de jobs en SQLite (estado del sidecar)."""
from __future__ import annotations

import json
import sqlite3
import threading
import time

from . import config

_conn: sqlite3.Connection | None = None
_lock = threading.Lock()


def init_db() -> None:
    global _conn
    config.ensure_dirs()
    _conn = sqlite3.connect(config.DB_PATH, check_same_thread=False)
    _conn.row_factory = sqlite3.Row
    _conn.execute(
        """
        CREATE TABLE IF NOT EXISTS jobs (
            id          TEXT PRIMARY KEY,
            status      TEXT NOT NULL,
            stage       TEXT,
            progress    REAL DEFAULT 0,
            input_path  TEXT,
            output_path TEXT,
            params      TEXT,
            error       TEXT,
            n_notes     INTEGER,
            bpm         REAL,
            created_at  REAL,
            updated_at  REAL
        )
        """
    )
    _conn.commit()


def _now() -> float:
    return time.time()


def create_job(job_id: str, input_path: str, params: dict) -> None:
    with _lock:
        _conn.execute(
            "INSERT INTO jobs (id, status, stage, progress, input_path, params, created_at, updated_at)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (job_id, "queued", "queued", 0.0, input_path, json.dumps(params), _now(), _now()),
        )
        _conn.commit()


def update_job(job_id: str, **fields) -> None:
    if not fields:
        return
    fields["updated_at"] = _now()
    cols = ", ".join(f"{k} = ?" for k in fields)
    with _lock:
        _conn.execute(f"UPDATE jobs SET {cols} WHERE id = ?", (*fields.values(), job_id))
        _conn.commit()


def get_job(job_id: str) -> dict | None:
    with _lock:
        row = _conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    if not row:
        return None
    d = dict(row)
    if d.get("params"):
        d["params"] = json.loads(d["params"])
    return d


def list_jobs(limit: int = 100) -> list[dict]:
    with _lock:
        rows = _conn.execute(
            "SELECT id, status, stage, progress, output_path, n_notes, created_at"
            " FROM jobs ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def clean_job_artifacts() -> None:
    """Elimina los archivos WAV pesados de los trabajos completados o fallidos."""
    import os
    import shutil
    from . import config

    with _lock:
        rows = _conn.execute(
            "SELECT id, status FROM jobs WHERE status IN ('done', 'error')"
        ).fetchall()

    for r in rows:
        job_id = r["id"]
        jd = config.job_dir(job_id)
        if not os.path.exists(jd):
            continue

        for item in os.listdir(jd):
            item_path = os.path.join(jd, item)
            # Conservar tab_notes.json, y el archivo GP final.
            # Borrar input.wav, region_temp.wav y el directorio htdemucs.
            if item.lower() in ("input.wav", "region_temp.wav"):
                try:
                    os.remove(item_path)
                except Exception:
                    pass
            elif item.lower() == "htdemucs" and os.path.isdir(item_path):
                try:
                    shutil.rmtree(item_path)
                except Exception:
                    pass
