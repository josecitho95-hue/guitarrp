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


def _run_demucs(in_path: str, out_dir: str, device: str) -> str:
    """Corre Demucs sobre in_path y devuelve la carpeta de stems resultante."""
    os.makedirs(out_dir, exist_ok=True)
    cmd = [sys.executable, "-m", "demucs", "-n", "htdemucs",
           "-d", device, "-o", out_dir, in_path]
    print(f"[separate] Ejecutando Demucs ({device}) sobre {os.path.basename(in_path)}...",
          file=sys.stderr)
    subprocess.run(cmd, check=True)
    base = os.path.splitext(os.path.basename(in_path))[0]
    return os.path.join(out_dir, "htdemucs", base)


def separate_all(in_path: str, out_dir: str, device: str = "cpu") -> dict[str, str]:
    """Ejecuta Demucs UNA vez y devuelve {instrumento: ruta_stem} para todos los
    stems disponibles. Si Demucs no está, devuelve {'guitar': in_path} (mezcla).
    """
    try:
        import demucs  # noqa: F401
    except ImportError:
        print("[separate] Demucs no instalado; se usa la mezcla completa.", file=sys.stderr)
        return {"guitar": in_path}

    stem_dir = _run_demucs(in_path, out_dir, device)
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


def separate_stereo(in_path: str, out_dir: str, device: str = "cpu") -> dict[str, str]:
    """Separa por canal para recuperar las DOS guitarras paneadas (L/R).

    En metal las rítmicas suelen ir hard-paneadas a izquierda/derecha. Demucs
    colapsa ese paneo en su stem 'other' (queda mono-centrado), así que aquí se
    separa cada canal por separado: el 'other' de L ≈ guitarra izquierda y el de
    R ≈ guitarra derecha. Bajo y batería (centrados) se sacan del mix completo.
    Devuelve {guitar_l, guitar_r, bass, drums}. Si el audio es mono o casi
    (L≈R), cae a separate_all (una sola guitarra).
    """
    try:
        import demucs  # noqa: F401
        import librosa
        import numpy as np
        import soundfile as sf
    except ImportError:
        return separate_all(in_path, out_dir, device)

    y, sr = librosa.load(in_path, sr=44100, mono=False)
    if y.ndim != 2 or y.shape[0] != 2:
        return separate_all(in_path, out_dir, device)
    L, R = y[0], y[1]
    if float(np.corrcoef(L, R)[0, 1]) > 0.95:
        print("[separate] Canales L/R casi idénticos; se usa separación mono.",
              file=sys.stderr)
        return separate_all(in_path, out_dir, device)

    os.makedirs(out_dir, exist_ok=True)
    lpath = os.path.join(out_dir, "chan_L.wav")
    rpath = os.path.join(out_dir, "chan_R.wav")
    sf.write(lpath, L, sr)
    sf.write(rpath, R, sr)

    out: dict[str, str] = {}
    dir_l = _run_demucs(lpath, out_dir, device)
    dir_r = _run_demucs(rpath, out_dir, device)
    out["guitar_l"] = os.path.join(dir_l, "other.wav")
    out["guitar_r"] = os.path.join(dir_r, "other.wav")
    # Bajo y batería del mix completo (centrados; el paneo no importa).
    dir_full = _run_demucs(in_path, out_dir, device)
    for inst in ("bass", "drums"):
        p = os.path.join(dir_full, f"{inst}.wav")
        if os.path.exists(p):
            out[inst] = p
    return out
