# Audio2Tab

Sistema de transcripción de audio de guitarra a tablaturas Guitar Pro mediante un
pipeline modular de modelos de IA. **Uso personal, ejecución local.**

> Documentos: [arquitectura](docs/ARQUITECTURA.md), [BRD](docs/BRD.docx), [SRS](docs/SRS.docx), [backlog](docs/BACKLOG.md), [empaquetado](docs/EMPAQUETADO.md), [análisis de calidad](docs/ANALISIS_CALIDAD.md), [validación de corpus](docs/VALIDACION_CORPUS.md) y [modelo de guitarra (parqueado)](docs/MODELO_GUITARRA.md).
>
> Estado: **Fases 0–6 completas + sesión de calidad**. Shell Tauri + UI + visor alphaTab + HITL
> (audio sincronizado, re-procesado por región) + afinaciones/capo + técnicas Tier 1/2/3. Además:
> **score de banda multipista** (2 guitarras paneadas + bajo + batería + voz), **fix de KV-cache**
> que hizo usable mr_mt3 en canciones reales (>60×), y detección de riffs repetidos. Calidad
> validada vs el GP oficial de *Master of Puppets*: **DTW ~84% / contenido ~99%** (cerca del techo
> práctico para mezcla densa — ver [análisis](docs/ANALISIS_CALIDAD.md)).

## Pipeline

```
preproceso → [separación Demucs] → audio→MIDI → MIDI→tab (digitación) → técnicas → Guitar Pro
   librosa     (estéreo L/R +      basic_pitch    DP + matriz de         Tier 1/2/3  PyGuitarPro
   + tempo      bajo/batería/voz)   o mr_mt3       inhibición                         (.gp5/.gp4/.gp3)
```

Transcriptores (audio→MIDI):
- **`basic_pitch`** (Spotify, ONNX): ligero, rápido, sin GPU obligatoria. Default práctico para
  guitarra/bajo y para canciones densas (mr_mt3 sobre-transcribe en metal).
- **`mr_mt3`** (familia MT3, SOTA en GuitarSet, F1 0.850): multi-instrumento; **única vía para
  transcribir batería** (percusión). Usable en canciones largas gracias al fix de KV-cache
  (`_mt3_compat`): de >2 h a ~3.8 min.

MIDI→Tab: programación dinámica que minimiza el movimiento de mano con la **matriz de inhibición**
(restricción física: una cuerda por nota, span de acorde limitado, posiciones válidas).

**Separación (Demucs) + score multipista**: `--separate` aísla la guitarra; `--multi-instrument`
añade bajo y batería en pistas separadas; `--stereo-guitars` recupera las **2 guitarras paneadas
L/R** (el lever que más mejoró la fidelidad: DTW 76%→84%); `--vocals` añade la melodía vocal.

## Instalación

```bash
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt   # Windows
```

## Uso

```bash
# Desde audio (mp3/wav)
.venv/Scripts/python.exe cli/transcribe.py samples/cancion.mp3 -o salida.gp5

# Desde un MIDI existente (salta la transcripción)
.venv/Scripts/python.exe cli/transcribe.py riff.mid --from-midi -o riff.gp5 --bpm 100

# Aislando la guitarra con Demucs (requiere instalar demucs + torch)
.venv/Scripts/python.exe cli/transcribe.py mezcla.wav -o tab.gp5 --separate --device cuda

# Score de banda completo: 2 guitarras paneadas (L/R) + bajo + batería + voz
.venv/Scripts/python.exe cli/transcribe.py mezcla.mp3 -o banda.gp5 \
    --separate --device cuda --multi-instrument --stereo-guitars --vocals
```

Opciones principales: `--transcriber {basic_pitch,mr_mt3}`, `--separate`, `--multi-instrument`,
`--stereo-guitars`, `--vocals`, `--tuning {standard,drop_d}`, `--capo`, `--calibrate`,
`--open-string-pref {alta,media,baja}`, `--bpm` (auto si se omite), `--work-dir`, formato por
extensión de `-o` (`.gp5` / `.gp4` / `.gp3`).

