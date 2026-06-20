// Audio2Tab UI — asistente paso a paso (vanilla). Habla con el sidecar local.
const API = window.AUDIO2TAB_API || "http://127.0.0.1:8765";
const $ = (id) => document.getElementById(id);

let selectedFile = null;
let pollTimer = null;
let currentJobId = null;
const STAGE_ORDER = ["preprocess", "separating", "transcribing", "tabbing", "done"];

// ---------- Navegación entre pasos ----------
function goStep(n) {
  document.querySelectorAll(".panel").forEach((p) => {
    p.classList.toggle("is-current", +p.dataset.panel === n);
  });
  document.querySelectorAll(".stepper .step").forEach((s) => {
    const i = +s.dataset.step;
    s.classList.toggle("is-active", i === n);
    s.classList.toggle("is-done", i < n);
  });
  document.querySelectorAll(".step-line").forEach((l, idx) => {
    l.classList.toggle("is-done", idx < n - 1);
  });
}

// ---------- Estado del sidecar ----------
async function ping() {
  const el = $("server");
  try {
    const r = await fetch(`${API}/healthz`, { cache: "no-store" });
    const up = r.ok;
    el.classList.toggle("is-on", up);
    el.querySelector(".server-text").textContent = up ? "conectado" : "sin conexión";
  } catch {
    el.classList.remove("is-on");
    el.querySelector(".server-text").textContent = "sin conexión";
  }
}

// ---------- Paso 1: archivo ----------
const drop = $("drop");
drop.addEventListener("click", () => $("file").click());
drop.addEventListener("dragover", (e) => { e.preventDefault(); drop.classList.add("is-over"); });
drop.addEventListener("dragleave", () => drop.classList.remove("is-over"));
drop.addEventListener("drop", (e) => {
  e.preventDefault(); drop.classList.remove("is-over");
  if (e.dataTransfer.files.length) setFile(e.dataTransfer.files[0]);
});
$("file").addEventListener("change", (e) => {
  if (e.target.files.length) setFile(e.target.files[0]);
});
function setFile(f) {
  selectedFile = f;
  $("file-name").textContent = f.name;
  $("file-pill").hidden = false;
  $("drop-title").textContent = "Archivo seleccionado";
  $("to-2").disabled = false;
}
$("file-clear").addEventListener("click", (e) => {
  e.preventDefault();
  selectedFile = null;
  $("file").value = "";
  $("file-pill").hidden = true;
  $("drop-title").textContent = "Arrastra el archivo aquí";
  $("to-2").disabled = true;
});

$("to-2").addEventListener("click", () => goStep(2));
$("to-1").addEventListener("click", () => goStep(1));

// BPM manual solo visible si se desactiva la detección automática
$("auto_bpm").addEventListener("change", (e) => {
  $("bpm-field").hidden = e.target.checked;
});

// ---------- Paso 2: controles segmentados ----------
document.querySelectorAll(".segmented").forEach((seg) => {
  seg.addEventListener("click", (e) => {
    const btn = e.target.closest("button");
    if (!btn) return;
    seg.querySelectorAll("button").forEach((b) => b.classList.remove("is-on"));
    btn.classList.add("is-on");
    seg.dataset.value = btn.dataset.val;
  });
});

// ---------- Lanzar transcripción ----------
$("go").addEventListener("click", async () => {
  if (!selectedFile) { goStep(1); return; }
  goStep(3);
  startProcessingUI();

  const isMidi = /\.midi?$/i.test(selectedFile.name);
  const separate = $("separate").checked;
  const fd = new FormData();
  fd.append("file", selectedFile);
  fd.append("transcriber", $("transcriber").dataset.value);
  fd.append("output_format", $("output_format").value);
  fd.append("open_string_pref", $("open_string_pref").dataset.value);
  fd.append("tuning", $("tuning").value);
  fd.append("capo", $("capo").value);
  fd.append("auto_bpm", $("auto_bpm").checked);
  fd.append("bpm", $("bpm").value);
  fd.append("separate", separate);
  fd.append("calibrate_tuning", $("calibrate_tuning").checked);
  fd.append("from_midi", isMidi);

  try {
    const r = await fetch(`${API}/jobs`, { method: "POST", body: fd });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const { id } = await r.json();
    poll(id);
  } catch (err) {
    showError(`No se pudo iniciar: ${err.message}`);
  }
});

// ---------- Paso 3: proceso ----------
function startProcessingUI() {
  $("processing").hidden = false;
  $("result").hidden = true;
  $("failed").hidden = true;
  $("proc-file").textContent = selectedFile ? selectedFile.name : "";
  // Mostrar/ocultar "Aislando guitarra" según el toggle
  const sepLi = document.querySelector('.stages li[data-stage="separating"]');
  sepLi.classList.toggle("hidden", !$("separate").checked);
  document.querySelectorAll(".stages li").forEach((li) => li.classList.remove("active", "done"));
  $("progress-bar").style.width = "0%";
}

