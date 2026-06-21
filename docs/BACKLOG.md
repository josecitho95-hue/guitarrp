# Backlog — Audio2Tab

Items priorizados con MoSCoW. Cada item indica el problema, la solución propuesta y la
etapa/componente del pipeline afectado.

---

## Prioridad alta — Calidad (lever de fidelidad)

**MG-01 — Modelo de transcripción específico de guitarra** ⛔ *PARQUEADO (sin pesos públicos)*
*Etapa 3 (Audio→MIDI).* Hoy usamos `basic_pitch` (~0.73 F1, genérico) y `mr_mt3` (multi-
instrumento, sobre-transcribe en mezcla densa). Ninguno está entrenado en guitarra.
*Estado (2026-06-20):* **BLOQUEADO.** Verificado que ningún modelo SOTA de guitarra (High-Res,
FretNet, robustez-eléctrica) publica pesos de inferencia — todos exigen entrenar, lo que
contradice la política "no entrenar". Omnizart tiene pesos pero es genérico + TF viejo. Para
mezcla densa el valor esperado es bajo (baseline estéreo DTW ~84% ≈ techo práctico).
**Detalle y plan de reactivación: [`MODELO_GUITARRA.md`](MODELO_GUITARRA.md).**
*Reactivar si:* aparece un modelo con pesos descargables, o se acepta entrenar (FretNet/TabCNN
en GuitarSet, factible en la 4070 pero retorno incierto en metal). La fontanería del pipeline
está lista (aislado a etapa 3 detrás de `list[Note]`).

---

## Should Have

Mejoras de bajo impacto en el código y alto valor de calidad: aditivas, aisladas, sin tocar la
arquitectura. Conviene incorporarlas temprano (al inicio de Fase 2).

**SH-01 — Calibración de tono (pitch drift / afinaciones no estándar)** *(antes CH-01)*
*Etapa 1 (Preproceso).* Muchos audios no están en A=440 Hz: cintas analógicas con variación,
bandas afinadas medio tono abajo (Eb) o en A=432 Hz. Una afinación corrida unos cents confunde
al detector de pitch y genera notas erráticas.
*Solución:* paso de calibración con `librosa` que estime la frecuencia de referencia (A4) real
del audio y aplique un pitch-shift microscópico para cuadrarlo a la rejilla de 440 Hz **antes**
de Demucs/transcripción. (Alternativa: detectar la afinación y exportar la tab en esa afinación
en vez de re-afinar.)
*Impacto:* 🟢 bajo — función nueva autocontenida en `preprocess.py`, no cambia firmas.

**SH-02 — Preferencia configurable por cuerdas al aire** *(antes CH-04)*
*Etapa 4b (Inhibición) + parámetro de job.* El DP minimiza distancia de dedos para hacer la
digitación "tocable", pero un Mi al aire (1ª cuerda) suena y se usa distinto que el mismo Mi en
2ª cuerda traste 5. El sesgo puede elegir la posición "cómoda" pero musicalmente equivocada.
*Solución:* peso/preferencia configurable como parámetro del job (ej. "Preferencia por cuerdas
al aire: Alta/Media/Baja") que ajuste el coste ergonómico en `inhibition.py` (ya existe
`W_OPEN_BONUS`; solo exponerlo).
*Impacto:* 🟢 casi nulo — ~20 líneas, aditivo.

---

## Could Have

No necesarias para el MVP; se consideran en futuras sesiones.

### 1. Mundo acústico real: tempo dinámico

**CH-02 — Mapa de tempo dinámico (vs. BPM estático)** — ⚠️ *PROBADO, SIN MEJORA con `librosa`*
*Etapa 5 (Tab → Guitar Pro).* Piezas con rubato, acelerando/desacelerando (clásico, solos
expresivos) no mantienen un BPM robótico. Asumir un BPM global (F5) desalinea los compases.
*Estado (2026-06-21):* la **infraestructura está implementada y mergeada, apagada por defecto**
(`preprocess.estimate_beats`, `to_gp._make_to_slot`/`_write_tempo_map`, `beats=None` → grid fijo).
Medido sobre MoP (chroma 76.0 vs 76.2) **y sobre Back in Black con beats del stem de batería**
(ventana 46.8% grid fijo vs 42-45% beat-relativo) → **no mejora, incluso empeora**. **Causa
identificada:** el beat-tracker de `librosa` no es lo bastante exacto (jitter de ms) → cuantizar
contra sus beats es peor que una rejilla matemática limpia para tempo estable (la mayoría de la
música). El enfoque es correcto (validado por experto externo); el cuello de botella es la
**exactitud del beat-tracker**. **Desbloqueo real: `madmom`** (beat/downbeat tracking preciso) →
serviría para canciones que ACELERAN (Stairway, outro de SCO). Riesgo: madmom frágil en Windows →
instalar en entorno aislado. No re-intentar con librosa.
*Impacto:* 🟠 medio (infra hecha); reactivación = integrar madmom + evaluar legibilidad (no chroma).

