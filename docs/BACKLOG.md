# Backlog — Audio2Tab

Items priorizados con MoSCoW. Cada item indica el problema, la solución propuesta y la
etapa/componente del pipeline afectado.

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

**CH-02 — Mapa de tempo dinámico (vs. BPM estático)**
*Etapa 5 (Tab → Guitar Pro).* Piezas con rubato, acelerando/desacelerando (clásico, solos
expresivos) no mantienen un BPM robótico. Asumir un BPM global (F5) desalinea los compases
hacia la mitad de la canción.
*Solución:* extraer un mapa de tempo dinámico (beat tracker de `librosa`/`madmom`) e inyectar
cambios de tempo explícitos por compás en el `.gp5`, en lugar de un único número al inicio.
*Impacto:* 🟠 medio — reescribe la cuantización de `to_gp.py` (aislado a ese módulo). Hacerlo en
su propia iteración con test de regresión.

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