function paintStages(stage) {
  const idx = STAGE_ORDER.indexOf(stage);
  if (idx < 0) return;
  document.querySelectorAll(".stages li").forEach((li) => {
    const i = STAGE_ORDER.indexOf(li.dataset.stage);
    li.classList.toggle("done", i < idx);
    li.classList.toggle("active", i === idx);
  });
}

function poll(id) {
  clearInterval(pollTimer);
  pollTimer = setInterval(async () => {
    try {
      const j = await (await fetch(`${API}/jobs/${id}`, { cache: "no-store" })).json();
      if (j.stage) paintStages(j.stage);
      $("progress-bar").style.width = `${Math.round((j.progress || 0) * 100)}%`;
      if (j.status === "done") {
        clearInterval(pollTimer);
        document.querySelectorAll(".stages li:not(.hidden)").forEach((li) => li.classList.add("done"));
        showResult(id, j);
      } else if (j.status === "error") {
        clearInterval(pollTimer);
        showError(j.error || "Error desconocido");
      }
    } catch (err) {
      clearInterval(pollTimer);
      showError(`Conexión perdida: ${err.message}`);
    }
  }, 700);
}

let atApi = null;

function initAlphaTab(fileUrl) {
  if (atApi) {
    atApi.destroy();
    atApi = null;
  }

  const element = $("alphaTab");
  atApi = new alphaTab.AlphaTabApi(element, {
    file: fileUrl,
    player: {
      enablePlayer: true,
      soundFont: "https://cdn.jsdelivr.net/npm/@coderline/alphatab@1.8.3/dist/soundfont/sonivox.sf2",
      scrollElement: document.querySelector(".at-viewport")
    }
  });

  const playBtn = $("play-btn");
  const pauseBtn = $("pause-btn");
  const stopBtn = $("stop-btn");
  const audio = $("original-audio");
  const modeSelect = $("audio-mode-select");

  // Forzar volumen según modo inicial
  atApi.scoreLoaded.on((score) => {
    const mode = modeSelect.value;
    atApi.masterVolume = mode === "original" ? 0.0 : 1.0;

    const track = score.tracks[0];
    if (track && track.staves[0] && track.staves[0].bars) {
      const totalBars = track.staves[0].bars.length;
      $("range-start").max = totalBars;
      $("range-end").max = totalBars;
      $("range-start").value = 1;
      $("range-end").value = Math.min(4, totalBars);
    }
  });

  atApi.playPauseChanged.on((e) => {
    if (e.state === 1) { // 1 = Playing
      playBtn.style.display = "none";
      pauseBtn.style.display = "inline-flex";
    } else { // 0 = Paused / Stopped
      playBtn.style.display = "inline-flex";
      pauseBtn.style.display = "none";
    }
  });

  playBtn.onclick = () => {
    const mode = modeSelect.value;
    if (mode === "original") {
      atApi.masterVolume = 0.0;
      atApi.play();
      audio.play();
    } else {
      atApi.masterVolume = 1.0;
      atApi.play();
      audio.pause();
    }
  };

  pauseBtn.onclick = () => {
    atApi.pause();
    audio.pause();
  };

  stopBtn.onclick = () => {
    atApi.stop();
    audio.pause();
    audio.currentTime = 0;
  };

  // Sincronización de audio original -> alphaTab
  audio.ontimeupdate = () => {
    if (modeSelect.value !== "original" || !atApi || !atApi.isReadyForPlayback) return;
    const diff = Math.abs(atApi.timePosition - (audio.currentTime * 1000));
    if (diff > 150) {
      atApi.timePosition = audio.currentTime * 1000;
    }
  };

  audio.onended = () => {
    atApi.stop();
  };

  // Sincronización de alphaTab -> audio original
  atApi.playerPositionChanged.on((args) => {
    if (modeSelect.value !== "original") return;
    const diff = Math.abs(args.currentTime - (audio.currentTime * 1000));
    if (diff > 300) {
      audio.currentTime = args.currentTime / 1000;
    }
  });

  // Manejador del cambio de fuente de audio
  modeSelect.onchange = (e) => {
    const mode = e.target.value;
    if (mode === "original") {
      atApi.masterVolume = 0.0;
      audio.currentTime = atApi.timePosition / 1000;
      if (playBtn.style.display === "none") { // playing
        audio.play();
      }
    } else {
      atApi.masterVolume = 1.0;
      audio.pause();
    }
  };
}

function showResult(id, j) {
  currentJobId = id;
  $("processing").hidden = true;
  $("result").hidden = false;
  const bpmTxt = j.bpm ? ` · ${Math.round(j.bpm)} BPM` : "";
  $("result-summary").textContent = `${j.n_notes ?? "?"} notas transcritas${bpmTxt} · ${$("output_format").value.toUpperCase()}`;
  $("download").href = `${API}/jobs/${id}/result`;

  // Cargar audio original
  const audio = $("original-audio");
  audio.src = `${API}/jobs/${id}/audio`;
  audio.load();

  // Ensanchar la interfaz para la partitura
  document.querySelector(".stage").classList.add("is-wide");
  document.querySelector('.panel[data-panel="3"]').classList.add("is-wide");

  // Inicializar alphaTab
  const gpUrl = `${API}/jobs/${id}/result`;
  initAlphaTab(gpUrl);
}

