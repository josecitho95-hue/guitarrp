"""Valida que el generate con KV-cache produce EXACTAMENTE los mismos tokens que
el generate original (full-sequence). Usa max_length corto para que el original
(O(L^2)) sea rapido tambien. Tambien mide el speedup en un input mas largo.
"""
import sys
import time

import numpy as np

# 1) Capturar el generate ORIGINAL antes de aplicar el patch.
from mt3_infer.models.mr_mt3 import t5 as _t5
orig_generate = _t5.T5ForConditionalGeneration.generate

# 2) Aplicar shims (incluye el patch de KV-cache).
from sidecar.pipeline import _mt3_compat
_mt3_compat.apply()
cached_generate = _t5.T5ForConditionalGeneration.generate
assert cached_generate is not orig_generate, "el patch no se aplico"

import torch
import librosa

from mt3_infer import load_model

device = "cuda" if torch.cuda.is_available() else "cpu"
print(f"device: {device}")
mdl = load_model("mr_mt3", device=device)
model = mdl.model

# Clip corto del audio (los primeros ~10s del fragmento ya separado/limpio sirven).
audio_path = sys.argv[1] if len(sys.argv) > 1 else "storage/mop_excerpt.wav"
y, _ = librosa.load(audio_path, sr=16000, mono=True)
y10 = y[:16000 * 10]
features = mdl.preprocess(y10, 16000)
inputs = features["inputs"].to(mdl.device_str)
print(f"inputs (segmentos x tiempo x freq): {tuple(inputs.shape)}")

# --- Correctitud: mismos tokens con max_length corto ---
ML = 64
with torch.no_grad():
    out_orig = orig_generate(model, inputs, max_length=ML)
    out_cached = cached_generate(model, inputs, max_length=ML)

L = min(out_orig.shape[1], out_cached.shape[1])
a = out_orig[:, :L]
b = out_cached[:, :L]
identical = torch.equal(a, b)
n_diff = int((a != b).sum().item())
print(f"\n[correctitud] max_length={ML}: tokens identicos = {identical} "
      f"(difs={n_diff}/{a.numel()})")
if not identical:
    # mostrar primera discrepancia
    diff_pos = (a != b).nonzero()
    print("  primeras discrepancias (seg, pos):", diff_pos[:5].tolist())

# --- Velocidad: full max_length sobre el mismo input ---
torch.cuda.synchronize() if device == "cuda" else None
t = time.time()
with torch.no_grad():
    _ = orig_generate(model, inputs, max_length=1024)
torch.cuda.synchronize() if device == "cuda" else None
t_orig = time.time() - t

t = time.time()
with torch.no_grad():
    _ = cached_generate(model, inputs, max_length=1024)
torch.cuda.synchronize() if device == "cuda" else None
t_cached = time.time() - t

print(f"\n[velocidad] sobre 10s ({inputs.shape[0]} segmentos), max_length=1024:")
print(f"  original (O(L^2)): {t_orig:.1f}s")
print(f"  KV-cache  (O(L)) : {t_cached:.1f}s")
if t_cached > 0:
    print(f"  speedup: {t_orig / t_cached:.1f}x")
