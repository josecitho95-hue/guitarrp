// Audio2Tab UI — habla con el sidecar FastAPI local.
const API = window.AUDIO2TAB_API || "http://127.0.0.1:8765";

const $ = (id) => document.getElementById(id);
const fileInput = $("file");
const drop = $("drop");
const dropLabel = $("drop-label");
const goBtn = $("go");
let selectedFile = null;
let pollTimer = null;

// --- Estado del servidor ---
async function ping() {
  try {
    const r = await fetch(`${API}/healthz`, { cache: "no-store" });
    setServer(r.ok);
  } catch {
    setServer(false);
  }
}
function setServer(up) {
  const el = $("server-status");
  el.classList.toggle("status--on", up);
  el.classList.toggle("status--off", !up);
  el.title = up ? "Sidecar conectado" : "Sidecar no disponible";
}

// --- Selección de archivo ---
drop.addEventListener("click", () => fileInput.click());
drop.addEventListener("dragover", (e) => { e.preventDefault(); drop.classList.add("drop--over"); });
drop.addEventListener("dragleave", () => drop.classList.remove("drop--over"));
drop.addEventListener("drop", (e) => {
  e.preventDefault();
  drop.classList.remove("drop--over");
  if (e.dataTransfer.files.length) setFile(e.dataTransfer.files[0]);
});
fileInput.addEventListener("change", () => {
  if (fileInput.files.length) setFile(fileInput.files[0]);
});
function setFile(f) {
  selectedFile = f;
  dropLabel.textContent = f.name;
  goBtn.disabled = false;
}

// --- Lanzar job ---
goBtn.addEventListener("click", async () => {
  if (!selectedFile) return;
  goBtn.disabled = true;
  const isMidi = /\.midi?$/i.test(selectedFile.name);

  const fd = new FormData();
  fd.append("file", selectedFile);
  fd.append("transcriber", $("transcriber").value);
  fd.append("output_format", $("output_format").value);
  fd.append("open_string_pref", $("open_string_pref").value);
  fd.append("bpm", $("bpm").value);
  fd.append("separate", $("separate").checked);
  fd.append("calibrate_tuning", $("calibrate_tuning").checked);
  fd.append("from_midi", isMidi);

  resetJobCard(selectedFile.name);
  try {
    const r = await fetch(`${API}/jobs`, { method: "POST", body: fd });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const { id } = await r.json();
    poll(id);
  } catch (err) {
    showError(`No se pudo crear el trabajo: ${err.message}`);
    goBtn.disabled = false;
  }
});

// --- Polling de progreso ---
function poll(id) {
  clearInterval(pollTimer);
  pollTimer = setInterval(async () => {
    try {
      const r = await fetch(`${API}/jobs/${id}`, { cache: "no-store" });
      const j = await r.json();
      setProgress(j.stage, j.progress);
      if (j.status === "done") {
        clearInterval(pollTimer);
        showDone(id, j);
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

// --- UI del job ---
function resetJobCard(name) {
  $("job-card").hidden = false;
  $("job-name").textContent = name;
  $("job-result").hidden = true;
  $("job-error").hidden = true;
  setProgress("en cola", 0);
}
function setProgress(stage, pct) {
  $("job-stage").textContent = stage || "";
  $("progress-bar").style.width = `${Math.round((pct || 0) * 100)}%`;
}
function showDone(id, j) {
  setProgress("listo", 1);
  $("job-summary").textContent = `${j.n_notes ?? "?"} notas transcritas`;
  const a = $("download");
  a.href = `${API}/jobs/${id}/result`;
  $("job-result").hidden = false;
  goBtn.disabled = false;
}
function showError(msg) {
  const e = $("job-error");
  e.textContent = msg;
  e.hidden = false;
  goBtn.disabled = false;
}

// --- init ---
ping();
setInterval(ping, 4000);
