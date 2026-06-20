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
const SUB_FILL = "D5E1F0";

function cell(text, w, opts = {}) {
  const runs = Array.isArray(text) ? text : [new TextRun({ text: String(text), bold: opts.bold, color: opts.color, size: opts.size || 20 })];
  return new TableCell({
    borders,
    width: { size: w, type: WidthType.DXA },
    shading: opts.fill ? { fill: opts.fill, type: ShadingType.CLEAR } : undefined,
    margins: { top: 60, bottom: 60, left: 110, right: 110 },
    verticalAlign: "center",
    children: [new Paragraph({ children: runs, spacing: { after: 0 } })],
  });
}

function headerRow(labels, widths) {
  return new TableRow({
    tableHeader: true,
    children: labels.map((l, i) => cell([new TextRun({ text: l, bold: true, color: "FFFFFF", size: 20 })], widths[i], { fill: HEAD_FILL })),
  });
}

function table(widths, headerLabels, rows) {
  const trs = [headerRow(headerLabels, widths)];
  rows.forEach((r) => {
    trs.push(new TableRow({ children: r.map((c, i) => cell(c, widths[i])) }));
  });
  return new Table({ width: { size: CONTENT_W, type: WidthType.DXA }, columnWidths: widths, rows: trs });
}

function h1(t) { return new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun(t)] }); }
function h2(t) { return new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun(t)] }); }
function p(t, opts = {}) { return new Paragraph({ spacing: { after: 120 }, children: [new TextRun({ text: t, ...opts })] }); }
function bullet(t) { return new Paragraph({ numbering: { reference: "bul", level: 0 }, children: parseRuns(t) }); }
function spacer() { return new Paragraph({ children: [new TextRun("")], spacing: { after: 80 } }); }

// minimal **bold** parser
function parseRuns(t) {
  const parts = t.split(/(\*\*[^*]+\*\*)/g).filter(Boolean);
  return parts.map((s) => s.startsWith("**") && s.endsWith("**")
    ? new TextRun({ text: s.slice(2, -2), bold: true })
    : new TextRun({ text: s }));
}

