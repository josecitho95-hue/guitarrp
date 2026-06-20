const fs = require("fs");
const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  Header, Footer, AlignmentType, LevelFormat, HeadingLevel, BorderStyle,
  WidthType, ShadingType, PageNumber, PageBreak, TableOfContents, TabStopType,
  TabStopPosition,
} = require("docx");

const CONTENT_W = 9360;
const border = { style: BorderStyle.SINGLE, size: 1, color: "BBBBBB" };
const borders = { top: border, bottom: border, left: border, right: border };
const HEAD_FILL = "1F4E79";
const SUB_FILL = "E7EEF7";

function cell(text, w, opts = {}) {
  const runs = Array.isArray(text) ? text : [new TextRun({ text: String(text), bold: opts.bold, color: opts.color, size: opts.size || 19 })];
  return new TableCell({
    borders,
    width: { size: w, type: WidthType.DXA },
    shading: opts.fill ? { fill: opts.fill, type: ShadingType.CLEAR } : undefined,
    margins: { top: 55, bottom: 55, left: 110, right: 110 },
    verticalAlign: "center",
    children: [new Paragraph({ children: runs, spacing: { after: 0 } })],
  });
}
function headerRow(labels, widths) {
  return new TableRow({ tableHeader: true, children: labels.map((l, i) => cell([new TextRun({ text: l, bold: true, color: "FFFFFF", size: 19 })], widths[i], { fill: HEAD_FILL })) });
}
function table(widths, headerLabels, rows) {
  const trs = [headerRow(headerLabels, widths)];
  rows.forEach((r) => trs.push(new TableRow({ children: r.map((c, i) => cell(c, widths[i])) })));
  return new Table({ width: { size: CONTENT_W, type: WidthType.DXA }, columnWidths: widths, rows: trs });
}
// Requirement card: label/value rows, 2 cols
function reqCard(id, title, rows) {
  const W1 = 2000, W2 = 7360;
  const trs = [new TableRow({ tableHeader: true, children: [
    new TableCell({ borders, width: { size: CONTENT_W, type: WidthType.DXA }, columnSpan: 2, shading: { fill: HEAD_FILL, type: ShadingType.CLEAR }, margins: { top: 55, bottom: 55, left: 110, right: 110 }, children: [new Paragraph({ children: [new TextRun({ text: `${id} — ${title}`, bold: true, color: "FFFFFF", size: 20 })] })] }),
  ] })];
  rows.forEach(([k, v]) => trs.push(new TableRow({ children: [
    cell([new TextRun({ text: k, bold: true, size: 19 })], W1, { fill: SUB_FILL }),
    cell(v, W2),
  ] })));
  return new Table({ width: { size: CONTENT_W, type: WidthType.DXA }, columnWidths: [W1, W2], rows: trs });
}
function h1(t) { return new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun(t)] }); }
function h2(t) { return new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun(t)] }); }
function p(t, opts = {}) { return new Paragraph({ spacing: { after: 120 }, children: parseRuns(t, opts) }); }
function bullet(t) { return new Paragraph({ numbering: { reference: "bul", level: 0 }, children: parseRuns(t) }); }
function spacer() { return new Paragraph({ children: [new TextRun("")], spacing: { after: 70 } }); }
function parseRuns(t, base = {}) {
  return t.split(/(\*\*[^*]+\*\*)/g).filter(Boolean).map((s) =>
    s.startsWith("**") && s.endsWith("**") ? new TextRun({ text: s.slice(2, -2), bold: true, ...base }) : new TextRun({ text: s, ...base }));
}
const mono = (t) => new TextRun({ text: t, font: "Consolas", size: 19 });

