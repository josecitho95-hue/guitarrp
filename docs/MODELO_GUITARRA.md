# Integración de un modelo de transcripción específico de guitarra

> **Estado:** ⛔ **BLOQUEADO por falta de pesos pre-entrenados** (verificado 2026-06-20).
> **Prioridad:** Should Have (ver `BACKLOG.md`, ítem **MG-01**).
> **Origen:** sesión de calidad del 2026-06-20. Tras descartar con datos varios
> levers (tempo dinámico, limpieza de notas) y validar uno real (transcripción
> estéreo, DTW 76%→84%), este era **el único lever de fidelidad que quedaba**.

---

## ⛔ ACTUALIZACIÓN (2026-06-20): bloqueo por disponibilidad de pesos

Se ejecutó el paso de viabilidad (§7, riesgo #1) y **ningún modelo SOTA específico
de guitarra publica pesos de inferencia descargables**:

| Modelo | Pesos públicos | Notas |
|--------|----------------|-------|
| High-Resolution Guitar Transcription (arXiv 2402.15258) | ❌ NO | Solo "companion site" (xavriley.github.io); no hay repo de inferencia ni checkpoint. |
| FretNet (github.com/cwitkowitz/guitar-transcription-continuous) | ❌ NO | Solo código de entrenamiento (6-fold CV sobre GuitarSet). Hay que entrenarlo. |
| Robustez guitarra eléctrica (arXiv 2405.14679) | ❌ NO | Código reproducible (robust-guitar-tabs.github.io) sin pesos. TabCNN. **Avisa que falla en contenido armónico multi-cuerda simultáneo (= metal).** |
| Omnizart (pip, `download-checkpoints`) | ✅ SÍ | Pero **genérico** (no guitarra), TensorFlow viejo (conflictos protobuf como basic_pitch). Improbable que supere a basic_pitch. |

**Conclusión:** integrar un modelo de guitarra SOTA **requiere entrenarlo**, lo que
contradice la decisión núcleo del proyecto ("no entrenar"). Además GuitarSet es
acústico/limpio → desajuste de dominio con metal eléctrico distorsionado. Para
**mezcla densa**, el valor esperado es bajo y el baseline estéreo (DTW ~84%)
probablemente esté cerca del techo práctico. Para **material limpio/acústico** sí
valdría más.

**Decisión (2026-06-20):** MG-01 queda **parqueado**. Reactivar solo si: (a) aparece
un modelo de guitarra con pesos descargables, o (b) se acepta entrenar (revisar
política) — entrenar FretNet/TabCNN en GuitarSet es factible en la 4070 (horas),
pero con retorno incierto en metal denso. La sección de implementación de abajo
sigue válida para cuando se desbloquee.

---

---

## 1. Objetivo y contexto

La etapa 3 (audio→MIDI) hoy usa dos transcriptores, ninguno especializado en
guitarra:

| Transcriptor | Tipo | F1 GuitarSet (ref.) | Rol actual |
|--------------|------|---------------------|------------|
| `basic_pitch` (Spotify) | genérico, ligero (ONNX) | ~0.73 | default rápido |
| `mr_mt3` (familia MT3) | multi-instrumento | 0.85 (limpio) / sobre-transcribe en mezcla densa | SOTA + única vía para batería |

El contenido de notas que producimos ya es bueno (chroma global ~99%), pero la
fidelidad nota-a-nota tiene techo. Un **modelo entrenado específicamente en
guitarra** es la palanca para subir la precisión de cada fuente — especialmente
ahora que la separación estéreo nos da stems de guitarra más limpios (uno por
canal paneado).

**Meta medible:** superar a `basic_pitch` en F1 sobre GuitarSet **y** subir el
DTW/contenido vs el GP oficial en el caso de Master of Puppets (baseline actual:
DTW ~84% con 2 guitarras estéreo + basic_pitch).

---

## 2. Modelos candidatos (OSS)

Elegir por F1 medido, no por intuición (usar el harness de §5). Verificar
disponibilidad de pesos/licencia antes de invertir.

### A. High-Resolution Guitar Transcription *(recomendado de partida)*
- Basado en Kong et al. (high-resolution piano transcription) adaptado a guitarra
  (Riley/Dixon). Predice onset/offset/pitch con regresión de alta resolución
  temporal, además de **contorno de pitch continuo** (útil para Tier 1: bends,
  slides, vibrato — hoy lo derivamos de pitch bends).
- F1 de referencia ~0.88 en GuitarSet (estado del arte sobre guitarra limpia).
- **A verificar:** repo y disponibilidad de pesos de inferencia (xavriley /
  arXiv 2402.15258). Dataset **GAPS** en Zenodo, reutilizable para benchmark.
- Riesgo: si solo hay código de entrenamiento sin pesos, el coste sube mucho
  (no entrenamos — ver decisión de proyecto). Confirmar pesos descargables.

### B. FretNet (Cwitkowitz)
- Estimación conjunta de **multipitch continuo + tablatura** (cuerda/traste) para
  guitarra, del ecosistema `amt-tools` (MIT). Encaja con nuestra matriz de
  inhibición (mismo autor que `guitar-transcription-with-inhibition`).
- Ventaja: si predice cuerda/traste directamente, puede **competir o sustituir**
  a `to_tab` (Path B parcial) — evaluar como alternativa, no solo como etapa 3.
- **A verificar:** pesos públicos y compatibilidad con PyTorch/CUDA del stack.

### C. Otros / fallback
- **GAPS / Basic Pitch**: baseline ya integrado (comparador).
- **YourMT3+**: bloqueado por incompatibilidad con transformers 5.x (ver
  `_mt3_compat`). Tras el fix de KV-cache entendemos mejor el API `Cache` de
  transformers 5.12; *podría* ser retomable, pero sigue siendo de alto riesgo.
  No es el camino recomendado para este ítem.

---

## 3. Contrato de integración (lo único que el modelo debe cumplir)

El pipeline está desacoplado detrás de **una sola firma**. Un transcriptor nuevo
solo tiene que devolver `list[Note]`:

```python
# sidecar/pipeline/types.py
@dataclass
class Note:
    pitch: int            # MIDI
    start: float          # segundos
    end: float            # segundos
    velocity: int = 64
    pitch_bends: list[tuple[float, int]] = ...   # (tiempo_s, valor_pitch_bend)
    # confidence: float | None = None   # <- AÑADIR si el modelo la expone (ver MG-01 / CH-03)
```

```python
# sidecar/pipeline/transcribe.py  — nueva función, misma forma que las existentes
def transcribe_highres(audio_path: str, device: str | None = None,
                       chunk_s: float = 30.0, overlap_s: float = 2.0,
                       progress=None) -> list[Note]:
    """Transcribe con el modelo específico de guitarra. Devuelve list[Note]."""
    ...
```

Todo lo de aguas abajo (matriz de inhibición, `assign_tab`, técnicas, export GP,
multipista, estéreo) ya consume `list[Note]` y **no requiere cambios**.

---

## 4. Pasos de implementación

1. **Dependencias y pesos**
   - Añadir el paquete/repo del modelo al entorno (`requirements-fase1.txt` o
     vendorizar como hicimos con `mt3_infer`). Si necesita shims de compatibilidad
     con transformers/torch 5.x, seguir el patrón de `sidecar/pipeline/_mt3_compat.py`
     (monkeypatch desde nuestro repo, **no** editar el `.venv`).
   - Descargar pesos a `.<modelo>_checkpoints/` (gitignored), igual que
     `.mt3_checkpoints/`. Auto-descarga en el primer uso (no inflar el instalador).

2. **`transcribe.py`**: implementar `transcribe_highres()` con el contrato de §3.
   - Reutilizar el patrón de chunking con solape + progreso/ETA ya presente en
     `transcribe_mt3` (mismo `progress(frac, msg)`), crítico para canciones largas.
   - Respetar `device` (cpu/cuda) y liberar VRAM entre etapas (`gpu.free_vram`).
   - Si el modelo emite contorno de pitch continuo, poblar `pitch_bends` para que
     `techniques.py` (Tier 1) detecte bends/slides/vibrato con más señal.
   - Si emite confianza por nota, poblar `Note.confidence` (habilita CH-03: poda
     por confianza en `inhibition`).

3. **Registro / selección**
   - `bench/run_benchmark.py`: añadir a `TRANSCRIBERS` (`"highres": _highres`).
   - `runner.py` (`PipelineParams.transcriber`) y `cli/transcribe.py`
     (`--transcriber {mr_mt3, basic_pitch, highres}`): añadir la opción.
   - Si FretNet predice cuerda/traste directo, evaluar un modo que **salte
     `to_tab`** (devolver `TabNote` ya digitado) — decisión aparte tras el benchmark.

4. **Default por material** (tras medir): mantener `basic_pitch` como rápido,
   `mr_mt3` para batería/percusión, y `highres` como default de calidad para
   guitarra/bajo. La selección puede ser por instrumento dentro del flujo
   multipista (`_stem_to_tab`).

---

## 5. Plan de validación (obligatorio antes de mergear)

1. **F1 en GuitarSet** (limpio, objetivo): el harness ya existe.
   ```bash
   .venv/Scripts/python.exe bench/run_benchmark.py --dataset guitarset --n 5 \
       --transcribers basic_pitch highres mr_mt3
   ```
   Criterio: `highres` debe ganar a `basic_pitch` en F1 medio (`bench/metrics.py`,
   onset+pitch, tolerancia 50 ms).

2. **Cercanía vs GP oficial** (mezcla real, Master of Puppets): usar los scripts
   de comparación de esta sesión.
   ```bash
   # transcribir con --transcriber highres --multi-instrument --stereo-guitars
   .venv/Scripts/python.exe scripts/compare_gp.py \
       "metallica-master_of_puppets - OFICIAL.gp3" salida.gp5 \
       --ref-tracks 0,1 --est-tracks 0,1 --windows 300
   ```
   Baseline a superar: **DTW ~84% / contenido ~99%** (2 guitarras estéreo +
   basic_pitch). `scripts/compare_excerpt.py` para fragmentos.

3. **Regresión**: `tests/test_pipeline.py` (núcleo) + `test_cli` + `test_sidecar`
   + `test_reprocess` siguen pasando.

---

## 6. Hardware y rendimiento (RTX 4070 8 GB)

- La VRAM (8 GB) es el recurso escaso. Cargar/descargar el modelo entre etapas y
  llamar `gc.collect()` + `torch.cuda.empty_cache()` (ver `gpu.py`).
- **Chunking + fp16** obligatorio en audio largo, con solape para no cortar notas
  (patrón ya implementado en `transcribe_mt3`).
- Con estéreo se separa y transcribe **por canal**: el coste de la etapa 3 se
  duplica (2 guitarras). Medir el tiempo total; con el fix de KV-cache mr_mt3 la
  canción completa va en ~1.7 min, dejar holgura.

---

## 7. Riesgos y mitigaciones

| Riesgo | Mitigación |
|--------|-----------|
| El modelo solo publica código de entrenamiento, sin pesos | Verificar pesos ANTES de empezar. Sin pesos, el ítem se reevalúa (no entrenamos). |
| Incompatibilidad torch/transformers 5.x | Patrón de shims `_mt3_compat` (monkeypatch desde el repo, no tocar `.venv`). |
| Degrada en mezcla densa/distorsionada pese a buen F1 en GuitarSet | Es esperado (GuitarSet es limpio/solista). Medir SIEMPRE también vs el GP oficial (§5.2), no solo F1. |
| No mejora sobre basic_pitch en el caso real | Decisión basada en datos: si no supera el baseline DTW ~84%, no se adopta como default. |
| Licencia GPL | Uso estrictamente personal sin distribución → sin restricción práctica (ver plan). Reevaluar solo si se distribuye. |

---

## 8. Criterios de aceptación ("hecho")

- [ ] `transcribe_highres()` implementada con el contrato de §3 (devuelve `list[Note]`).
- [ ] Seleccionable por `--transcriber highres` (CLI), `PipelineParams.transcriber`
      y registrado en `bench/run_benchmark.py`.
- [ ] Chunking con progreso/ETA y respeto de `device` (cpu/cuda) + liberación de VRAM.
- [ ] **F1 GuitarSet > basic_pitch** (medido con el harness).
- [ ] **DTW vs oficial ≥ baseline 84%** (medido con `compare_gp.py`), o justificación
      con datos si se descarta.
- [ ] Tests del núcleo + CLI + sidecar pasan sin regresión.
- [ ] Pesos auto-descargables a `.<modelo>_checkpoints/` (gitignored); doc de
      instalación actualizada (`docs/EMPAQUETADO.md` si afecta al bundle).

---

> **Nota para quien retome:** el desacople por `list[Note]` hace que este cambio
> sea **aditivo y aislado a la etapa 3**. Nada de aguas abajo (inhibición, tab,
> técnicas, GP, estéreo, multipista) necesita tocarse. El mayor trabajo real es
> conseguir/portar el modelo y sus pesos, y validar con datos que supera el
> baseline — no la fontanería del pipeline.
