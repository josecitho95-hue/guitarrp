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
