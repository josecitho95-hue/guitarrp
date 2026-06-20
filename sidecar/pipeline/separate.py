"""Etapa 2: Separacion de fuentes (Demucs) — opcional en Fase 0.

Aisla la guitarra de la mezcla. htdemucs no tiene un stem dedicado de guitarra;
se usa el stem 'other' (donde suele caer la guitarra). Por defecto esta
DESACTIVADO en el spike: requiere descargar pesos (~varios cientos de MB) y es la
etapa mas pesada. Si Demucs no esta disponible, devuelve el audio sin cambios.
"""
from __future__ import annotations

import os
import subprocess
import sys


def separate_guitar(in_path: str, out_dir: str, device: str = "cpu",
                    stem: str = "other") -> str:
    """Ejecuta Demucs y devuelve la ruta del stem aislado.

    Si Demucs no esta instalado, registra un aviso y devuelve `in_path` para que
    el pipeline continue con la mezcla completa.
    """
    try:
        import demucs  # noqa: F401
    except ImportError:
        print("[separate] Demucs no instalado; se usa la mezcla completa.", file=sys.stderr)
        return in_path

    os.makedirs(out_dir, exist_ok=True)
    cmd = [sys.executable, "-m", "demucs", "-n", "htdemucs",
           "-d", device, "-o", out_dir, in_path]
    print(f"[separate] Ejecutando Demucs ({device})...", file=sys.stderr)
    subprocess.run(cmd, check=True)

    base = os.path.splitext(os.path.basename(in_path))[0]
    stem_path = os.path.join(out_dir, "htdemucs", base, f"{stem}.wav")
    if not os.path.exists(stem_path):
        print(f"[separate] No se encontro {stem_path}; se usa la mezcla.", file=sys.stderr)
        return in_path
    return stem_path