### Herramientas de evaluación (`scripts/`)
```bash
# Comparar una salida vs un GP oficial (DTW chroma + contenido)
python scripts/compare_gp.py "oficial.gp3" salida.gp5 --ref-tracks 0,1 --est-tracks 0,1
# Validar por lotes varios pares (audio + tab oficial) — ver docs/VALIDACION_CORPUS.md
python scripts/validate_corpus.py corpus/ --device cuda
# Detectar riffs repetidos (estructura) de una transcripción
python scripts/detect_structure.py salida.gp5 audio.mp3 --tracks 0,1
# Generar la matriz de inhibición data-driven (opt-in) desde GuitarSet
python scripts/build_inhibition.py
```

## App de escritorio (Tauri — Fase 3)

Shell Tauri que lanza el sidecar al abrir (y lo termina al cerrar) y muestra la UI
(`ui/`: subir audio, parámetros, progreso, descargar). Requiere Rust + Node.

```bash
npm install                 # instala el CLI de Tauri
npm run dev                 # tauri dev: ventana de escritorio (lanza el sidecar)
npm run build               # tauri build: ejecutable + instalador Windows
```

En dev, el shell lanza `\.venv\Scripts\python.exe -m sidecar`. Para producción, el
sidecar se empaqueta como venv embebido (ver [empaquetado](docs/EMPAQUETADO.md));
configurable con `AUDIO2TAB_PYTHON` y `AUDIO2TAB_CWD`.

## Sidecar (API local — Fase 2)

Backend FastAPI que el shell de escritorio (Tauri, Fase 3) lanzará como subproceso. Cola en
proceso de un solo worker (serializa por VRAM) + estado en SQLite. Datos en `~/.audio2tab`
(o `AUDIO2TAB_DATA`).

```bash
python -m sidecar          # arranca en http://127.0.0.1:8765
```

Endpoints:
- `POST /jobs` — multipart: `file` + params (`transcriber`, `separate`, `auto_bpm`,
  `bpm`, `output_format`, `calibrate_tuning`, `open_string_pref`, `from_midi`) → `{id}`.
  El tempo se **detecta automáticamente** (`auto_bpm=true`); `bpm` solo se usa como override.
- `GET /jobs/{id}` — estado: `queued|running|done|error`, `stage`, `progress`, `n_notes`.
- `GET /jobs/{id}/result` — descarga el `.gp5/.gp4/.gp3`.
- `GET /jobs` · `GET /healthz`.

```bash
# ejemplo
curl -F "file=@cancion.wav" -F "transcriber=mr_mt3" -F "open_string_pref=alta" \
     http://127.0.0.1:8765/jobs
```

> ⚠️ Los flags de **score de banda** (`--multi-instrument`, `--stereo-guitars`, `--vocals`) y la
> detección de estructura son por ahora **solo CLI**; exponerlos por el sidecar + UI está
> pendiente (ver `SIDE-01` en el backlog).

## Tests

**33 tests** del núcleo (digitación + inhibición + export GP + multipista + percusión +
estructura + CLI + sidecar + reprocess), rápidos y sin modelos pesados:

```bash
python tests/test_pipeline.py     # 14 — digitación, inhibición, export, técnicas
python tests/test_multitrack.py   # 10 — multipista, percusión, drums, voz, beats, matriz aprendida
python tests/test_structure.py    #  5 — detección de riffs repetidos
python tests/test_cli.py          #     CLI básico + parámetros avanzados
python tests/test_reprocess.py    #     re-procesado por región
python tests/test_sidecar.py      #     ciclo de vida de un job
```

## Estructura

```
sidecar/pipeline/   # etapas: preprocess, separate, transcribe, to_tab, inhibition,
                    #   techniques, to_gp, structure, reprocess, runner, _mt3_compat, types
sidecar/            # server.py, queue.py, db.py, config.py (API local + cola + SQLite)
cli/transcribe.py   # orquestador CLI
src-tauri/ · ui/    # shell de escritorio (Tauri) + frontend (visor alphaTab, HITL)
scripts/            # compare_gp, compare_excerpt, validate_corpus, detect_structure,
                    #   build_inhibition, eval_fretting, validate_kvcache
bench/              # benchmark de F1 sobre GuitarSet
docs/               # arquitectura, BRD/SRS, backlog, análisis de calidad, validación
tests/              # 33 tests del núcleo
samples/ · storage/ # audio/MIDI de prueba · artefactos por ejecución (gitignored)
```

## Fase 1 — Benchmark de calidad

