# Análisis de calidad de transcripción — hallazgos experimentales (2026-06-20)

> Bitácora razonada de los experimentos de calidad sobre Master of Puppets, con
> datos. Documenta **qué se probó, qué funcionó y por qué** — para que el equipo no
> repita callejones y entienda dónde está el techo real. Métrica principal: similitud
> chroma DTW vs el GP oficial (`scripts/compare_gp.py`).

---

## 1. Resumen ejecutivo

- **Baseline actual:** DTW **~84%** / contenido global **~99%** con 2 guitarras estéreo
  + basic_pitch. Es un buen "borrador editable".
- **Lo único que mejoró la fidelidad:** la **transcripción por canal estéreo** (recuperar
  las 2 guitarras paneadas), DTW 76%→84%. Funcionó porque **añade información real**.
- **Todo lo demás (auto-corrección) NO mejoró** y a menudo empeoró: tempo dinámico,
  limpieza de notas, snap-to-escala, matriz de inhibición de GuitarSet, consenso por
  repetición. Razón común: **intentan reorganizar/limpiar lo ya transcrito, no añaden
  información**, y la música real excede los priors.

**Conclusión:** estamos cerca del **techo práctico** de auto-transcripción para mezcla
densa de metal. El gap restante es **detalle irreducible** (cromatismo + variación) que
ningún prior automático puede *añadir*. El valor futuro está en (a) mejor modelo de
audio (bloqueado, sin pesos — ver `MODELO_GUITARRA.md`), o (b) **acelerar al humano**
(HITL), no en seguir auto-corrigiendo.

---

## 2. Qué funcionó

### Transcripción por canal estéreo (mergeado, PR #2)
En metal las rítmicas van hard-paneadas L/R (MoP: correlación L/R = 0.555). Demucs
**colapsa** ese paneo en su stem `other` (queda mono). Separando **cada canal del original
estéreo por separado** se recuperan las 2 guitarras → **DTW 76%→84%**, notas 2640→5577
(oficial: 6663). Es el patrón que funciona: **añadir información de la fuente.**

---

## 3. Qué NO funcionó (con datos) — no reintentar igual

| Experimento | Resultado | Por qué falló |
|-------------|-----------|---------------|
| **Tempo dinámico** (beat-relativo + mapa de tempo) | DTW 76.0 vs 76.2 | librosa no da tempo dinámico real (pulso ~constante); el ritmo no era el cuello de botella. Necesitaría madmom. |
| **Limpieza de notas** (octavas dobladas, notas cortas) | +0.2 / −0.7 | El metric chroma (ponderado por duración + clase) es casi insensible; el dedup de octavas quita notas reales. |
| **Snap-to-escala** (diatónica) | 76.1→75.9 (snap), 75.4 (drop) | Ver §4: la música real es más cromática que nuestra transcripción. |
| **Matriz inhibición GuitarSet** | acuerdo digitación 62.7→62.9% | GuitarSet (acústico) no transfiere a las posiciones graves del metal; la heurística ya las captura. |
| **Consenso por repetición** (aplanar riffs) | 76.2→75.3 | Ver §5: el oficial conserva variaciones legítimas que el consenso borra. |
| **Consenso gentil** (quitar outliers no repetidos) | 76.2→75.0 | Igual: las notas "no repetidas" incluyen variación real. |

---

## 4. Análisis de escalas (pentatónica / modal / tónica) — el hallazgo definitivo

Pregunta: ¿considerar pentatónicas, escalas adicionales y la tónica que dicta los patrones
cambia el resultado? Se ajustaron **9 escalas** ancladas a la tónica detectada (pentatónica
menor/mayor, blues menor, menor natural, frigia, frigia dominante, menor armónica, dórica,
mayor), ponderadas por duración, sobre **nuestra transcripción** y el **oficial** (verdad).

```
=== NUESTRA | tónica E (correcta) ===     === OFICIAL | tónica E (correcta) ===
   94.0%  menor natural (eólica)              88.6%  menor natural (eólica)
   86.4%  frigia                              84.6%  dórica
   85.4%  menor armónica                      82.9%  menor armónica
```

Hallazgos:
1. **Tónica (E) y escala (menor natural) se detectan bien** en ambos. La **pentatónica NO
   domina** — los riffs usan la escala menor completa (2ª/6ª grados), por eso ni aparece en
   el top. (Detectar pentatónica/modal está bien hecho; simplemente no es lo que dicta MoP.)
2. **Dato decisivo:** el **oficial está solo al 88.6% en escala** → **el 11.4% de sus notas
   son cromáticas/fuera de escala intencionales**. El metal real **excede la escala a
   propósito**.
3. **Nuestra transcripción está MÁS en escala (94%) que el oficial (88.6%)** — somos *más
   diatónicos que la canción real*.

**Por eso snap-to-escala empuja al revés:** corregir nuestro ~6% fuera de escala nos haría
aún más diatónicos, alejándonos del 88.6% cromático del oficial. **La tónica/escala no es el
lever porque la música real va por delante de la escala.**

---

## 5. Detección de patrones / consenso por repetición — funciona para detectar, no para corregir

La idea (el metal repite riffs; promediar repeticiones cancela errores aleatorios) es del
tipo correcto. La **detección SÍ funciona**: con emparejado tolerante (±1 slot) se hallaron
**34 clusters de riffs repetidos** (tamaños 18, 9, 7…). Pero **auto-aplicar el consenso
empeora** (76.2→75.3 aplanando; →75.0 quitando outliers): el oficial **conserva las
variaciones legítimas entre repeticiones** (fills, notas fantasma reales), y el consenso las
borra.

**Redirección de valor:** la detección de repetición es oro **para HITL**, no para
auto-corregir → *"arregla un riff una vez y propágalo a sus N repeticiones"* (ver
propuesta abajo). Usa lo que funciona (detección) donde hay valor (revisión humana).

---

## 6. El patrón profundo (por qué todo converge)

Probado por escala, pentatónica, tónica, repetición y limpieza: la transcripción ya captura
fielmente el **núcleo** (escala menor + riffs repetidos). El **gap restante es justo el
detalle que excede cualquier prior**: cromatismo intencional (supera la escala) + variación
entre repeticiones (supera el patrón). **Ningún prior automático puede *añadir* ese detalle**
— solo un mejor modelo de audio o el oído humano.

Lo que funciona = **añadir información** (estéreo) o **priors de dominio correcto**. Lo que
no = **reorganizar/limpiar lo ya transcrito**.

---

## 7. Acción recomendada

1. **HITL "fix once, apply everywhere"** (combina detección de repetición ✅ + el lever real
   HITL): detectar grupos de riffs repetidos y, cuando el usuario corrige uno, ofrecer
   propagar la corrección a todas sus instancias. → módulo `structure.py` + UI.
2. **Mapa de confianza en el visor** (UX-01): colorear notas por confianza para revisar
   primero lo peor.
3. **Modelo específico de guitarra** (MG-01): parqueado hasta que liberen pesos; sería el
   único lever de fidelidad de contenido que queda.

> Reglas para futuros experimentos de calidad: (a) medir SIEMPRE vs el GP oficial con
> `compare_gp.py`, no asumir; (b) preferir lo que **añade información**; (c) desconfiar de
> auto-correcciones basadas en priors — la música real suele exceder el prior.
