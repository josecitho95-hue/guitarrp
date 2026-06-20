# Audio2Tab

Sistema de transcripción de audio de guitarra a tablaturas Guitar Pro mediante un
pipeline modular de modelos de IA. **Uso personal, ejecución local.**

> Documentos: [arquitectura](docs/ARQUITECTURA.md), [BRD](docs/BRD.docx), [SRS](docs/SRS.docx), [backlog](docs/BACKLOG.md) y [empaquetado](docs/EMPAQUETADO.md).
> Estado actual: **Fase 6 COMPLETA** — shell Tauri + UI web + visor alphaTab + sincronización bidireccional + re-procesamiento por región + afinaciones/capo avanzados + técnicas expresivas completas (Tiers 1, 2, 3) + digitalización robusta con fallback + Garbage Collection. SOTA `mr_mt3` F1=0.985.

## Pipeline

```
preproceso → [separación Demucs] → audio→MIDI → MIDI→tab (digitación) → Guitar Pro
   librosa        (opcional)        Basic Pitch    DP + restricción       PyGuitarPro
                                                    física                 (.gp5/.gp4/.gp3)
```

Transcriptores:
- **Audio→MIDI**: `mr_mt3` (familia MT3, SOTA, por defecto) o `basic_pitch` (ligero, sin GPU).
- **MIDI→Tab**: algoritmo de programación dinámica que minimiza el movimiento de mano
  con restricciones físicas (una cuerda por nota, span de acorde limitado, posiciones
  válidas) — hace de "matriz de inhibición" ligera.
- **Separación**: cableada pero desactivada por defecto (pesada).

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
```

Opciones: `--bpm`, `--onset-threshold`, `--min-note-ms`, `--work-dir`, formato por
extensión de `-o` (`.gp5` por defecto, `.gp4`, `.gp3`).

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

## Tests

Tests de humo del núcleo (digitación + inhibición + export GP), rápidos y sin modelos pesados:

```bash
python tests/test_pipeline.py        # runner standalone
python -m pytest tests/ -q           # si tienes pytest
```

## Estructura

```
sidecar/pipeline/   # etapas: preprocess, separate, transcribe, to_tab, to_gp, types
cli/transcribe.py   # orquestador CLI (Fase 0)
docs/               # BRD.docx, SRS.docx (+ generadores build_*.js)
samples/            # audio/MIDI de prueba y salidas .gp
storage/jobs/       # artefactos intermedios por ejecución (gitignored)
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

## Limitaciones de Fase 0 (conocidas)

- La calidad de la transcripción depende de Basic Pitch; en mezcla completa conviene
  `--separate`. La transcripción polifónica desde mezcla es el caso más difícil.
- La cuantización rítmica ajusta cada onset a una rejilla de semicorcheas con una única
  duración por nota (sin ligaduras); es suficiente para un borrador abrible y editable.
- Aún sin detección de técnicas expresivas (Fase 4) ni UI/visor (Fase 3–5).

## Próximos pasos

- **Fase 5**: Human-in-the-loop (HITL) completo con reproducción sincronizada de audio MP3 original, selección de rango y re-procesado por región (recorte -> re-transcripción -> empalme).
- Mejoras opcionales de calidad: afinar `MT3_TIME_SCALE`; reintentar `yourmt3`/`mt3_pytorch`.