### 2. Casos extremos en la matriz de inhibición

**CH-03 — Poda por exceso de polifonía ("la séptima nota")**
*Etapa 4b (Inhibición).* ¿Qué pasa si el modelo acústico detecta 7 notas simultáneas? Una
guitarra estándar tiene 6 cuerdas (y dedos limitados en un radio de trastes factible).
*Solución:* regla dura de pruning: si la polifonía supera las cuerdas/dedos disponibles,
descartar la(s) nota(s) con **menor confianza** del modelo **antes** de mapear cuerda/traste.
Requiere propagar la confianza por nota desde la etapa 3 (hoy se descarta).
*Impacto:* 🟠 medio — único item que cambia el contrato de datos (`confidence` en `Note`,
poblado en `transcribe.py`). La poda en sí es pequeña.

### 3. UX avanzada en el Human-in-the-Loop

**CH-05 — Reprocesado con anclaje (hinting de zona del mástil)**
*RF-07 (HITL) + Etapa 4b.* Si el usuario sabe visualmente dónde se toca el solo, pasar un
"anclaje" a la matriz de inhibición: ej. "reprocesa estos 2 compases restringiendo todo entre
el traste 12 y el 17". Reduce el espacio de búsqueda y casi garantiza la digitación deseada.
*Solución:* parámetro de rango de trastes (min/max) en `/reprocess` que restrinja los
candidatos del DP en `to_tab.py`.
*Impacto:* 🟢 bajo (núcleo algorítmico trivial); la UX/endpoint entra con Fase 2.

### 4. Ciclo de vida y deuda técnica (almacenamiento)

**CH-06 — Garbage collection de artefactos intermedios**
*RNF (no funcional) + RF-06.* Un stem de guitarra en WAV pesa 30–50 MB; procesar el repertorio
completo lleva la carpeta de datos a gigabytes rápidamente.
*Solución:* limpieza de caché: botón en la UI "Purgar artefactos intermedios", y/o política en
SQLite que elimine los WAV de jobs `done` con más de 30 días (conservando el `.gp` final y,
opcionalmente, el MIDI ligero).
*Impacto:* 🟢 bajo, pero depende de la infraestructura de Fase 2 (BD de jobs + UI).

---

> Origen: observaciones de revisión tras cerrar Fase 1 (2026-06-20). SH-01 y SH-02 promovidos
> desde Could Have por bajo impacto y alto valor. Reevaluar el resto al planificar Fase 2+.

---

## Bitácora de la sesión de calidad (2026-06-20)

Tras retomar el proyecto se validó el flujo end-to-end contra un GP oficial de Master of
Puppets y se probaron levers de calidad con datos (todo mergeado a `main`):

