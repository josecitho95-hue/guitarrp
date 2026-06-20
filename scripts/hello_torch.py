"""Mínimo para validar el empaquetado (PyInstaller) de torch+CUDA.

Si el .exe empaquetado imprime 'CUDA: True', PyInstaller es viable para el sidecar.
Si falla (hooks de torch, DLLs de CUDA), se usa el fallback de venv embebido (uv).
"""
import torch

print("torch:", torch.__version__)
print("CUDA:", torch.cuda.is_available())
if torch.cuda.is_available():
    print("GPU:", torch.cuda.get_device_name(0))
