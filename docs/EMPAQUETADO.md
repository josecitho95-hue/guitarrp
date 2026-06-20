# Decisión de empaquetado — validación temprana (Fase 2)

> Objetivo de la prueba (plan §7, Fase 2): validar **cuanto antes** si PyInstaller puede
> empaquetar `torch + CUDA`, ya que es el riesgo técnico principal del enfoque de app de
> escritorio autocontenida.

## Resultado de la prueba

Se empaquetó `scripts/hello_torch.py` (solo `import torch` + chequeo de CUDA) con
`pyinstaller --onedir`. El `.exe` resultante **arrancó y detectó la GPU correctamente**:

```
torch: 2.6.0+cu124
CUDA: True
GPU: NVIDIA GeForce RTX 4070 Laptop GPU
```

**Conclusión clave: PyInstaller es técnicamente viable** — torch+CUDA empaquetado funciona y ve
la 4070. La principal preocupación del plan queda des-arriesgada.

### Problema: tamaño y bloat

| Componente | Tamaño |
|---|---|
| **Total del paquete** | **5.0 GB** |
| torch (CUDA) | 3.6 GB |
| tensorflow | 871 MB ⚠️ innecesario |
| llvmlite | 102 MB |
| scipy | 53 MB |
| transformers | 42 MB |

- torch+CUDA (~3.6 GB) es inevitable con cualquier método (es el motor).
- **TensorFlow (871 MB) NO se usa** (la transcripción corre por el backend ONNX de Basic Pitch);
  entró arrastrado por hooks porque `basic-pitch[onnx]` lo trae como dependencia del entorno.

## Recomendación para Fase 3

Hay **dos rutas viables** (ambas validadas en la práctica):

1. **Venv embebido con `uv`/`micromamba` (preferida).** Empaquetar el `.venv` ya funcional junto
   al binario de Tauri y que Rust llame a `python.exe`. Ventajas: sin guerra de hooks, sin
   arrastres sorpresa, reproducible, y el sidecar **ya corre así hoy**. Tamaño comparable.
2. **PyInstaller (fallback validado).** Funciona, pero requiere podar explícitamente lo que no
   se usa para bajar de 5 GB:
   ```
   pyinstaller --onedir \
     --exclude-module tensorflow --exclude-module tensorflow_estimator \
     --exclude-module keras --exclude-module tensorboard \
     sidecar_entry.py
   ```
   Aun podado, ronda ~3.5–4 GB por torch+CUDA.

**Decisión:** ir con el **venv embebido (`uv`)** en Fase 3; PyInstaller queda como alternativa
probada. En cualquier caso, conviene **separar las dependencias de transcripción** para no
arrastrar TensorFlow (evaluar reemplazar `basic-pitch[onnx]` por solo el modelo ONNX, ya que
mr_mt3 es el transcriptor por defecto).

> Artefactos de la prueba (`dist_pkg/`, `build_pkg/`, ~5 GB) eliminados tras validar; el log
> completo quedó en `logs/pyinstaller.log` (gitignored).