**Hecho / mergeado:**
- **Fix KV-cache de mr_mt3** (PR #1): de inviable (>2 h) a ~3.8 min (>60x), tokens idénticos
  validados. Desbloqueó el modelo SOTA y la transcripción de batería.
- **Score multipista** (PR #1): Guitar + Bass + Drums (percusión en canal MIDI 10).
- **Transcripción estéreo** (PR #2): recupera las 2 guitarras paneadas L/R. **DTW 76% → 84%**
  — el único lever que mejoró la fidelidad de forma medible (añade información del paneo).
- Herramientas: `scripts/compare_gp.py` (DTW + chroma), `scripts/compare_excerpt.py`
  (subsecuencia), `scripts/validate_kvcache.py`.

**Probado y DESCARTADO con datos (NO re-intentar igual):**
- **Tempo dinámico** con librosa: sin mejora (ver CH-02). Necesita `madmom`.
- **Limpieza de notas** (quitar octavas dobladas / notas cortas): sin mejora; el dedup de
  octavas incluso empeora (quita notas reales). El metric chroma es insensible a esto.
- **Más pistas** (lead/Gtr.3, etc.): no mejora fidelidad. Verificado: añadir el lead oficial a
  la referencia mueve DTW solo +0.3; las 2 rítmicas ya son el 98% del contenido. Llegamos al
  techo de información del estéreo (2 canales → 2 guitarras, ambas extraídas).

**Conclusión:** el objetivo ("borrador editable multipista de alta calidad") está cumplido. El
test `test_techniques_bend_and_vibrato` se corrigió (bend realista ≥3 puntos); suite en 28 verdes.

> **Análisis detallado de calidad (escalas, pentatónicas, tónica, repetición, techo) en
> [`ANALISIS_CALIDAD.md`](ANALISIS_CALIDAD.md).** Hallazgo definitivo: el oficial es MÁS cromático
> (88.6% en escala) que nuestra transcripción (94%) → ninguna corrección por escala/tónica ayuda; la
> música real excede el prior. Lo que funciona = añadir información (estéreo); lo que no = limpiar/
> reorganizar lo transcrito.

---

## Propuestas de mejora — investigación web/literatura (2026-06-20)

Survey de foros, papers recientes y herramientas. **Hallazgo meta:** la literatura valida nuestra
arquitectura (TART, arXiv 2510.02597, es un pipeline audio→tab de 4 etapas idéntico) y explica
nuestros fracasos: todos los modelos buenos usan **DadaGP (incluye metal)**, no GuitarSet (acústico).
Las herramientas comerciales **no separan instrumentos** → nuestro Demucs+estéreo va por delante.

**Referencias clave:** TART (2510.02597) · MIDI-to-Tab/BART (2408.05024) · Fretting-Transformer
(2506.14223) · DadaGP corpus 26k tabs (2107.14653, github.com/dada-bots/dadaGP, MIT, acceso por
solicitud) · snap-to-scale (Scaler Detector) · ACR con LLM (2509.18700).

### Limpieza con teoría musical (🟢 barato, sin entrenar, medible) — RECOMENDADO empezar aquí
**TC-01 — Snap-to-scale / detección de tonalidad.** *Etapa 4c/5.* Detectar tonalidad
(Krumhansl-Schmuckler en `librosa`) y corregir/marcar notas fuera de escala como errores probables
de basic_pitch. Feature comercial real. Medible vs el oficial. **Top-1: barato y podría mover la
aguja de verdad** (a diferencia del dedup de octavas). 🟢
**TC-02 — Transcripción consciente de acordes.** Reconocer acorde por compás (ACR) y usarlo de
prior: conservar tonos del acorde, degradar no-tonos. Limpia sobre-transcripción. 🟡
**TC-03 — Afinaciones down-tuned.** ✅ *PARCIAL (manual hecho; auto pendiente/ambiguo).* Tabular
contenido de Eb en estándar da digitación toda mal (Sweet Child: acuerdo cuerda+traste **0%→59%**
en Eb). El chroma es invariante a la afinación; la digitación es lo que se LEE. **Hecho:**
afinaciones manuales en `to_tab.TUNINGS` (eb_standard, d_standard, drop_c) + CLI `--tuning`. **Auto
pendiente:** detectar la afinación desde audio es AMBIGUO (mismas alturas; el heurístico de
traste-medio no separa Eb de estándar). Posible vía futura: probar candidatas y elegir por
idiomática + contexto, o pedir al usuario (la sabe del tab oficial). 🟢

### Notación rítmica (🟠 patrón clave del metal)
**RHY-01 — Cuantización de tresillos / galope.** ✅ *HECHO (opt-in `--triplets`).* La cuantización
recta a semicorcheas no representaba tresillos; The Trooper usa **606 tresillos (3:2) = 21%** del
oficial (el galope). *Implementado:* rejilla de 48/compás (12 subdiv/beat) con tuplets GP
(`beat.duration.tuplet`), **opt-in** (default = rejilla recta, cero regresión). Claves del fix
(`to_gp`): (a) **sesgo hacia recto** (`straight_bias=8`) en el snap de onset → solo tresillo si el
onset está casi exacto (evita falsos por jitter); (b) **fin forzado a recto** + **duración = brecha
entre onsets** (la señal de tresillo es el onset, no la duración de nota suelta). Resultado en
Trooper: **569 tresillos en las 2 guitarras (vs 606 oficial, 94%)**; DTW sin cambio (chroma es
invariante al ritmo); modo recto idéntico (Back in Black 77.9% sin regresión). 33 tests verdes
(+3 nuevos). *Hecho: sesión 21 jun.*

### Priors de dominio correcto (🟡 arregla el desajuste GuitarSet→metal)
**MG-02 — Matriz de inhibición desde DadaGP-metal.** Reconstruir `models/inhibition.npz` (ver
`scripts/build_inhibition.py`) desde tabs de **metal** (DadaGP o colección GP propia) en vez de
GuitarSet acústico. El encoder de DadaGP es público (MIT). **No es entrenar, son estadísticas** de
dominio correcto. Ataca directo el hallazgo de que GuitarSet no transfiere. 🟡
**MG-03 — Fretting-Transformer / MIDI-to-Tab.** BART entrenado en DadaGP, "mejor jugabilidad y
acuerdo que el software tradicional" (= mejor que nuestro DP+inhibición). Encaja en el contrato
`list[Note]`/`TabNote`. **Parqueado hasta que liberen pesos** (mismo bloqueo que MG-01). 🟠

### Post-proceso con LLM (🟠 el plan permite LLM accesorio vía OpenRouter)
**LLM-01 — Etiquetado de secciones.** Nombrar Intro/Verso/Coro/Solo/Breakdown + marcadores de
sección en el GP. Una llamada barata, muy útil para navegar. 🟢
**LLM-02 — Pase "crítico musical".** Darle tab + contexto tonalidad/acordes; marca notas obviamente
erróneas como **sugerencias HITL** (no auto-aplica). Arriesgado (alucinación). 🟠
**LLM-03 — Simplificador de tabs.** Generar "versión fácil" (sin fantasmas, ritmos simplificados). 🟡

### Ensemble y multi-pass (🟡)
**EN-01 — Consenso de modelos.** Correr basic_pitch + mr_mt3 (ya rápido) y conservar notas en que
**ambos coinciden**; marcar discrepancias. Reduce espurias. 🟡
**EN-02 — Separación mid/side + por bandas.** Además de L/R, explotar canal *side* y sub-bandas para
recuperar más fuentes (extiende el truco estéreo que SÍ funcionó). 🟡

### HITL/UX — donde está el valor real (la auto-transcripción topa en ~84%) — RECOMENDADO
**UX-01 — Mapa de calor de confianza en el visor.** basic_pitch emite fuerza de activación por nota
→ colorear notas por confianza para arreglar primero lo peor. Convierte "84% preciso" en "aquí está
el 16% a revisar". **Top-3: mayor multiplicador real de productividad.** Requiere propagar
`confidence` en `Note` (≈ CH-03). 🟡
**UX-02 — Diff audio-original vs synth.** Resaltar regiones donde el synth más diverge del original
(= errores probables) para revisión dirigida. 🟡
**UX-03 — Prior por recuperación de tabs.** Para canciones famosas, alinear/validar contra tab
comunitaria existente (fallback a transcripción pura). 🟠
**UX-04 — "Arregla un riff una vez, propágalo a sus repeticiones".** *RF-07 (HITL) + structure.py.*
La detección de riffs repetidos FUNCIONA (34 clusters en MoP; ver `ANALISIS_CALIDAD.md` §5), pero
auto-aplicar consenso EMPEORA (borra variación legítima). El valor está en HITL: detectar grupos de
riffs repetidos y, cuando el usuario corrige uno, ofrecer **propagar la corrección a todas sus
instancias**. Combina lo que funciona (detección) con el lever real (revisión humana). Misma
detección alimenta el etiquetado de secciones (LLM-01) y mostrar estructura en el visor.
**Top recomendado actual.** Cimiento Python (`structure.py`) contenido; consumo UI después. 🟡

### Integración sidecar/UI (🟡 cerrar el gap CLI→app)
**SIDE-01 — Exponer score de banda + estructura por el sidecar y la UI.** Los flags
`--multi-instrument`, `--stereo-guitars`, `--vocals` y la detección de estructura
(`structure.json`) hoy son **solo CLI** (`server.py` no los pasa). Falta: añadirlos a
`POST /jobs` (`server.py` + `PipelineParams`), checkboxes en el wizard (`ui/`), y consumir
`structure.json` en el visor (cimiento de UX-04/etiquetado de secciones). 🟡

### Validación (🟢 robustez cross-género)
**VAL-01 — Probar más artistas/géneros de metal.** Solo validamos MoP. Harness listo
(`scripts/validate_corpus.py`): coloca pares (audio + tab oficial de **mySongBook**) en una
carpeta → reporta afinación/BPM/DTW/contenido por canción + media. Set de prueba recomendado
y metodología en [`VALIDACION_CORPUS.md`](VALIDACION_CORPUS.md). Hipótesis a confirmar: el
estéreo ayuda en proporción al paneo; el techo ~84% se mueve con densidad/calidad de mezcla.
**El usuario aporta los pares** (audio propio + tab oficial; copyright). 🟢

### Creativas / exploratorias (🟣)
**CR-01 — Huella de estilo de ejecución** (densidad palm-mute, tipo de vibrato).
**CR-02 — Estimación de dificultad + modo práctica** (pistas ralentizadas por sección).
**CR-03 — "Riff search"** (indexar riffs transcritos para encontrar canciones similares).

> **Top-3 por impacto/esfuerzo:** TC-01 (snap-to-scale) · MG-02 (inhibición DadaGP-metal) ·
> UX-01 (mapa de confianza). Patrón aprendido: lo que funciona es **añadir información real**
> (estéreo) o **priors de dominio correcto** (DadaGP-metal, teoría musical), no reorganizar lo ya
> transcrito (tempo/limpieza ciega fallaron).
