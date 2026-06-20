# Plan: Sistema de Transcripción de Audio a Tablaturas (Audio2Tab) — Edición Máxima Calidad

## Context

**Idea:** sistema que toma un audio (MP3/WAV de canción completa) y produce una tablatura de
guitarra editable en formato Guitar Pro (`.gp5`), usando los mejores modelos de IA disponibles.

**Objetivo dominante:** **máxima calidad de transcripción posible**, sin importar costo
adicional — pero ejecutando **localmente** en el hardware del usuario.

**Hallazgo central de la investigación (jun 2026):** el problema NO se resuelve con un LLM ni
con un único modelo, sino con un **pipeline modular** de transformers especializados, y **lo
mejor de cada etapa ya existe pre-entrenado en open source**. Entrenar desde 0 sería peor que
descargar el estado del arte. La calidad se gana **eligiendo el mejor modelo por etapa +
human-in-the-loop**, no entrenando.

**Decisiones tomadas con el usuario:**
- Estrategia de modelo: **mejores pre-entrenados en inferencia** (NO entrenar, NO fine-tuning).
- Alcance: **guitarra polifónica desde la mezcla completa** (MP3 → separar → tab).
- Destino: **uso personal, todo local**.
- Hardware: **RTX 4070 8GB VRAM + i9-13980HX (24C/32T) + 24GB RAM**. La VRAM (8GB) es el
  recurso escaso; el CPU es abundante → repartir trabajo CPU↔GPU para que la VRAM no sea cuello
  de botella (ver "Estrategia GPU+CPU").
- Formato de salida: **GP5 por defecto, con export opcional a GP4/GP3** (PyGuitarPro soporta los
  tres desde el mismo modelo; coste casi nulo, mayor compatibilidad y fallback de estabilidad).
- Entregables de doc: **este plan ahora**; SRS.docx / BRD.docx se generan después.
- **Uso estrictamente personal, sin distribución ni comercialización.** Esto elimina la
  barrera de licencias: GPL-3.0 solo obliga a liberar código *al distribuir*; sin distribución,
  podemos **replicar, copiar y adaptar libremente** YourMT3+, festivalhopper y cualquier repo
  GPL. La selección de modelos se decide solo por **calidad**, no por licencia.
- **Restricción de realismo físico como principio de diseño:** la **matriz de inhibición** es
  un componente CENTRAL (no opcional) que impide generar posiciones cuerda/traste imposibles
  o no ergonómicas en cualquier backbone.

**Aclaración clave (OpenRouter):** OpenRouter es una pasarela de **LLMs de texto/chat**; NO
aloja Demucs, YourMT3+, Basic Pitch ni modelos de tablatura. El núcleo del pipeline son
modelos PyTorch que se ejecutan localmente, no por API de LLM. Por eso el diseño es local.
Un LLM (vía OpenRouter, opcional) solo se usaría para tareas accesorias (nombrar secciones,
limpiar metadatos), nunca para la transcripción.

**Expectativa honesta de calidad:** ni las herramientas comerciales logran transcripción
perfecta de guitarra polifónica desde mezcla. La meta es "borrador de alta calidad, editable",
con F1 de referencia en el rango ~85–88% (estado del arte sobre guitarra limpia; menos sobre
mezcla). Por eso la edición humana de la tab generada es parte del diseño, no un añadido.

---

## 1. Arquitectura del sistema (app de escritorio Tauri + Python embebido, sin Docker)

App de escritorio autocontenida: el shell **Tauri** (Rust + webview del sistema) muestra la UI
y lanza/gestiona un **sidecar Python** (servidor local FastAPI) que ejecuta el pipeline en la
GPU. No hay Docker, ni Redis, ni Celery: para un solo usuario, una **cola local en proceso**
(tareas en background + estado en SQLite) basta y simplifica el empaquetado.

