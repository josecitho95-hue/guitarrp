"""Audio2Tab — CLI.

Encadena las 5 etapas del pipeline sobre un archivo y produce un .gp5/.gp4/.gp3:

    preproceso -> [separacion] -> audio->MIDI -> MIDI->tab -> Guitar Pro

Usa el mismo runner que el sidecar (sidecar.pipeline.runner).

Ejemplos:
    python cli/transcribe.py samples/cancion.mp3 -o out.gp5
    python cli/transcribe.py riff.mid --from-midi -o riff.gp5 --bpm 100
    python cli/transcribe.py mezcla.wav -o tab.gp5 --separate --device cuda
    python cli/transcribe.py solo.wav --calibrate --open-string-pref alta
"""
from __future__ import annotations

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sidecar.pipeline.runner import PipelineParams, run_pipeline  # noqa: E402


def log(stage: str, msg: str) -> None:
    print(f"[{stage}] {msg}", file=sys.stderr, flush=True)


def run(args: argparse.Namespace) -> int:
    t0 = time.time()
    in_path = args.input
    if not os.path.exists(in_path):
        log("error", f"No existe el archivo: {in_path}")
        return 2

    work_dir = args.work_dir or os.path.join("storage", "jobs", str(int(t0)))
    out_path = args.output or (os.path.splitext(in_path)[0] + f".{args.output_format}")

    params = PipelineParams(
        transcriber=args.transcriber, separate=args.separate, device=args.device,
        auto_bpm=(args.bpm is None), bpm=(args.bpm or 120.0),
        output_format=args.output_format,
        calibrate_tuning=args.calibrate, open_string_pref=args.open_string_pref,
        tuning=args.tuning, capo=args.capo,
        onset_threshold=args.onset_threshold, min_note_ms=args.min_note_ms,
        from_midi=args.from_midi, multi_instrument=args.multi_instrument,
        stereo_guitars=args.stereo_guitars, include_vocals=args.vocals,
    )

    try:
        result = run_pipeline(in_path, out_path, params, work_dir,
                              on_progress=lambda s, p: log(s, f"{int(p * 100)}%"))
    except Exception as exc:  # noqa: BLE001
        log("error", str(exc))
        return 3

    log("done", f"{result['n_notes']} notas @ {result.get('bpm')} BPM -> "
                f"{result['output']} en {time.time() - t0:.1f}s")
    print(result["output"])
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Audio2Tab CLI")
    ap.add_argument("input", help="Audio (mp3/wav) o MIDI de entrada")
    ap.add_argument("-o", "--output", help="Salida (def: <input>.<formato>)")
    ap.add_argument("--output-format", default="gp5", choices=["gp5", "gp4", "gp3"])
    ap.add_argument("--from-midi", action="store_true", help="La entrada ya es un MIDI")
    ap.add_argument("--transcriber", default="mr_mt3", choices=["mr_mt3", "basic_pitch"],
                    help="Modelo audio->MIDI (def: mr_mt3, SOTA)")
    ap.add_argument("--separate", action="store_true", help="Aislar guitarra con Demucs")
    ap.add_argument("--multi-instrument", action="store_true",
                    help="Guitarra + bajo en pistas separadas (requiere --separate)")
    ap.add_argument("--stereo-guitars", action="store_true",
                    help="2 guitarras paneadas L/R (requiere --multi-instrument)")
    ap.add_argument("--vocals", action="store_true",
                    help="Añade pista de melodía vocal (requiere --multi-instrument)")
    ap.add_argument("--device", default="cpu", choices=["cpu", "cuda"], help="Dispositivo Demucs")
    ap.add_argument("--bpm", type=float, default=None,
                    help="Tempo manual; si se omite, se detecta automaticamente")
    ap.add_argument("--calibrate", action="store_true", help="Calibrar afinacion a A440 (SH-01)")
    ap.add_argument("--open-string-pref", default="media", choices=["alta", "media", "baja"],
                    help="Preferencia por cuerdas al aire (SH-02)")
    ap.add_argument("--tuning", default="standard",
                    choices=["standard", "eb_standard", "d_standard", "drop_d", "drop_c"],
                    help="Afinación de la guitarra")
    ap.add_argument("--capo", type=int, default=0, help="Traste en el que se coloca el capo")
    ap.add_argument("--onset-threshold", type=float, default=0.5)
    ap.add_argument("--min-note-ms", type=float, default=80.0)
    ap.add_argument("--work-dir", help="Carpeta de artefactos intermedios")
    args = ap.parse_args()
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
