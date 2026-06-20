"""Gestión de dispositivo y VRAM para el pipeline (Fase 1).

Con 8 GB de VRAM, la carga secuencial de modelos pesados (Demucs, YourMT3+) es
crítica: PyTorch retiene memoria reservada en la GPU aunque se destruyan las
variables. `free_vram()` fuerza la liberación entre modelos.
"""
from __future__ import annotations

import contextlib
import gc


def get_device(prefer: str = "cuda") -> str:
    """Devuelve 'cuda' si hay GPU disponible, si no 'cpu'."""
    try:
        import torch
    except ImportError:
        return "cpu"
    if prefer == "cuda" and torch.cuda.is_available():
        return "cuda"
    return "cpu"


def free_vram(*objs) -> None:
    """Libera referencias a modelos y vacía la caché de la GPU.

    Llamar tras terminar con un modelo y ANTES de cargar el siguiente:
        model = load_demucs(); ... ; free_vram(model)
    """
    for _ in objs:
        pass  # las referencias locales del llamador se sueltan al pasar aquí
    del objs
    gc.collect()
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.cuda.ipc_collect()
    except ImportError:
        pass


@contextlib.contextmanager
def model_scope(name: str = "modelo"):
    """Contexto que garantiza liberar la VRAM al salir (éxito o error)."""
    try:
        yield
    finally:
        free_vram()


def vram_status() -> str:
    """Resumen del uso de VRAM (para logs/diagnóstico)."""
    try:
        import torch
        if not torch.cuda.is_available():
            return "VRAM: sin CUDA"
        alloc = torch.cuda.memory_allocated() / 1024**3
        reserved = torch.cuda.memory_reserved() / 1024**3
        total = torch.cuda.get_device_properties(0).total_memory / 1024**3
        return f"VRAM: {alloc:.2f}G usada / {reserved:.2f}G reservada / {total:.1f}G total"
    except ImportError:
        return "VRAM: torch no instalado"
