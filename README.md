# Audio2Tab

Sistema de transcripción de audio de guitarra a tablaturas Guitar Pro mediante un
pipeline modular de modelos de IA. **Uso personal, ejecución local.**

> Documentos: plan de arquitectura, [BRD](docs/BRD.docx) y [SRS](docs/SRS.docx).
> Estado actual: **Fase 1 — Benchmark de calidad** (infraestructura de medición + baseline + matriz de inhibición). Fase 0 (CLI spike) completa.

## Pipeline

```
preproceso → [separación Demucs] → audio→MIDI → MIDI→tab (digitación) → Guitar Pro
   librosa        (opcional)        Basic Pitch    DP + restricción       PyGuitarPro
                                                    física                 (.gp5/.gp4/.gp3)
```

En Fase 0:
- **Audio→MIDI**: Basic Pitch (se sustituye por High-Res/YourMT3+ en Fase 1).
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

Resultados sobre 4 piezas de **GuitarSet** (audio mic, guitarra ya aislada):

| Transcriptor | F1 medio | Precisión | Recall |
|---|---|---|---|
| basic_pitch | **0.741** | 0.647 | 0.877 |
| demucs+basic_pitch | 0.736 | 0.643 | 0.872 |

**Hallazgos:**
- Sobre guitarra **ya aislada**, Demucs no aporta (introduce artefactos) → la separación es
  para mezclas completas, no para pistas limpias. Confirma hacerla opcional por job.
- Baseline ~0.74 F1; el SOTA (High-Res/GAPS ~0.85–0.88) marca el margen a ganar integrando
  YourMT3+/High-Res (Path A) y el CRNN de trimplexx (Path B) — el harness ya los acepta vía
  el registro `TRANSCRIBERS`.
- La **matriz de inhibición** (`sidecar/pipeline/inhibition.py`) es ahora la etapa 4b central:
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

- **Fase 1 (cierre)**: integrar los modelos SOTA en el harness — YourMT3+ y High-Res (Path A)
  y el CRNN de trimplexx (Path B) — para superar el baseline de Basic Pitch por F1 medido.
- **Fase 2+**: empaquetado (Tauri + sidecar Python embebido), UI y flujo human-in-the-loop
  con alphaTab; detección de técnicas expresivas.