```
┌─────────────────────── App de escritorio (un solo binario instalable) ───────────────────────┐
│  [Tauri shell: Rust + webview]                                                                │
│        │  arranca al abrir / mata al cerrar                                                   │
│        ▼                                                                                      │
│  [Sidecar Python (FastAPI en 127.0.0.1:PORT)]                                                 │
│        │  encola job → cola local (thread/async) + estado en SQLite                           │
│        ▼                                                                                      │
│  [Pipeline 5 etapas en la 4070 (chunked, carga/descarga secuencial de modelos)]              │
│        └── resultado .gp5  ──▶ UI (progreso por SSE/polling, descarga/abrir)                  │
└──────────────────────────────────────────────────────────────────────────────────────────────┘
        (fallback opcional: GPU nube por-uso si un modelo no cupiera — desactivado por defecto)
```

El sidecar se empaqueta como ejecutable autocontenido (PyInstaller, o entorno Python
embebido construido con `uv`) y se declara como **Tauri sidecar/resource**, de modo que Tauri
lo arranca como subproceso. Los checkpoints de modelos se descargan a una carpeta de datos del
usuario en el primer uso (no van dentro del instalador para no inflarlo de más).

### Pipeline de IA — selección por MÁXIMA CALIDAD

| # | Etapa | Modelo OSS elegido (calidad) | VRAM inferencia | Notas |
|---|-------|------------------------------|-----------------|-------|
| 1 | Pre-proceso | `ffmpeg` + `librosa` | CPU | MP3 → WAV mono/estéreo 44.1k normalizado |
| 2 | Separación | **Demucs `htdemucs`** (o `htdemucs_ft`) | ~4–6 GB | aislar stem de guitarra; usar `--segment` para chunking |
| 3 | Audio→MIDI | **High-Resolution Guitar Transcription** (domain-adapt) como principal; **YourMT3+** como alterno multi-instrumento | ~6–8 GB | inferencia por ventanas; YourMT3+ robusto en mezclas reales |
| 4 | MIDI→Tab | **Fretting-Transformer / open-fret** (T5) | <1 GB | asigna cuerda+traste; fallback: programación dinámica |
| 4b | **Restricción física (CENTRAL)** | **Matriz de inhibición** (de inhibition repo) | CPU | filtra/penaliza posiciones imposibles o no ergonómicas; se aplica a la salida de la etapa 4 (Path A) o del CRNN (Path B) |
| 4c | **Detección de técnicas** | Análisis de contorno de pitch + onsets (Tier 1) + clasificador timbre (Tier 2) | CPU | marca HOPO/slide/bend/vibrato; palm mute/armónicos; tapping/sweep como sugerencia. Ver "Técnicas expresivas" |
| 5 | Tab→GP | **PyGuitarPro** (`NoteEffect`) (+ alineamiento nota→compás portado de festivalhopper) | CPU | escribe técnicas + notas en `.gp5` (default) o `.gp4`/`.gp3`; mismo modelo en memoria |

**Por qué estos modelos:** High-Res Guitar Transcription (Riley et al.) y GAPS marcan el
estado del arte (~88% F1 en GuitarSet); YourMT3+ aporta robustez en audio mezclado real con su
Mixture-of-Experts. Fretting-Transformer resuelve el "fretting" que el borrador original
marcaba como el mayor reto — ya no hay que escribir ese algoritmo.

### Estrategia GPU+CPU (8GB VRAM escasa, CPU de 32 hilos abundante)
- **GPU solo para el modelo pesado de turno**: separación o transcripción, uno a la vez,
  cargando/descargando para que la VRAM nunca tenga dos modelos grandes.
- **Liberación explícita de VRAM entre modelos (crítico con 8GB)**: PyTorch retiene memoria
  reservada en la GPU aunque se destruyan las variables. Tras terminar un modelo y antes de
  cargar el siguiente, llamar explícitamente a `del modelo`, `gc.collect()` y
  `torch.cuda.empty_cache()`. Sin esto, la transición Demucs → YourMT3+ puede agotar la VRAM.
- **Empujar a CPU todo lo que no necesita GPU**: MIDI→tab (T5 diminuto), **matriz de inhibición
  + DP de digitación** (CPU puro, paralelizable por compás), beat/tempo/onset (librosa/madmom),
  ffmpeg + CQT/STFT del preprocesado (FFT multihilo).
- **Pipelining CPU↔GPU**: mientras la GPU transcribe el chunk N, la CPU pre-procesa el N+1 y
  post-procesa el N−1 → solape que sube throughput casi sin coste.
