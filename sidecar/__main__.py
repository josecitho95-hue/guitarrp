"""Lanza el sidecar:  python -m sidecar"""
from __future__ import annotations

import uvicorn

from . import config

if __name__ == "__main__":
    uvicorn.run("sidecar.server:app", host=config.HOST, port=config.PORT,
                log_level="info")