function showError(msg) {
  $("processing").hidden = true;
  $("failed").hidden = false;
  $("error-text").textContent = msg;
}

function reset() {
  clearInterval(pollTimer);

  // Restaurar el audio original
  const audio = $("original-audio");
  audio.pause();
  audio.src = "";
  currentJobId = null;

  // Restaurar el texto del mensaje de rango
  $("range-msg").textContent = "Puedes loop-reproducir, seleccionar el rango o re-transcribir esta sección con nuevos parámetros.";
  $("range-msg").style.color = "var(--muted)";

  // Restaurar el ancho normal de la interfaz
  document.querySelector(".stage").classList.remove("is-wide");
  document.querySelector('.panel[data-panel="3"]').classList.remove("is-wide");

  if (atApi) {
    try {
      atApi.clearPlaybackRangeHighlight();
      atApi.playbackRange = null;
    } catch(e) {}
    atApi.destroy();
    atApi = null;
  }
  $("btn-clear-highlight").style.display = "none";

  goStep(1);
}
$("again").addEventListener("click", reset);
$("retry").addEventListener("click", () => goStep(2));

// ---------- init ----------
ping();
setInterval(ping, 4000);
goStep(1);

// ---------- Selección de Rango (Fase 4 - Visual / Loop) ----------
$("btn-highlight").addEventListener("click", () => {
  if (!atApi || !atApi.score) return;
  const track = atApi.score.tracks[0];
  if (!track || !track.staves[0]) return;

  const start = parseInt($("range-start").value) || 1;
  const end = parseInt($("range-end").value) || 1;
  const bars = track.staves[0].bars;
  const totalBars = bars.length;

  if (start < 1 || end < 1 || start > totalBars || end > totalBars || start > end) {
    alert("Rango de compases inválido.");
    return;
  }

  const startBar = bars[start - 1];
  const endBar = bars[end - 1];

  if (startBar && endBar && startBar.beats.length > 0 && endBar.beats.length > 0) {
    const startBeat = startBar.beats[0];
    const endBeat = endBar.beats[endBar.beats.length - 1];

    // Resaltar visualmente
    atApi.highlightPlaybackRange(startBeat, endBeat);

    // Fijar el loop/playback range
    atApi.playbackRange = {
      startTick: startBeat.absoluteTick,
      endTick: endBeat.absoluteTick + endBeat.duration
    };

    $("btn-clear-highlight").style.display = "inline-flex";
  }
});

$("btn-clear-highlight").addEventListener("click", () => {
  if (!atApi) return;
  try {
    atApi.clearPlaybackRangeHighlight();
    atApi.playbackRange = null;
  } catch(e) {}
  $("btn-clear-highlight").style.display = "none";
});

// ---------- Reprocesamiento por Región (Fase 5) ----------
$("btn-reprocess").addEventListener("click", async () => {
  if (!currentJobId || !atApi) return;
  const start = parseInt($("range-start").value) || 1;
  const end = parseInt($("range-end").value) || 1;

  const track = atApi.score.tracks[0];
  if (!track || !track.staves[0]) return;
  const totalBars = track.staves[0].bars.length;

  if (start < 1 || end < 1 || start > totalBars || end > totalBars || start > end) {
    alert("Rango de compases inválido.");
    return;
  }

  const btn = $("btn-reprocess");
  const msg = $("range-msg");
  btn.disabled = true;
  msg.textContent = "Re-procesando región de compases seleccionada...";
  msg.style.color = "var(--accent)";

  const fd = new FormData();
  fd.append("start_measure", start);
  fd.append("end_measure", end);
  fd.append("transcriber", $("transcriber").dataset.value);
  fd.append("open_string_pref", $("open_string_pref").dataset.value);

  try {
    const r = await fetch(`${API}/jobs/${currentJobId}/reprocess`, {
      method: "POST",
      body: fd
    });
    if (!r.ok) {
      throw new Error(`HTTP ${r.status}: ${await r.text()}`);
    }
    const res = await r.json();
    msg.textContent = `Región re-procesada con éxito. ${res.n_reprocessed} notas actualizadas en el rango.`;
    msg.style.color = "var(--ok)";

    // Detener audio
    const audio = $("original-audio");
    audio.pause();
    audio.currentTime = 0;

    // Recargar alphaTab sin caché
    initAlphaTab(`${API}/jobs/${currentJobId}/result?t=${Date.now()}`);
  } catch (e) {
    msg.textContent = `Error al re-procesar: ${e.message}`;
    msg.style.color = "var(--err)";
  } finally {
    btn.disabled = false;
  }
});