- **Modo lote paralelo**: con 32 hilos, procesar varias canciones a la vez (preprocesado y
  post-procesado en CPU) mientras la GPU sirve de cola para la etapa pesada.
- **Demucs en CPU como opción/overflow**: si se quiere reservar 100% de VRAM para transcripción,
  Demucs corre en CPU (más lento, pero viable con 32 hilos). Configurable por job.
- **Chunking + fp16** en etapas GPU con solapamiento para no cortar notas.
- **Fallback opcional a nube por-uso** (RunPod/Vast), SOLO si un modelo no cupiera; off por defecto.

### Stack tecnológico
- **Shell de escritorio:** **Tauri** (Rust + webview del sistema); UI web (React/Svelte/Vanilla).
- **Visor/editor de tab (HITL):** **alphaTab** (MPL-2.0) — renderiza GP3-7, reproduce con
  sintetizador MIDI + cursor en vivo, selección de rangos. Base del flujo human-in-the-loop.
- **Backend (sidecar):** FastAPI local (async) en `127.0.0.1`, arrancado por Tauri.
- **Cola/tareas:** **cola local en proceso** (FastAPI BackgroundTasks o un worker en thread) +
  estado de jobs en **SQLite**. Sin Celery/Redis.
- **IA:** PyTorch (CUDA), Demucs, High-Res Guitar Transcription / YourMT3+, open-fret,
  librosa, pretty_midi, PyGuitarPro.
- **Empaquetado:** sidecar Python a ejecutable con **PyInstaller** (o entorno embebido con `uv`),
  declarado como Tauri sidecar; instalador Windows generado por Tauri (`.msi`/`.exe`). `ffmpeg`
  se incluye como binario embebido. CUDA usa el driver/runtime de la GPU del sistema (no Docker).

### Flujo human-in-the-loop: visor + re-procesado por regiones (con alphaTab)
Bucle de refinamiento iterativo antes de exportar. **Tier A (en alcance, complejidad media)**;
**Tier B (fuera, se delega a Guitar Pro/TuxGuitar real)**.
- **Visor (alphaTab):** renderiza la tab generada, la reproduce (synth + cursor), permite
  seleccionar un rango de compases. Coste bajo (lo da la librería).
- **Reproducción del audio original sincronizada:** `<audio>` con el MP3 + alternar entre
  "original" y "synth"; sync vía el mapa **compás→tiempo** producido en la etapa 5 (sync flojo
  primero; fino después). Coste medio.
- **Re-procesar región (pieza nueva clave):** el usuario selecciona compases → el sidecar
  recorta ese rango del audio original, lo pasa por el pipeline con parámetros distintos (otro
  modelo, sensibilidad, fretting alterno) y **empalma** el resultado en los compases correctos
  del `Song` en memoria, cuidando bordes/tempo. alphaTab re-renderiza. Coste medio-alto.
- **Iterar y exportar:** repetir hasta convencer; mantener el `Song` de trabajo (con undo/redo
  por versión de región) y exportar a GP5/GP4/GP3. Coste medio.
- **Tier B (fuera):** edición manual nota-por-nota (cambiar traste/añadir efecto a mano).
  alphaTab no edita; construirlo es un mini editor → se delega al `.gp5` exportado abierto en
  Guitar Pro/TuxGuitar.

### Detección de técnicas expresivas (etapa 4c)
La salida GP no es solo notas: marca técnicas vía `NoteEffect` de PyGuitarPro. Detección por
niveles de confiabilidad (se escribe lo confiable; lo dudoso se sugiere para revisión humana):
- **Tier 1 — auto (alta confianza):** hammer-on/pull-off (notas consecutivas en la misma cuerda
  sin nuevo onset; asc=hammer, desc=pull), **slides** (glissando continuo entre trastes),
  **bends** (desviación microtonal → puntos de bend ¼/½/full), **vibrato** (oscilación periódica
  de pitch). Todo derivable del **contorno de pitch continuo** que producen High-Res/FretNet.
