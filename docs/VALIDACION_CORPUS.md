# Validación con más canciones (otros artistas / géneros de metal)

> Solo se ha validado con Master of Puppets. Para saber si los hallazgos (estéreo
> ayuda, techo ~84%, auto-detección de afinación/BPM) son **robustos**, hay que probar
> con un set que varíe las dimensiones que afectan al pipeline.

---

## 1. Fuentes oficiales de tablatura

- **[mySongBook](https://www.guitar-pro.com/tabs/genres/3-metal)** — catálogo **oficial** de
  Guitar Pro (6800 tabs, 1070 artistas, transcripciones profesionales licenciadas, sección
  de metal). Es la verdad de terreno recomendada (de aquí salen tabs como el MoP que ya
  tenemos). Se compran por score o por suscripción; **no se pueden editar** (copyright).
- **[GOAT dataset](https://github.com/JackJamesLoth/GOAT-Dataset)** (ISMIR 2025) — 5.9 h de
  guitarra eléctrica con **audio+tab pareados (formato Guitar Pro)**, abierto/descargable.
  Útil para evaluar las etapas audio→MIDI→tab en aislado, pero es **DI de una sola guitarra**
  (no mezcla de banda) → no ejercita separación/estéreo.
- **GuitarSet** (ya lo usamos en `bench/`) — acústico/limpio, no metal, pero sirve de
  regresión de la calidad de transcripción pura.

> ⚠️ El audio y las tabs oficiales son material con copyright; **el usuario aporta los pares
> (audio propio + tab oficial)**. El harness los procesa localmente.

---

## 2. Set de prueba recomendado (varía lo que importa al pipeline)

Elegido para estresar las variables que descubrimos que afectan la calidad: **paneo
estéreo, afinación, densidad/tempo, era de producción y polifonía (armonías a 2 guitarras)**.

| Subgénero | Canción de referencia | Qué estresa |
|-----------|----------------------|-------------|
| Thrash (base) | Metallica — *Master of Puppets* | E estándar, hard-pan, denso (baseline ya medido: ~84%) |
| Thrash/groove | Pantera — *Walk* | **Drop D**, groove, palm-mute pesado |
| Speed/thrash | Slayer — *Raining Blood* | caótico, tremolo, solos atonales (estresa cromatismo) |
| NWOBHM/power | Iron Maiden — *The Trooper* | **armonías a 2 guitarras** (prueba directa del estéreo), gallop |
| Death | Death — *Crystal Mountain* | técnico, afinación baja (C#), polifonía densa |
| Doom/clásico | Black Sabbath — *Iron Man* | lento/disperso, producción 70s analógica |
| Prog | Dream Theater / Opeth | compases impares, limpio+pesado, dinámica amplia |
| Moderno/djent | Periphery / Gojira | **drop bajo / 7-8 cuerdas**, producción moderna centrada (poco paneo) |

Razonamiento: si el estéreo ayuda **más** en Maiden (armonías reales L/R) y **menos** en
djent moderno (mezcla centrada), confirma la hipótesis. Si la auto-detección de afinación
acierta en Drop D / C# / 7 cuerdas, valida ese paso. Si el techo ~84% se sostiene en
thrash pero baja en black metal lo-fi, sabremos dónde flaquea la separación.

---

## 3. Cómo correr la validación

Coloca los pares en una carpeta (mismos nombres base) y corre el harness:

```
corpus/
  walk.mp3              walk.gp5
  the_trooper.mp3       the_trooper.gp4
  iron_man.mp3          iron_man.gp5
  ...
```

```bash
# estéreo (modo de producción, 2 guitarras)
python scripts/validate_corpus.py corpus/ --device cuda --out storage/reporte_estereo.md
# baseline mono (para medir el delta del estéreo por canción)
python scripts/validate_corpus.py corpus/ --device cuda --mono --out storage/reporte_mono.md
```

El harness (`scripts/validate_corpus.py`):
- Autodetecta las pistas de guitarra del oficial y de nuestra salida (por nombre).
- Corre el pipeline completo (Demucs + estéreo + transcripción) por canción.
- Reporta por canción: **afinación detectada, BPM, DTW, contenido, nº de notas ref/est**, y
  la **media agregada**. Comparar `reporte_estereo` vs `reporte_mono` da el aporte del estéreo.

Validado en MoP: `tuning=Mi(40) bpm=207 DTW=82.8% contenido=99.2%`.

---

## 4. Resultados medidos (21 jun 2026) — 6 canciones, 6 estilos

Cada canción `<base>.mp3` + `<base>.gp3` en `storage/corpus/` con un `corpus.json` que mapea
`{base: [pistas de guitarra del oficial]}` (la auto-detección por nombre falla en tabs sin
nombrar/con pistas de cuerda no-guitarra).

| Canción | Estilo | Afinación | DTW | Ventana | Contenido | Lever de notación |
|---------|--------|-----------|-----|---------|-----------|-------------------|
| Stairway to Heaven | Acústico/limpio | E | **84.5%** | **58%** | 99.4% | — (caso de éxito) |
| Master of Puppets | Thrash | E | 84% | — | 99% | (estéreo) |
| Sweet Child O' Mine | Rock | **Eb** | 79% | 49% | 98.6% | afinación Eb |
| Back in Black | Hard rock | E | 78% | 46% | 98.7% | tempo (half-time) |
| Killing in the Name | Funk-metal | **Drop D** | 72% | 41% | **99.6%** | Drop D + tempo inverso |
| The Trooper | NWOBHM gallop | E | 70% | 52% | 98.1% | tresillos (RHY-01) |

**Conclusiones (confirmadas con datos):**
1. **El contenido es siempre 98-99.6%** — el pipeline capta las notas correctas en TODO género.
2. **El DTW sube con material limpio/simple** (Stairway 84.5%, Killing-contenido 99.6%) y **baja
   con complejidad rítmica** (gallop/tresillos) o **mismatch de fuente** (tabs oficiales de versión
   más larga/condensada que el MP3). → **El techo lo marca el MATERIAL, no el pipeline.** Hipótesis
   confirmada.
3. **El estéreo SÍ aporta en harmonías reales** (The Trooper: 1 guitarra 66.6% → 2 guitarras 70.3%).
4. **Cada estilo reveló un lever de NOTACIÓN** (no de contenido). Entregados: tempo (PR #11),
   afinaciones Eb/D/Drop D/Drop C (PR #12). Pendiente: tresillos (RHY-01).
5. **La afinación NO se auto-detecta** de forma fiable desde audio (mismas alturas); selección
   manual `--tuning`. El **tempo** tiene ambigüedad de octava (BiB se sobre-doblaba, Killing se
   sobre-detecta a 172 vs 80) → `--bpm` override.

## 5. Sobre cuantización rítmica / mapa de tempo (análisis de tips externos)

Toda la maquinaria del "flujo profesional" (beat tracking + cuantización **relativa a beats** +
mapa de tempo dinámico) **ya está construida** (`preprocess.estimate_beats`,
`to_gp._make_to_slot`, `to_gp._write_tempo_map`) pero **apagada por defecto**. Medido (incluyendo
beats del **stem de batería**, no solo de la mezcla): en Back in Black el grid fijo gana (ventana
46.8%) y el beat-relativo empeora (42-45%).

**Causa:** el beat-tracker de **librosa no es lo bastante exacto** (jitter de ms) → cuantizar contra
sus beats es peor que una rejilla matemática limpia para tempo estable (la mayoría). El cuello de
botella es la **exactitud del beat-tracker**, no el enfoque. **Upgrade real: `madmom`** (beat/
downbeat tracking preciso) → desbloquearía el beat-relativo + mapa de tempo para canciones que
**aceleran** (Stairway, outro de SCO). Ver **CH-02**. El otro lever de notación rítmica es **RHY-01
(tresillos)**.
