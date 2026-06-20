"""Audio2Tab — CLI spike (Fase 0).

Encadena las 5 etapas del pipeline sobre un archivo y produce un .gp5/.gp4/.gp3:

    preproceso -> [separacion] -> audio->MIDI -> MIDI->tab -> Guitar Pro

Ejemplos:
    python cli/transcribe.py samples/cancion.mp3 -o out.gp5
    python cli/transcribe.py riff.mid --from-midi -o riff.gp5 --bpm 100
    python cli/transcribe.py mezcla.wav -o tab.gp5 --separate
"""
from __future__ import annotations

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sidecar.pipeline import preprocess, separate, transcribe, to_tab, to_gp  # noqa: E402


def log(stage: str, msg: str) -> None:
    print(f"[{stage}] {msg}", file=sys.stderr, flush=True)


def run(args: argparse.Namespace) -> int:
    t0 = time.time()
    in_path = args.input
    if not os.path.exists(in_path):
        log("error", f"No existe el archivo: {in_path}")
        return 2

    work_dir = args.work_dir or os.path.join("storage", "jobs", str(int(t0)))
    os.makedirs(work_dir, exist_ok=True)

    # --- Camino directo desde MIDI (salta etapas 1-3) ---
    if args.from_midi:
        log("transcribe", f"Cargando notas desde MIDI: {in_path}")
        notes = transcribe.notes_from_midi_file(in_path)
    else:
        # Etapa 1: preproceso
        wav = preprocess.to_wav_mono(in_path, os.path.join(work_dir, "input.wav"))
        log("preprocess", f"Audio listo: {os.path.basename(wav)}")

        # Etapa 2: separacion (opcional)
        if args.separate:
            wav = separate.separate_guitar(wav, work_dir, device=args.device)
            log("separate", f"Stem de guitarra: {os.path.basename(wav)}")
        else:
            log("separate", "omitida (usa --separate para aislar la guitarra)")

        # Etapa 3: audio -> MIDI
        if args.transcriber == "mr_mt3":
            log("transcribe", "Transcribiendo audio a notas (MT3 / mr_mt3, SOTA)...")
            notes = transcribe.transcribe_mt3(wav, model="mr_mt3")
        else:
            log("transcribe", "Transcribiendo audio a notas (Basic Pitch)...")
            notes = transcribe.transcribe_audio(
                wav, onset_threshold=args.onset_threshold,
                min_note_length_ms=args.min_note_ms)

    log("transcribe", f"{len(notes)} notas detectadas")
    if not notes:
        log("error", "No se detectaron notas; nada que exportar.")
        return 3

    # Etapa 4 + 4b: MIDI -> tab (digitacion + restricciones fisicas)
    tab = to_tab.assign_tab(notes)
    log("to_tab", f"{len(tab)} notas con digitacion asignada")

    # Etapa 5: tab -> Guitar Pro
    out_path = args.output or (os.path.splitext(in_path)[0] + ".gp5")
    to_gp.write_gp(tab, out_path, bpm=args.bpm,
                   title=os.path.splitext(os.path.basename(in_path))[0])
    dt = time.time() - t0
    log("to_gp", f"Escrito: {out_path}")
    log("done", f"Completado en {dt:.1f}s")
    print(out_path)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Audio2Tab CLI (Fase 0)")
    ap.add_argument("input", help="Audio (mp3/wav) o MIDI de entrada")
    ap.add_argument("-o", "--output", help="Salida .gp5/.gp4/.gp3 (def: <input>.gp5)")
    ap.add_argument("--from-midi", action="store_true", help="La entrada ya es un MIDI")
    ap.add_argument("--transcriber", default="mr_mt3", choices=["mr_mt3", "basic_pitch"],
                    help="Modelo audio->MIDI (def: mr_mt3, SOTA)")
    ap.add_argument("--separate", action="store_true", help="Aislar guitarra con Demucs")
    ap.add_argument("--device", default="cpu", choices=["cpu", "cuda"], help="Dispositivo Demucs")
    ap.add_argument("--bpm", type=float, default=120.0, help="Tempo para la cuantizacion")
    ap.add_argument("--onset-threshold", type=float, default=0.5)
    ap.add_argument("--min-note-ms", type=float, default=80.0)
    ap.add_argument("--work-dir", help="Carpeta de artefactos intermedios")
    args = ap.parse_args()
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