const doc = new Document({
  creator: "Audio2Tab",
  title: "Business Requirements Document — Audio2Tab",
  styles: {
    default: { document: { run: { font: "Calibri", size: 22 } } },
    paragraphStyles: [
      { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 30, bold: true, color: "1F4E79", font: "Calibri" },
        paragraph: { spacing: { before: 280, after: 140 }, outlineLevel: 0, border: { bottom: { style: BorderStyle.SINGLE, size: 6, color: "1F4E79", space: 4 } } } },
      { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 25, bold: true, color: "2E75B6", font: "Calibri" },
        paragraph: { spacing: { before: 200, after: 100 }, outlineLevel: 1 } },
    ],
  },
  numbering: {
    config: [
      { reference: "bul", levels: [{ level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 540, hanging: 280 } } } }] },
    ],
  },
  sections: [{
    properties: { page: { size: { width: 12240, height: 15840 }, margin: { top: 1440, right: 1440, bottom: 1440, left: 1440 } } },
    headers: { default: new Header({ children: [new Paragraph({ alignment: AlignmentType.RIGHT, children: [new TextRun({ text: "Audio2Tab — BRD", color: "888888", size: 16 })] })] }) },
    footers: { default: new Footer({ children: [new Paragraph({ children: [new TextRun({ text: "Documento de Requisitos de Negocio (BRD) — Confidencial · uso personal", color: "888888", size: 16 }), new TextRun({ text: "\t", size: 16 }), new TextRun({ text: "Pág. ", color: "888888", size: 16 }), new TextRun({ children: [PageNumber.CURRENT], color: "888888", size: 16 })], tabStops: [{ type: TabStopType.RIGHT, position: TabStopPosition.MAX }] })] }) },
    children: [
      // Cover
      new Paragraph({ spacing: { before: 1800, after: 0 }, alignment: AlignmentType.CENTER, children: [new TextRun({ text: "Audio2Tab", bold: true, size: 64, color: "1F4E79" })] }),
      new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 80 }, children: [new TextRun({ text: "Sistema de Transcripción de Audio a Tablaturas de Guitarra", size: 30, color: "2E75B6" })] }),
      new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 400 }, children: [new TextRun({ text: "Documento de Requisitos de Negocio (BRD)", size: 26, bold: true })] }),
      new Paragraph({ alignment: AlignmentType.CENTER, children: [new TextRun({ text: "Versión 1.0", size: 22 })] }),
      new Paragraph({ alignment: AlignmentType.CENTER, children: [new TextRun({ text: "20 de junio de 2026", size: 22 })] }),
      new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 600 }, children: [new TextRun({ text: "Autor: José C.  ·  Uso personal (sin distribución ni comercialización)", size: 20, color: "666666" })] }),
      new Paragraph({ children: [new PageBreak()] }),

      // TOC
      new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun("Tabla de contenido")] }),
      new TableOfContents("Tabla de contenido", { hyperlink: true, headingStyleRange: "1-2" }),
      new Paragraph({ children: [new PageBreak()] }),

      // Control de versiones
      h1("Control de versiones"),
      table([1400, 2000, 3200, 2760], ["Versión", "Fecha", "Descripción", "Autor"], [
        ["1.0", "2026-06-20", "Versión inicial derivada del plan de arquitectura aprobado.", "José C. / Claude"],
      ]),
      spacer(),

      // 1. Resumen ejecutivo
      h1("1. Resumen ejecutivo"),
      p("Audio2Tab es una aplicación de escritorio de uso personal que convierte un archivo de audio (MP3/WAV de una canción completa) en una tablatura de guitarra editable en formato Guitar Pro (GP5, con exportación opcional a GP4/GP3). El sistema automatiza un proceso que hoy se realiza a mano y que consume horas por canción."),
      p("La solución se apoya en un pipeline modular de modelos de inteligencia artificial open-source de estado del arte (separación de fuentes, transcripción audio→MIDI, asignación de digitación y marcado de técnicas), ejecutados localmente sobre el hardware del usuario (GPU NVIDIA RTX 4070 + CPU Intel i9-13980HX). No se entrenan modelos nuevos: la calidad proviene de seleccionar el mejor componente por etapa y de un flujo de revisión humana (human-in-the-loop)."),
      p("El objetivo no es una transcripción perfecta —algo que ninguna herramienta, ni comercial, logra hoy en guitarra polifónica desde una mezcla— sino un borrador de alta calidad, editable y físicamente tocable, que reduzca drásticamente el tiempo de transcripción manual.", { italics: true }),

      // 2. Objetivos
      h1("2. Objetivos de negocio / personales"),
      p("Los objetivos se expresan en términos del valor para el usuario, no en términos técnicos:"),
      table([900, 4200, 4260], ["ID", "Objetivo", "Indicador de éxito"], [
        ["OBJ-1", "Reducir el tiempo de transcripción de una canción.", "De horas a minutos para obtener un borrador utilizable."],
        ["OBJ-2", "Obtener tablaturas físicamente tocables.", "Cero posiciones imposibles en la salida (garantizado por la matriz de inhibición)."],
        ["OBJ-3", "Permitir refinamiento iterativo sin software externo.", "Seleccionar y reprocesar secciones dentro de la propia app hasta convencer."],
        ["OBJ-4", "Cero fricción de instalación y uso.", "Instalador único; abrir y arrastrar un MP3 sin configurar Python, CUDA ni Docker."],
        ["OBJ-5", "Capturar la expresividad de la guitarra.", "Marcado automático de hammer-on/pull-off, slides, bends y vibrato en la salida."],
      ]),
      spacer(),

      // 3. Stakeholders
      h1("3. Stakeholders"),
      table([2600, 3380, 3380], ["Stakeholder", "Rol", "Interés / Expectativa"], [
        ["Usuario propietario (José)", "Owner, único usuario, revisor humano.", "Transcribir su repertorio rápido y con calidad editable."],
        ["Comunidad OSS", "Provee modelos y librerías (Demucs, YourMT3+, PyGuitarPro, alphaTab, etc.).", "Las licencias se respetan en ámbito de uso personal."],
        ["Editores de tablatura externos", "Guitar Pro / TuxGuitar / MuseScore.", "Compatibilidad de los archivos GP exportados para edición fina."],
      ]),
      spacer(),

      // 4. Alcance
      h1("4. Alcance"),
      h2("4.1 Dentro de alcance (in-scope)"),
      bullet("Entrada de **guitarra polifónica desde la mezcla completa** (MP3/WAV)."),
      bullet("Separación de la pista de guitarra, transcripción a notas y asignación de cuerda/traste."),
      bullet("**Restricción de realismo físico** que impide posiciones imposibles o no ergonómicas."),
      bullet("Marcado de **técnicas expresivas** por niveles de confiabilidad (Tier 1 automático; Tier 2 con clasificador; Tier 3 como sugerencia revisable)."),
      bullet("**Flujo human-in-the-loop**: visor con reproducción, selección de secciones y reprocesado por región hasta el resultado final."),
      bullet("Exportación a **GP5 (por defecto), GP4 y GP3**."),
      bullet("**App de escritorio autocontenida** (Tauri + Python embebido), ejecución 100% local."),
      h2("4.2 Fuera de alcance (out-of-scope)"),
      bullet("Multiusuario, autenticación, facturación o despliegue como servicio (SaaS)."),
      bullet("Entrenamiento o fine-tuning de modelos propios."),
      bullet("Otros instrumentos (bajo, piano, batería) como salida de tablatura."),
      bullet("**Edición manual nota por nota** dentro de la app (Tier B): se delega a Guitar Pro / TuxGuitar abriendo el archivo exportado."),
      bullet("Transcripción perfecta o lista para publicación sin revisión humana."),
      spacer(),

      // 5. Requisitos de negocio
      h1("5. Requisitos de negocio de alto nivel"),
      p("Expresados en lenguaje no técnico; se rastrean hacia los requisitos funcionales del SRS (ver matriz de trazabilidad)."),
      table([1100, 5600, 2660], ["ID", "Requisito de negocio", "Prioridad"], [
        ["BR-01", "El sistema debe aceptar una canción en MP3/WAV y producir una tablatura de guitarra descargable.", "Must"],
        ["BR-02", "La tablatura generada nunca debe contener posiciones físicamente imposibles de tocar.", "Must"],
        ["BR-03", "El usuario debe poder escuchar el resultado y compararlo con el audio original.", "Must"],
        ["BR-04", "El usuario debe poder seleccionar una sección y volver a procesarla con otros parámetros, las veces que necesite.", "Must"],
        ["BR-05", "La salida debe poder guardarse en formatos Guitar Pro compatibles (GP5/GP4/GP3).", "Must"],
        ["BR-06", "La aplicación debe instalarse y usarse sin configurar dependencias técnicas (Python, CUDA, Docker).", "Must"],
        ["BR-07", "La tablatura debe incluir técnicas expresivas detectables automáticamente con alta confianza.", "Should"],
        ["BR-08", "El procesamiento debe completarse en un tiempo razonable en el hardware del usuario.", "Should"],
        ["BR-09", "El usuario debe poder elegir entre modelos de transcripción y comparar calidad.", "Could"],
        ["BR-10", "El sistema debe poder procesar varias canciones por lote (modo posterior).", "Could"],
      ]),
      spacer(),

      // 6. AS-IS vs TO-BE
      h1("6. Procesos AS-IS vs TO-BE"),
      h2("6.1 Proceso actual (AS-IS) — transcripción manual"),
      bullet("Escuchar la canción repetidamente, segmento a segmento."),
      bullet("Identificar de oído las notas, su altura y duración."),
      bullet("Deducir la posición en el diapasón (cuerda/traste) probando con el instrumento."),
      bullet("Capturar manualmente en un editor (Guitar Pro/TuxGuitar) compás por compás."),
      bullet("Resultado: **horas por canción**; alta carga cognitiva; dependiente de la habilidad auditiva."),
      h2("6.2 Proceso propuesto (TO-BE) — Audio2Tab"),
      bullet("Arrastrar el MP3 a la app; el pipeline separa, transcribe, asigna digitación y marca técnicas automáticamente."),
      bullet("Revisar el borrador en el visor: reproducir, comparar con el original, identificar secciones débiles."),
      bullet("Seleccionar y reprocesar solo esas secciones con otros parámetros; iterar."),
      bullet("Exportar a Guitar Pro; (opcional) pulir detalles finos en el editor externo."),
      bullet("Resultado: **minutos hasta un borrador editable**; el esfuerzo humano se concentra en revisar, no en transcribir desde cero."),
      spacer(),

      // 7. Supuestos, restricciones, riesgos
      h1("7. Supuestos, restricciones y riesgos"),
      h2("7.1 Supuestos"),
      bullet("El usuario dispone de GPU NVIDIA con drivers/CUDA funcionando y de los archivos de audio de entrada."),
      bullet("Los modelos open-source y sus pesos siguen disponibles para descarga."),
      h2("7.2 Restricciones"),
      bullet("Ejecución local en RTX 4070 (8 GB VRAM) — recurso escaso que obliga a procesar por bloques (chunking)."),
      bullet("Uso estrictamente personal y sin distribución (define el tratamiento de licencias GPL como no restrictivo)."),
      bullet("Plataforma objetivo: Windows."),
      h2("7.3 Riesgos principales (resumen — detalle técnico en el SRS)"),
      table([3000, 3180, 3180], ["Riesgo", "Impacto", "Mitigación"], [
        ["Calidad de transcripción polifónica desde mezcla.", "Alto", "Expectativa de borrador editable; revisión humana; opción de pista limpia."],
        ["Empaquetado de PyTorch+CUDA en la app.", "Medio-alto", "Validar el empaquetado de forma temprana con un binario mínimo."],
        ["Detección poco fiable de técnicas (tapping/sweep).", "Medio", "Enfoque por niveles; solo auto-escribir lo confiable; resto como sugerencia."],
        ["Empalme del reprocesado por región.", "Medio-alto", "Reprocesar en fronteras de compás; conservar tempo global."],
      ]),
      spacer(),

      // 8. Criterios de aceptación
      h1("8. Criterios de aceptación / Definición de “hecho”"),
      bullet("Dado un MP3 de una canción con guitarra, la app produce un archivo GP5 que abre sin errores en Guitar Pro/TuxGuitar."),
      bullet("La tablatura resultante no contiene ninguna posición físicamente imposible."),
      bullet("El usuario puede reproducir la tab y el audio original, seleccionar una sección y reprocesarla, viendo el resultado actualizado."),
      bullet("Las técnicas Tier 1 (hammer-on/pull-off, slides, bends, vibrato) aparecen marcadas cuando están presentes con alta confianza."),
      bullet("La app se instala y ejecuta en una máquina limpia sin instalar Python, CUDA toolkit ni Docker por separado."),
      bullet("El resultado puede exportarse a GP5, GP4 o GP3 según elección del usuario."),
      spacer(),
      p("Fin del documento — BRD v1.0.", { italics: true, color: "888888" }),
    ],
  }],
});

Packer.toBuffer(doc).then((buf) => {
  fs.writeFileSync("docs/BRD.docx", buf);
  console.log("BRD.docx escrito:", buf.length, "bytes");
});