- **Tier 2 — clasificador de timbre (media):** palm mute (espectro apagado/corto) y armónicos
  (espectro tipo campana). Usa un clasificador ligero; dataset **Guitar-TECHS** como referencia.
- **Tier 3 — heurística / sugerencia (baja):** tapping (saltos legato amplios y altos) y sweep
  picking (arpegio rápido entre cuerdas adyacentes). Se marcan como sugerencia de baja confianza
  para que el revisor humano (F7) confirme; no se imponen.
- **Antecedente OSS:** el pipeline del Fretting-Transformer incluye una etapa de clasificación
  de técnicas (MLP); sirve de referencia para Tier 2.
- **Nota de formato:** GP5/GP4 soportan todas estas técnicas; GP3 es más limitado (algunas se
  degradan) → si se exporta a GP3, las técnicas no soportadas se omiten con aviso.

### Estructura de carpetas
```
audio2tab/
├─ src-tauri/                 # shell Tauri (Rust): arranca/mata el sidecar, ventana, IPC
│  ├─ tauri.conf.json         # declara el sidecar y los recursos
│  └─ src/main.rs
├─ ui/                        # frontend web: subir, progreso, visor alphaTab (render+play+
│                             # selección de rango), reproductor del MP3 original, re-procesar
├─ sidecar/                   # backend Python empaquetable
│  ├─ pyproject.toml
│  ├─ server.py               # FastAPI: /jobs, /jobs/{id}, SSE; /jobs/{id}/reprocess (rango)
│  ├─ reprocess.py            # recorte (con padding 200-300ms) + re-transcripción + empalme
│  ├─ config.py               # settings (carpeta de datos, flag fallback nube off)
│  ├─ db.py                   # SQLite: estado de jobs
│  ├─ queue.py                # cola local en proceso
│  ├─ schemas.py
│  └─ pipeline/
│     ├─ preprocess.py        # ffmpeg + librosa
│     ├─ separate.py          # Demucs (chunked)
│     ├─ transcribe.py        # High-Res / YourMT3+ (ventaneo)
│     ├─ to_tab.py            # Path A: open-fret + matriz de inhibición; fallback DP
│     ├─ inhibition.py        # restricción física central (etapa 4b)
│     ├─ techniques.py        # detección de técnicas expresivas (etapa 4c, Tiers 1-3)
│     └─ to_gp.py             # PyGuitarPro: notas + NoteEffect → gp5/gp4/gp3
├─ cli/transcribe.py          # pipeline completo sin UI (dev/uso por lotes)
├─ models/                    # checkpoints (descargados a carpeta de datos del usuario en runtime)
├─ tests/
└─ docs/  (BRD.md/.docx, SRS.md/.docx)
```

---

## 2. Funcionalidades (MVP)
- **F1** Subir audio (MP3/WAV) y crear job.
- **F2** Procesamiento asíncrono con estados (`queued→separating→transcribing→tabbing→done/error`).
- **F3** Consultar progreso (polling/SSE).
- **F4** Descargar la tablatura en el formato elegido (`.gp5` default / `.gp4` / `.gp3`).
- **F5** Parámetros: afinación (estándar/Drop D), capo, BPM auto/manual, elegir modelo de
  transcripción (High-Res vs YourMT3+), formato de salida (GP5/GP4/GP3) y dónde corre Demucs
  (GPU/CPU).
- **F6** Persistir artefactos intermedios (stem WAV, MIDI, tab JSON) para inspección/reproceso.
- **F7** Human-in-the-loop (Tier A): visor alphaTab que renderiza y reproduce la tab (synth +
  cursor), reproduce el MP3 original sincronizado, permite **seleccionar compases y re-procesar
  esa región** con otros parámetros, iterar, y confirmar/descartar técnicas Tier 3 antes de
  exportar. (Edición manual nota-por-nota = Tier B, fuera; se delega a Guitar Pro/TuxGuitar.)
- **F8** Marcado de técnicas expresivas en la salida GP: Tier 1 (HOPO, slides, bends, vibrato)
  automático; Tier 2 (palm mute, armónicos) con clasificador; Tier 3 (tapping, sweep) como
  sugerencia revisable.
- **F9 (post-MVP)** CLI por lotes; fallback a GPU de nube on-demand.

