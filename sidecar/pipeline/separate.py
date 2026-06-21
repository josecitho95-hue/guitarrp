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


# Mapa instrumento lógico -> stem de htdemucs. La guitarra cae en 'other'.
STEM_MAP = {"guitar": "other", "bass": "bass", "drums": "drums", "vocals": "vocals"}


def separate_all(in_path: str, out_dir: str, device: str = "cpu") -> dict[str, str]:
    """Ejecuta Demucs UNA vez y devuelve {instrumento: ruta_stem} para todos los
    stems disponibles. Si Demucs no está, devuelve {'guitar': in_path} (mezcla).
    """
    try:
        import demucs  # noqa: F401
    except ImportError:
        print("[separate] Demucs no instalado; se usa la mezcla completa.", file=sys.stderr)
        return {"guitar": in_path}

    os.makedirs(out_dir, exist_ok=True)
    cmd = [sys.executable, "-m", "demucs", "-n", "htdemucs",
           "-d", device, "-o", out_dir, in_path]
    print(f"[separate] Ejecutando Demucs ({device})...", file=sys.stderr)
    subprocess.run(cmd, check=True)

    base = os.path.splitext(os.path.basename(in_path))[0]
    stem_dir = os.path.join(out_dir, "htdemucs", base)
    out: dict[str, str] = {}
    for inst, stem in STEM_MAP.items():
        p = os.path.join(stem_dir, f"{stem}.wav")
        if os.path.exists(p):
            out[inst] = p
    if not out:
        print(f"[separate] No se encontraron stems en {stem_dir}; se usa la mezcla.",
              file=sys.stderr)
        return {"guitar": in_path}
    return out
