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

## 4. Qué buscamos confirmar (hipótesis)

1. **El estéreo ayuda en proporción al paneo** (mucho en Maiden/thrash clásico; poco en
   djent moderno centrado).
2. **La auto-detección de afinación/BPM** acierta en drop tunings y 7-8 cuerdas.
3. **El techo ~84%** se sostiene en thrash y se mueve predeciblemente con la densidad y la
   calidad de la mezcla (peor en black metal lo-fi, mejor en producción limpia).
4. **Géneros menos cromáticos/densos** (doom clásico, hard rock) deberían dar **mejor** DTW
   que el metal denso → confirmaría que el techo es del material, no del pipeline.

> Cuando tengamos 5-8 canciones medidas, sabremos si generalizamos o si hay que ajustar por
> subgénero (p.ej. activar la matriz DadaGP-metal o la inhibición según el material).