Fuera de alcance MVP: multiusuario, login, billing, otros instrumentos,
entrenamiento/fine-tuning de modelos. Las técnicas expresivas SÍ entran (F8), por niveles:
Tier 1 en el MVP; Tier 2/3 en fases siguientes.

---

## 3. Estructura del SRS (IEEE 830 / ISO-29148) — a redactar después
1. Introducción — propósito, alcance, definiciones (tab, stem, MIDI, GP5, F1), referencias.
2. Descripción general — perspectiva, funciones, usuario (guitarrista hobbyista), restricciones
   (4070 8GB, inferencia local por chunks), supuestos y dependencias.
3. Requisitos funcionales — F1–F9 con ID, entrada, proceso, salida, criterio de aceptación.
4. Requisitos no funcionales — rendimiento (objetivo orientativo: canción de 4 min en pocos
   minutos en la 4070), fiabilidad, usabilidad, portabilidad (app Tauri autocontenida, sin
   dependencias externas que instalar), restricción de VRAM, tamaño del instalador.
5. Requisitos de interfaz — API local FastAPI (Tauri↔sidecar), interfaz de archivos (formatos
   in/out), hardware (GPU/CUDA del sistema).
6. Modelos del sistema — diagrama de pipeline, estados del job, secuencia.
7. Apéndices — glosario, matriz de trazabilidad requisito↔feature.

## 4. Estructura del BRD — a redactar después
1. Resumen ejecutivo — problema (transcribir a mano es lento) y solución.
2. Objetivos personales — éxito = transcribir tus canciones en minutos con calidad editable.
3. Stakeholders — tú (owner/usuario), comunidad OSS.
4. Alcance — in/out (ver §2).
5. Requisitos de negocio de alto nivel — BR-01…n (lenguaje no técnico).
6. AS-IS vs TO-BE — flujo manual vs automatizado.
7. Supuestos, restricciones y riesgos — ver §6.
8. Criterios de aceptación / definición de "hecho".

---

## 5. Componentes OSS de referencia y piezas reutilizables (analizados)

### Dos backbones a comparar (no elegir a ciegas — ver Fase 1 benchmark)
- **Path A (modular):** Demucs → audio→MIDI → MIDI→tab (open-fret + inhibición) → GP5.
  Más flexible y editable, pero acumula error entre etapas.
- **Path B (directo audio→tab):** Demucs → CRNN de **trimplexx** (predice cuerda/traste
  directo) → GP5. Menos etapas, todo MIT, pero entrenado solo en acústica solista (riesgo de
  no generalizar a eléctrica/mezcla). El orquestador debe soportar ambos y elegir por F1 medido.

### Piezas concretas a reutilizar (no solo modelos)
| Repo | Licencia | Qué tomar |
|------|----------|-----------|
| **cwitkowitz/guitar-transcription-with-inhibition** | MIT | **Matriz de inhibición** (combinaciones cuerda/traste tocables desde DadaGP/GuitarSet) para restringir/re-rankear el fretting; conversión GuitarPro→JAMS con PyGuitarPro; métricas vía `amt-tools` |
| **trimplexx/music-transcription** | MIT | CRNN audio→tab (Path B); preprocesado **CQT** (168 bins); pipeline de aumentación; loader GuitarSet vía `mirdata`; export ASCII/MIDI; utilidades de inferencia frame→nota |
| **open-fret** (Sidmaz666) | MIT | Tokenización y `tokens_to_tab.py`; config T5 del Fretting-Transformer (sin pesos públicos) |
| **YourMT3+** (mimbres) | GPL-3.0 (OK uso personal) | audio→MIDI multi-instrumento robusto en mezclas reales; demo en HF Spaces. Candidato **principal** de la etapa 3 junto con High-Res |
| **festivalhopper/music-transcription** | GPL-3.0 (OK uso personal) | **Portar** su alineamiento nota→compás/beat y escritura GP5 con PyGuitarPro de Python 3.5/Theano a Python moderno (reusar la lógica, no el stack viejo) |
| **High-Res Guitar Transcription** (xavriley) | paper+dataset | audio→MIDI SOTA (basado en Kong et al.); **dataset en Zenodo** reutilizable para benchmark; revisar arXiv 2402.15258 por código/pesos de inferencia |
| **GAPS / Basic Pitch** | permisiva | Alternativas de transcripción para comparar calidad (Basic Pitch es ligerísimo, buena baseline) |
| **PyGuitarPro** | LGPL | Escritura `.gp5` (etapa 5) |
| **Guitar-TECHS** (dataset) | dataset | Etiquetas de **técnicas expresivas** (palm mute, armónicos, etc.) — referencia para el clasificador de la etapa 4c (Tier 2) |
| Datasets: **GuitarSet, GAPS, GOAT, DadaGP** | varias | Solo evaluación/benchmark e inhibición, no entrenamiento |