const doc = new Document({
  creator: "Audio2Tab",
  title: "Software Requirements Specification — Audio2Tab",
  styles: {
    default: { document: { run: { font: "Calibri", size: 22 } } },
    paragraphStyles: [
      { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 30, bold: true, color: "1F4E79", font: "Calibri" },
        paragraph: { spacing: { before: 280, after: 140 }, outlineLevel: 0, border: { bottom: { style: BorderStyle.SINGLE, size: 6, color: "1F4E79", space: 4 } } } },
      { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 24, bold: true, color: "2E75B6", font: "Calibri" },
        paragraph: { spacing: { before: 200, after: 90 }, outlineLevel: 1 } },
    ],
  },
  numbering: { config: [{ reference: "bul", levels: [{ level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 540, hanging: 280 } } } }] }] },
  sections: [{
    properties: { page: { size: { width: 12240, height: 15840 }, margin: { top: 1440, right: 1440, bottom: 1440, left: 1440 } } },
    headers: { default: new Header({ children: [new Paragraph({ alignment: AlignmentType.RIGHT, children: [new TextRun({ text: "Audio2Tab — SRS", color: "888888", size: 16 })] })] }) },
    footers: { default: new Footer({ children: [new Paragraph({ children: [new TextRun({ text: "Especificación de Requisitos de Software (SRS) — uso personal", color: "888888", size: 16 }), new TextRun({ text: "\t", size: 16 }), new TextRun({ text: "Pág. ", color: "888888", size: 16 }), new TextRun({ children: [PageNumber.CURRENT], color: "888888", size: 16 })], tabStops: [{ type: TabStopType.RIGHT, position: TabStopPosition.MAX }] })] }) },
    children: [
      // Cover
      new Paragraph({ spacing: { before: 1700, after: 0 }, alignment: AlignmentType.CENTER, children: [new TextRun({ text: "Audio2Tab", bold: true, size: 64, color: "1F4E79" })] }),
      new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 80 }, children: [new TextRun({ text: "Sistema de Transcripción de Audio a Tablaturas de Guitarra", size: 28, color: "2E75B6" })] }),
      new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 380 }, children: [new TextRun({ text: "Especificación de Requisitos de Software (SRS)", size: 26, bold: true })] }),
      new Paragraph({ alignment: AlignmentType.CENTER, children: [new TextRun({ text: "Conforme a la estructura IEEE 830 / ISO-29148", size: 20, italics: true, color: "666666" })] }),
      new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 200 }, children: [new TextRun({ text: "Versión 1.0  ·  20 de junio de 2026", size: 22 })] }),
      new Paragraph({ children: [new PageBreak()] }),

      new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun("Tabla de contenido")] }),
      new TableOfContents("Tabla de contenido", { hyperlink: true, headingStyleRange: "1-2" }),
      new Paragraph({ children: [new PageBreak()] }),

      // 1. Introducción
      h1("1. Introducción"),
      h2("1.1 Propósito"),
      p("Este documento especifica los requisitos funcionales y no funcionales del sistema Audio2Tab, una aplicación de escritorio que transcribe audio de guitarra a tablatura en formato Guitar Pro. Está dirigido al desarrollo y verificación del producto en su versión de uso personal."),
      h2("1.2 Alcance"),
      p("Audio2Tab recibe un archivo de audio (MP3/WAV) de una canción completa, aísla la guitarra, transcribe las notas, asigna una digitación físicamente tocable, marca técnicas expresivas y produce un archivo GP5/GP4/GP3. Incluye un visor con reproducción y un flujo de reprocesado por secciones (human-in-the-loop). Se ejecuta localmente; no entrena modelos; no es multiusuario."),
      h2("1.3 Definiciones, acrónimos y abreviaturas"),
      table([2300, 7060], ["Término", "Definición"], [
        ["Tablatura (tab)", "Notación de guitarra que indica cuerda y traste a tocar."],
        ["Stem", "Pista de un instrumento aislada de una mezcla."],
        ["MIDI", "Representación simbólica de notas (altura, inicio, duración, velocidad)."],
        ["GP3/GP4/GP5", "Formatos de archivo de Guitar Pro."],
        ["F1-score", "Media armónica de precisión y exhaustividad; métrica de calidad de transcripción."],
        ["VRAM", "Memoria de la tarjeta gráfica (GPU)."],
        ["HITL", "Human-in-the-loop: revisión/corrección humana dentro del flujo."],
        ["HOPO", "Hammer-on / pull-off (técnicas de ligado)."],
        ["Matriz de inhibición", "Estructura que codifica qué combinaciones cuerda/traste son físicamente tocables."],
        ["Chunking", "Procesar el audio por segmentos para limitar el uso de VRAM."],
        ["Sidecar", "Proceso backend (Python) lanzado y gestionado por la app de escritorio."],
      ]),
      spacer(),
      h2("1.4 Referencias"),
      bullet("Plan de arquitectura Audio2Tab (documento base aprobado, 2026-06-20)."),
      bullet("Demucs; YourMT3+ (arXiv:2407.04822); High-Resolution Guitar Transcription (arXiv:2402.15258)."),
      bullet("Fretting-Transformer (arXiv:2506.14223) y open-fret; guitar-transcription-with-inhibition (matriz de inhibición)."),
      bullet("PyGuitarPro (lectura/escritura GP3/GP4/GP5); alphaTab (render y reproducción); Tauri."),
      bullet("Datasets de evaluación: GuitarSet, GAPS, GOAT, DadaGP, Guitar-TECHS."),
      new Paragraph({ children: [new PageBreak()] }),

      // 2. Descripción general
      h1("2. Descripción general"),
      h2("2.1 Perspectiva del producto"),
      p("Aplicación de escritorio autocontenida compuesta por un shell Tauri (Rust + webview) y un sidecar Python (FastAPI local) que ejecuta un pipeline modular de IA sobre la GPU/CPU del usuario. Una cola local en proceso con estado en SQLite gestiona los trabajos; no se usan Docker, Redis ni Celery."),
      h2("2.2 Funciones del producto (resumen)"),
      bullet("Importar audio y generar tablatura editable."),
      bullet("Garantizar digitaciones físicamente tocables (matriz de inhibición)."),
      bullet("Marcar técnicas expresivas por niveles de confiabilidad."),
      bullet("Revisar, reproducir y reprocesar por secciones hasta el resultado final."),
      bullet("Exportar a GP5/GP4/GP3."),
      h2("2.3 Características del usuario"),
      p("Único usuario: guitarrista con conocimientos musicales, capaz de revisar y corregir una tablatura. No requiere conocimientos técnicos de IA ni de línea de comandos."),
      h2("2.4 Restricciones"),
      bullet("Hardware objetivo: RTX 4070 (8 GB VRAM), i9-13980HX (24C/32T), 24 GB RAM; SO Windows."),
      bullet("8 GB de VRAM como recurso escaso: obliga a chunking, fp16 y carga/descarga secuencial de modelos."),
      bullet("Ejecución local; sin entrenamiento de modelos."),
      bullet("Uso estrictamente personal (sin distribución): licencias GPL/LGPL tratadas como no restrictivas."),
      h2("2.5 Supuestos y dependencias"),
      bullet("Drivers NVIDIA/CUDA del sistema instalados y operativos."),
      bullet("Disponibilidad de los pesos de los modelos open-source para descarga en el primer uso."),
      bullet("FFmpeg embebido en la aplicación."),
      new Paragraph({ children: [new PageBreak()] }),

      // 3. Requisitos funcionales
      h1("3. Requisitos funcionales"),
      p("Cada requisito indica entrada, proceso, salida y criterio de aceptación. Prioridad MoSCoW."),
      reqCard("RF-01 (F1)", "Importar audio y crear trabajo", [
        ["Prioridad", "Must"],
        ["Entrada", "Archivo MP3 o WAV seleccionado o arrastrado por el usuario."],
        ["Proceso", "Validar formato/duración, registrar el trabajo (job) con estado inicial en SQLite y encolarlo."],
        ["Salida", "Identificador de job y estado «queued»."],
        ["Criterio", "Un MP3 válido genera un job consultable; un formato no soportado produce un error claro."],
      ]),
      spacer(),
      reqCard("RF-02 (F2)", "Procesamiento asíncrono con estados", [
        ["Prioridad", "Must"],
        ["Entrada", "Job encolado."],
        ["Proceso", "Ejecutar el pipeline (preproceso → separación → transcripción → digitación → técnicas → export) en segundo plano, actualizando el estado."],
        ["Salida", "Transiciones de estado: queued → separating → transcribing → tabbing → done | error."],
        ["Criterio", "El estado refleja la etapa real; los errores dejan el job en «error» con mensaje."],
      ]),
      spacer(),
      reqCard("RF-03 (F3)", "Consultar progreso", [
        ["Prioridad", "Must"],
        ["Entrada", "Identificador de job."],
        ["Proceso", "Exponer progreso por SSE o polling."],
        ["Salida", "Estado y porcentaje/etapa actual."],
        ["Criterio", "La UI muestra avance en vivo hasta la finalización."],
      ]),
      spacer(),
      reqCard("RF-04 (F4)", "Descargar la tablatura", [
        ["Prioridad", "Must"],
        ["Entrada", "Job en estado «done» y formato elegido (GP5/GP4/GP3)."],
        ["Proceso", "Serializar el modelo de partitura con PyGuitarPro al formato solicitado."],
        ["Salida", "Archivo .gp5/.gp4/.gp3 descargable."],
        ["Criterio", "El archivo abre sin errores en Guitar Pro/TuxGuitar."],
      ]),
      spacer(),
      reqCard("RF-05 (F5)", "Parámetros de transcripción", [
        ["Prioridad", "Must"],
        ["Entrada", "Afinación (estándar/Drop D), capo, BPM (auto/manual), modelo (High-Res/YourMT3+), formato de salida y ubicación de Demucs (GPU/CPU)."],
        ["Proceso", "Aplicar parámetros al pipeline del job."],
        ["Salida", "Resultado coherente con los parámetros elegidos."],
        ["Criterio", "Cambiar un parámetro altera el resultado de forma observable y consistente."],
      ]),
      spacer(),
      reqCard("RF-06 (F6)", "Persistir artefactos intermedios", [
        ["Prioridad", "Must"],
        ["Entrada", "Job en ejecución."],
        ["Proceso", "Guardar stem WAV, MIDI y tab JSON en la carpeta de datos del job."],
        ["Salida", "Artefactos inspeccionables y reutilizables para reprocesado."],
        ["Criterio", "Cada etapa deja su artefacto; permiten depurar y reanudar."],
      ]),
      spacer(),
      reqCard("RF-07 (F7)", "Human-in-the-loop: visor y reprocesado por región", [
        ["Prioridad", "Must"],
        ["Entrada", "Job «done»; selección de compases por el usuario; parámetros alternativos."],
        ["Proceso", "Renderizar y reproducir la tab (alphaTab) con cursor; reproducir el MP3 original sincronizado; recortar la región seleccionada, reprocesarla y empalmarla en el modelo en memoria; iterar."],
        ["Salida", "Tablatura actualizada por secciones; confirmación/descartado de técnicas Tier 3."],
        ["Criterio", "Reprocesar una sección actualiza solo esa parte sin romper compases vecinos ni el tempo global."],
      ]),
      spacer(),
      reqCard("RF-08 (F8)", "Marcado de técnicas expresivas", [
        ["Prioridad", "Should"],
        ["Entrada", "Notas transcritas con contorno de pitch y onsets."],
        ["Proceso", "Tier 1 (auto): HOPO, slides, bends, vibrato; Tier 2 (clasificador): palm mute, armónicos; Tier 3 (heurística): tapping, sweep como sugerencia."],
        ["Salida", "Técnicas escritas como NoteEffect en la tab (degradadas si el formato es GP3)."],
        ["Criterio", "Técnicas Tier 1 presentes con alta confianza aparecen marcadas; Tier 3 nunca se impone."],
      ]),
      spacer(),
      reqCard("RF-09 (F9)", "Procesamiento por lotes y fallback a nube (post-MVP)", [
        ["Prioridad", "Could"],
        ["Entrada", "Conjunto de archivos o un modelo que no cabe en 8 GB VRAM."],
        ["Proceso", "CLI por lotes aprovechando CPU multinúcleo; opción de reenviar una etapa a GPU de nube por uso."],
        ["Salida", "Múltiples tablaturas; o etapa resuelta en nube."],
        ["Criterio", "El lote procesa varios archivos; el fallback a nube está desactivado por defecto."],
      ]),
      new Paragraph({ children: [new PageBreak()] }),

      // 4. Requisitos no funcionales
      h1("4. Requisitos no funcionales"),
      table([1300, 2600, 5460], ["ID", "Categoría", "Requisito"], [
        ["RNF-01", "Rendimiento", "Una canción de ~4 min debe procesarse en pocos minutos en la RTX 4070, usando chunking para no exceder 8 GB de VRAM."],
        ["RNF-02", "Uso de recursos", "El sistema debe mantener un solo modelo pesado en VRAM a la vez y delegar al CPU (32 hilos) las etapas que no requieren GPU."],
        ["RNF-03", "Fiabilidad", "Un fallo en una etapa deja el job en «error» con mensaje y conserva los artefactos previos; no debe corromper otros jobs."],
        ["RNF-04", "Usabilidad", "Flujo principal (importar → procesar → revisar → exportar) sin conocimientos técnicos; mensajes de error comprensibles."],
        ["RNF-05", "Portabilidad / Despliegue", "Distribuirse como app Tauri autocontenida; instalar y ejecutar sin instalar Python, CUDA toolkit ni Docker por separado."],
        ["RNF-06", "Mantenibilidad", "Cada etapa del pipeline es un módulo independiente y sustituible; los dos backbones (Path A/B) son intercambiables."],
        ["RNF-07", "Tamaño del instalador", "El instalador puede ser grande (~5–8 GB por torch+CUDA); los pesos de modelos se descargan en el primer uso para no inflarlo más."],
        ["RNF-08", "Calidad de transcripción", "Objetivo de referencia F1 ~85–88% sobre guitarra limpia (benchmark interno); en mezcla se acepta menor, con revisión humana."],
        ["RNF-09", "Seguridad / Privacidad", "Procesamiento 100% local por defecto; ningún audio se envía a servicios externos salvo que el usuario active explícitamente el fallback a nube."],
      ]),
      spacer(),

      // 5. Requisitos de interfaz
      h1("5. Requisitos de interfaz"),
      h2("5.1 Interfaces de software (API local Tauri ↔ sidecar)"),
      table([3400, 1400, 4560], ["Endpoint", "Método", "Descripción"], [
        ["/jobs", "POST", "Crea un job a partir de un audio y parámetros; devuelve job_id."],
        ["/jobs/{id}", "GET", "Estado y progreso del job (SSE para progreso en vivo)."],
        ["/jobs/{id}/result", "GET", "Descarga la tablatura en el formato solicitado."],
        ["/jobs/{id}/reprocess", "POST", "Reprocesa un rango de compases con parámetros alternativos y lo empalma."],
      ]),
      spacer(),
      h2("5.2 Interfaces de archivos"),
      bullet("Entrada: MP3, WAV."),
      bullet("Intermedios: WAV (stem), MID (MIDI), JSON (tab/estado)."),
      bullet("Salida: GP5 (por defecto), GP4, GP3."),
      h2("5.3 Interfaces de hardware"),
      bullet("GPU NVIDIA con CUDA (RTX 4070, 8 GB) para separación y transcripción."),
      bullet("CPU multinúcleo (i9-13980HX) para preproceso, digitación, inhibición, técnicas y pipelining CPU↔GPU."),
      new Paragraph({ children: [new PageBreak()] }),

      // 6. Modelos del sistema
      h1("6. Modelos del sistema"),
      h2("6.1 Pipeline de procesamiento (etapas)"),
      table([700, 2600, 4060, 2000], ["#", "Etapa", "Componente", "Cómputo"], [
        ["1", "Preproceso", "ffmpeg + librosa", "CPU"],
        ["2", "Separación de fuentes", "Demucs (htdemucs / htdemucs_ft)", "GPU (o CPU)"],
        ["3", "Audio → MIDI", "High-Res Guitar Transcription / YourMT3+", "GPU"],
        ["4", "MIDI → Tab (digitación)", "Fretting-Transformer / open-fret (+ fallback DP)", "CPU/GPU ligero"],
        ["4b", "Restricción física", "Matriz de inhibición", "CPU"],
        ["4c", "Detección de técnicas", "Contorno de pitch + clasificador de timbre", "CPU"],
        ["5", "Tab → Guitar Pro", "PyGuitarPro (NoteEffect)", "CPU"],
      ]),
      spacer(),
      h2("6.2 Estados del trabajo (job)"),
      p("queued → separating → transcribing → tabbing → done. En cualquier etapa puede pasar a error. Desde done puede entrar en reprocessing (por región) y volver a done.", {}),
      h2("6.3 Secuencia principal (camino feliz)"),
      bullet("El usuario importa un MP3 (RF-01) → se crea y encola el job."),
      bullet("El worker ejecuta las etapas 1–5 actualizando el estado (RF-02, RF-03)."),
      bullet("El usuario revisa en el visor, reproduce y compara (RF-07)."),
      bullet("Si una sección falla, la selecciona y reprocesa (RF-07) hasta convencer."),
      bullet("Exporta a GP5/GP4/GP3 (RF-04)."),
      new Paragraph({ children: [new PageBreak()] }),

      // 7. Apéndices
      h1("7. Apéndices"),
      h2("7.1 Matriz de trazabilidad (Requisito de negocio ↔ Requisito funcional)"),
      table([2200, 7160], ["Req. negocio (BRD)", "Requisitos funcionales (SRS)"], [
        ["BR-01", "RF-01, RF-02, RF-04"],
        ["BR-02", "RF-02 (etapa 4b — matriz de inhibición)"],
        ["BR-03", "RF-07 (visor + reproducción)"],
        ["BR-04", "RF-07 (reprocesado por región)"],
        ["BR-05", "RF-04 (export GP5/GP4/GP3)"],
        ["BR-06", "RNF-05, RNF-07 (app autocontenida)"],
        ["BR-07", "RF-08 (técnicas Tier 1/2)"],
        ["BR-08", "RNF-01, RNF-02 (rendimiento, GPU+CPU)"],
        ["BR-09", "RF-05 (selección de modelo)"],
        ["BR-10", "RF-09 (lote)"],
      ]),
      spacer(),
      h2("7.2 Glosario ampliado"),
      bullet("**Path A (modular):** separación → audio→MIDI → MIDI→tab → GP. Más flexible; acumula error entre etapas."),
      bullet("**Path B (directo):** separación → CRNN audio→tab → GP. Menos etapas; entrenado en acústica solista."),
      bullet("**Tier 1/2/3 de técnicas:** niveles de confiabilidad de detección (auto / clasificador / sugerencia)."),
      spacer(),
      p("Fin del documento — SRS v1.0.", { italics: true, color: "888888" }),
    ],
  }],
});

Packer.toBuffer(doc).then((buf) => {
  fs.writeFileSync("docs/SRS.docx", buf);
  console.log("SRS.docx escrito:", buf.length, "bytes");
});
