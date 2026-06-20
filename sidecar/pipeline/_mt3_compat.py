"""Compatibilidad para correr modelos MT3 (mt3-infer) sobre el stack 2026.

El código T5 vendorizado en mt3-infer (escrito ~2024) usa métodos de
`transformers.ModuleUtilsMixin` que transformers 5.x removió o cambió de firma.
Aquí se restauran con sus implementaciones clásicas (idempotente). Llamar a
`apply()` antes de `mt3_infer.load_model()`.

Esto evita depender de parches dentro del venv (no reproducibles).
"""
from __future__ import annotations

import sys
import types

_applied = False


def apply() -> None:
    global _applied
    if _applied:
        return
    import torch

    # 1) stdout/stderr en UTF-8 (mt3-infer imprime caracteres unicode; Windows usa cp1252)
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except Exception:
            pass

    # 2) shim de transformers.utils.model_parallel_utils (removido en 5.x)
    if "transformers.utils.model_parallel_utils" not in sys.modules:
        mod = types.ModuleType("transformers.utils.model_parallel_utils")

        def get_device_map(n_layers, devices):
            from math import ceil
            layers = list(range(n_layers))
            n_blocks = int(ceil(n_layers / len(devices)))
            chunks = [layers[i:i + n_blocks] for i in range(0, n_layers, n_blocks)]
            return dict(zip(devices, chunks))

        def assert_device_map(device_map, num_blocks):
            return  # validación no crítica en inferencia

        mod.get_device_map = get_device_map
        mod.assert_device_map = assert_device_map
        sys.modules["transformers.utils.model_parallel_utils"] = mod

    # 3) métodos clásicos de ModuleUtilsMixin
    from transformers.modeling_utils import ModuleUtilsMixin as MUM

    _orig_ext = MUM.get_extended_attention_mask

    def get_extended_attention_mask(self, attention_mask, input_shape, device=None, dtype=None):
        # transformers 5.x quitó el parámetro posicional `device`; tolerarlo.
        if isinstance(device, torch.dtype):
            dtype, device = device, None
        if isinstance(device, torch.device):
            device = None
        if dtype is None:
            dtype = self.dtype
        return _orig_ext(self, attention_mask, input_shape, dtype=dtype)

    MUM.get_extended_attention_mask = get_extended_attention_mask

    def _convert_head_mask_to_5d(self, head_mask, num_hidden_layers):
        if head_mask.dim() == 1:
            head_mask = head_mask.unsqueeze(0).unsqueeze(0).unsqueeze(-1).unsqueeze(-1)
            head_mask = head_mask.expand(num_hidden_layers, -1, -1, -1, -1)
        elif head_mask.dim() == 2:
            head_mask = head_mask.unsqueeze(1).unsqueeze(-1).unsqueeze(-1)
        return head_mask.to(dtype=self.dtype)

    def get_head_mask(self, head_mask, num_hidden_layers, is_attention_chunked=False):
        if head_mask is not None:
            head_mask = self._convert_head_mask_to_5d(head_mask, num_hidden_layers)
            if is_attention_chunked is True:
                head_mask = head_mask.unsqueeze(-1)
        else:
            head_mask = [None] * num_hidden_layers
        return head_mask

    def invert_attention_mask(self, encoder_attention_mask):
        if encoder_attention_mask.dim() == 3:
            ext = encoder_attention_mask[:, None, :, :]
        else:
            ext = encoder_attention_mask[:, None, None, :]
        ext = ext.to(dtype=self.dtype)
        return (1.0 - ext) * torch.finfo(self.dtype).min

    for name, fn in [
        ("_convert_head_mask_to_5d", _convert_head_mask_to_5d),
        ("get_head_mask", get_head_mask),
        ("invert_attention_mask", invert_attention_mask),
    ]:
        if not hasattr(MUM, name):
            setattr(MUM, name, fn)

    _applied = True