### Nota de licencias (resuelto: uso personal)
Al ser **uso estrictamente personal sin distribución**, GPL-3.0/LGPL no imponen restricción
práctica: se puede copiar, portar y adaptar cualquier repo (incluidos YourMT3+ y festivalhopper)
directamente al código. **La selección se hace solo por calidad.** (Si en el futuro se decidiera
distribuir, habría que revisar: aislar GPL tras proceso o reimplementar — fuera de alcance hoy.)

**Recomendación:** orquestador que invoque/porte cada componente como librería/subproceso,
cargando/liberando VRAM secuencialmente. Replicar directamente: la matriz de inhibición
(central), el CRNN de trimplexx (Path B), open-fret (Path A), y el alineamiento+export GP5
portado de festivalhopper a Python moderno. Nada de OpenRouter en el núcleo.

---

## 6. Riesgos y mitigaciones
- **Calidad polifónica desde mezcla** (alto): separar+transcribir acordes es lo más difícil.
  *Mitigación:* expectativa "borrador editable"; permitir subir pista limpia para máxima
  precisión; revisión humana (F7); medir F1 sobre un set propio.
- **8GB VRAM insuficientes para algún modelo grande** (medio): *Mitigación:* chunking, fp16,
  carga secuencial; fallback opcional a GPU de nube on-demand.
- **Compatibilidad CUDA/PyTorch/Demucs/YourMT3+** (medio): *Mitigación:* fijar versiones de
  wheels (torch+cuXXX) en `pyproject.toml`/lockfile con `uv`; usar el runtime CUDA del sistema.
- **Empaquetar PyTorch+CUDA con PyInstaller** (medio-alto): es la parte frágil del enfoque
  embebido — PyInstaller suele romper al resolver los hooks dinámicos de PyTorch y al empaquetar
  las DLLs de CUDA (varios GB). *Mitigación:* validar el empaquetado temprano (Fase 2) con un
  "hola mundo" de torch+CUDA antes de meter todo el pipeline; **si PyInstaller falla, NO insistir**:
  usar una **distribución de Python portable embebida** (entorno creado con `uv` o `micromamba`),
  empaquetar el venv completo junto al binario de Tauri y que el shell Rust llame directamente al
  `python.exe` de esa carpeta. Esta es la ruta de respaldo preferida, no un último recurso.
- **open-fret inmaduro** (medio): *Mitigación:* fallback de programación dinámica en etapa 4.
- **Detección de técnicas poco fiable** (alto en Tier 2/3): tapping/sweep son casi indetectables
  desde audio. *Mitigación:* el enfoque por niveles solo auto-escribe lo confiable (Tier 1) y
  deja Tier 3 como sugerencia que el humano confirma; nunca impone un marcado dudoso. Falsos
  positivos de técnicas degradan más la tab que omitirlas → umbral conservador.
- **Empalme del re-procesado por región** (medio-alto): unir la región re-transcrita con el
  resto sin saltos de tempo ni cortes de nota en los bordes. *Mitigación:* re-procesar en
  fronteras de compás, solapar un compás de contexto, y conservar el tempo global del `Song`.
- **Pérdida de transitorios al recortar audio** (medio): si el corte de la región es
  matemáticamente exacto en el beat, se pierde el ataque inicial de la púa y el modelo
  (sobre todo YourMT3+) transcribe peor. *Mitigación:* al extraer la región, añadir un
  **padding de 200–300 ms antes** del inicio del compás para dar contexto del ataque, y luego
  **recortar ese excedente en el MIDI/tab resultante** antes de empalmar.