Infraestructura para medir y comparar transcriptores sobre datos reales con tablatura
"verdad", y elegir el principal por **F1 medido** (no por intuición).

```bash
# Requiere torch+CUDA, demucs, mir_eval, mirdata (ver requirements-fase1.txt)
python bench/run_benchmark.py --dataset guitarset --n 5
python bench/run_benchmark.py --dataset dir --path mis_pruebas/   # <name>.wav + <name>.mid
```

Resultados sobre **GuitarSet** (audio mic), F1 de onset a 50 ms:

| Transcriptor | F1 medio | Precisión | Recall |
|---|---|---|---|
| **mr_mt3** (SOTA, familia MT3) | **0.850** | 0.851 | 0.849 |
| basic_pitch (baseline) | 0.733 | 0.650 | 0.857 |
| demucs+basic_pitch | 0.736 | 0.643 | 0.872 |

**Hallazgos:**
- **El SOTA gana por F1 medido**: `mr_mt3` (0.850) supera a Basic Pitch (0.733) en +0.117,
  alcanzando el rango de la literatura (~0.85). Varias piezas llegan a 0.99–1.00.
- Integrar la familia MT3 sobre el stack 2026 (torch 2.6, transformers 5.x) requirió:
  - **`_mt3_compat.py`**: shims que restauran métodos de `ModuleUtilsMixin` que transformers
    5.x removió (el T5 vendorizado de mt3-infer los usa).
  - **Corrección de deriva temporal**: mt3-infer comprime el eje de tiempo ~1% (error de
    frame-rate); sin corregir, los onsets tardíos se salen de la ventana y el F1 colapsa a
    ~0.30. La constante `MT3_TIME_SCALE` (≈1.010) lo recupera.
  - `yourmt3` (el más potente) queda bloqueado por incompatibilidades profundas de
    transformers 5.x; `mt3_pytorch` falla al clonar por git-lfs en Windows. **`mr_mt3` es el
    modelo MT3 operativo** en este stack.
- Sobre guitarra **ya aislada**, Demucs no aporta (introduce artefactos) → la separación es
  para mezclas completas, no para pistas limpias. Confirma hacerla opcional por job.
- La **matriz de inhibición** (`sidecar/pipeline/inhibition.py`) es la etapa 4b central:
  el DP de digitación descarta posiciones imposibles y minimiza coste ergonómico.
- Gestión de VRAM (`sidecar/pipeline/gpu.py`): `free_vram()` con `gc.collect()` +
  `torch.cuda.empty_cache()` para la carga secuencial de modelos en 8 GB.

## Calidad: qué funciona y qué no (medido)

La meta es un **borrador editable de alta calidad**, no transcripción perfecta (ni las
herramientas comerciales lo logran desde mezcla). Validado vs el GP oficial de *Master of
Puppets* (ver [`ANALISIS_CALIDAD.md`](docs/ANALISIS_CALIDAD.md)):

- ✅ **Lo que mejoró la fidelidad**: transcripción **estéreo** (recuperar las 2 guitarras
  paneadas L/R) → DTW 76%→84%. Funciona porque **añade información real**.
- ❌ **Lo que NO ayudó** (probado con datos): tempo dinámico, limpieza de notas, snap-to-escala,
  matriz de inhibición de GuitarSet, consenso por repetición. El metric es robusto y la música
  real (cromatismo, variación) excede los priors → estamos cerca del **techo práctico**.
- ⛔ **Modelo específico de guitarra** (mayor lever de fidelidad): parqueado — ningún modelo SOTA
  publica pesos (ver [`MODELO_GUITARRA.md`](docs/MODELO_GUITARRA.md)).

## Próximos pasos

- **UX-04 — "Arregla un riff una vez, propágalo a sus repeticiones"**: el cimiento
  (`structure.py`, detecta riffs repetidos) ya está; falta el consumo en la UI alphaTab.
- **UX-01 — Mapa de confianza** en el visor (revisar primero lo peor).
- **Validación cross-género**: probar más artistas/subgéneros con `scripts/validate_corpus.py`
  (ver [`VALIDACION_CORPUS.md`](docs/VALIDACION_CORPUS.md)).
- Backlog completo (con IDs y prioridades) en [`docs/BACKLOG.md`](docs/BACKLOG.md).