- **Sincronía MP3 original ↔ tab** (medio): el audio real puede tener rubato/tempo variable.
  *Mitigación:* empezar con sync por compás (flojo) y mejorar con beat-tracking si hace falta.

---

## 7. Fases de implementación
1. **Fase 0 — Spike/CLI:** `cli/transcribe.py` encadena las 5 etapas sobre 1 MP3 conocido,
   sin UI, validando que cabe en la 4070 con chunking → produce `.gp5` abrible.
2. **Fase 1 — Benchmark de calidad (Path A vs Path B):** comparar el camino modular
   (High-Res/YourMT3+ → open-fret+inhibición) contra el directo (CRNN trimplexx), más Basic
   Pitch como base, sobre 3–5 piezas con tab "verdad" (GuitarSet/GAPS/GOAT/Zenodo) usando
   métricas de `amt-tools`; elegir el principal por F1 medido. Aplicar matriz de inhibición
   como re-ranking de fretting en ambos.
3. **Fase 2 — Sidecar + empaquetado temprano:** envolver el pipeline en FastAPI local con cola
   en proceso + SQLite (F1–F4); validar **cuanto antes** el empaquetado PyInstaller de
   torch+CUDA (riesgo principal) con un binario mínimo que corra una inferencia en GPU.
4. **Fase 3 — Shell Tauri:** `src-tauri` arranca/mata el sidecar, UI básica que sube audio y
   muestra progreso (SSE) y descarga el `.gp5`; generar instalador Windows.
5. **Fase 4 — UI + parámetros (F5) + técnicas Tier 1 (F8):** visor alphaTab (render+play+cursor),
   selección de rango; HOPO/slides/bends/vibrato desde contorno de pitch como `NoteEffect`.
6. **Fase 5 — Human-in-the-loop completo (F7):** reproducción del MP3 original sincronizada
   (mapa compás→tiempo) + **re-procesado por región** (`/reprocess`: recorte→pipeline→empalme)
   + iterar/exportar GP5/GP4/GP3.
7. **Fase 6 — Robustez y técnicas Tier 2/3:** clasificador de palm mute/armónicos (Guitar-TECHS),
   sugerencias de tapping/sweep; fallback DP de fretting, manejo de errores, fallback nube
   opcional, descarga de checkpoints en primer uso.

---

## 8. Verificación (end-to-end)
- **Fase 0:** `python cli/transcribe.py samples/cancion.mp3 -o out.gp5`; abrir `out.gp5` en
  TuxGuitar/MuseScore y comparar con el audio. Confirmar que no excede 8GB (monitorear `nvidia-smi`).
- **Por etapa:** inspeccionar la carpeta de datos del job: stem de Demucs debe sonar a guitarra;
  el `.mid` debe reproducir la línea; el `.gp5` debe abrir sin error.
- **Benchmark de calidad:** F1 de multipitch/tab sobre el set propio; comparar modelos.
- **Sidecar:** `POST /jobs` → `job_id`; SSE/polling `GET /jobs/{id}` hasta `done`; descargar `.gp5`.
- **Visor HITL:** abrir un job terminado en el visor alphaTab, reproducir tab y MP3 original,
  seleccionar unos compases, re-procesarlos con otro parámetro y ver que el empalme re-renderiza
  sin romper compases vecinos; exportar el resultado final.
- **App empaquetada:** instalar el `.msi`/`.exe` generado por Tauri en una sesión limpia, abrir,
  arrastrar un MP3 y obtener el `.gp5` — sin instalar Python, CUDA toolkit ni Docker aparte.
- **GPU:** en el sidecar empaquetado, `torch.cuda.is_available()==True` y Demucs/transcripción en GPU.

---

## 9. Siguiente paso tras aprobar
Generaré (fuera de plan mode) `docs/BRD.docx` y `docs/SRS.docx` con el contenido redactado según
§3 y §4, y arrancamos la **Fase 0 (CLI spike)** validando el encaje en la 4070 con chunking.
