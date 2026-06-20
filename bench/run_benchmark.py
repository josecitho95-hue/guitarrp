"""Benchmark de calidad de transcripción — Fase 1.

Compara los transcriptores (Path A modular vs Path B directo, mas baselines)
sobre un conjunto de piezas con tablatura "verdad", midiendo F1 a nivel de nota.
Elige el principal por F1 medido (no por intuicion).

Uso:
    python bench/run_benchmark.py --dataset guitarset --n 5
    python bench/run_benchmark.py --dataset dir --path mis_pruebas/

Cada item del dataset es (nombre, audio_path, ground_truth Notes).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sidecar.pipeline import separate, transcribe        # noqa: E402
from sidecar.pipeline.types import Note                  # noqa: E402
from bench.metrics import note_onset_prf                 # noqa: E402


# --- Registro de transcriptores: nombre -> callable(audio_path) -> list[Note] ---

def _basic_pitch(audio_path: str) -> list[Note]:
    return transcribe.transcribe_audio(audio_path)


def _demucs_basic_pitch(audio_path: str) -> list[Note]:
    stem = separate.separate_guitar(audio_path, "storage/bench_sep", device="cuda")
    return transcribe.transcribe_audio(stem)


def _mr_mt3(audio_path: str) -> list[Note]:
    return transcribe.transcribe_mt3(audio_path, model="mr_mt3")


TRANSCRIBERS = {
    "basic_pitch": _basic_pitch,
    "mr_mt3": _mr_mt3,                  # Path A SOTA (familia MT3, vía mt3-infer)
    "demucs+basic_pitch": _demucs_basic_pitch,
    # "yourmt3": incompatibilidad transformers 5.x (no operativo en stack 2026)
    # "trimplexx_crnn": Path B directo audio->tab (pendiente)
}


# --- Carga de datasets ---

def load_dir(path: str) -> list[tuple[str, str, list[Note]]]:
    """Empareja <name>.wav con <name>.mid (ground truth) en una carpeta."""
    items = []
    for f in sorted(os.listdir(path)):
        if f.lower().endswith((".wav", ".mp3", ".flac")):
            base = os.path.splitext(f)[0]
            gt = os.path.join(path, base + ".mid")
            if os.path.exists(gt):
                items.append((base, os.path.join(path, f),
                              transcribe.notes_from_midi_file(gt)))
    return items


def load_guitarset(n: int = 5, download: bool = True) -> list[tuple[str, str, list[Note]]]:
    """Carga un subconjunto de GuitarSet via mirdata (audio mic + anotacion)."""
    import mirdata
    gs = mirdata.initialize("guitarset")
    if download:
        gs.download(partial_download=["annotations", "audio_mic"])
    items = []
    for tid in list(gs.track_ids)[:n]:
        track = gs.track(tid)
        audio_path = _gs_audio_path(track)
        notes = _notes_from_guitarset(track)
        if audio_path and os.path.exists(audio_path) and notes:
            items.append((tid, audio_path, notes))
    return items


def _gs_audio_path(track):
    for attr in ("audio_mic_path", "audio_mono_mic_path", "audio_path"):
        p = getattr(track, attr, None)
        if p:
            return p
    return None


def _notes_from_guitarset(track) -> list[Note]:
    """Convierte la anotacion de notas de GuitarSet a list[Note].

    GuitarSet anota el pitch en MIDI (float); se redondea al semitono.
    """
    import math
    notes_anno = (getattr(track, "notes_all", None) or getattr(track, "notes", None))
    if notes_anno is None:
        return []
    unit = (getattr(notes_anno, "pitch_unit", None) or "midi").lower()
    out = []
    for interval, pitch in zip(notes_anno.intervals, notes_anno.pitches):
        if unit == "hz":
            midi = int(round(69 + 12 * math.log2(pitch / 440.0))) if pitch > 0 else 0
        else:  # midi
            midi = int(round(pitch))
        if 30 <= midi <= 96:
            out.append(Note(pitch=midi, start=float(interval[0]), end=float(interval[1])))
    out.sort(key=lambda n: (n.start, n.pitch))
    return out


# --- Ejecucion ---

def run(items, transcribers: list[str]) -> dict:
    results = {t: [] for t in transcribers}
    for name, audio, gt in items:
        print(f"\n=== {name}  (gt: {len(gt)} notas) ===", file=sys.stderr)
        for t in transcribers:
            fn = TRANSCRIBERS[t]
            t0 = time.time()
            try:
                est = fn(audio)
                m = note_onset_prf(gt, est)
                m["time_s"] = round(time.time() - t0, 1)
                results[t].append(m)
                print(f"  {t:22s} F1={m['f1']:.3f}  P={m['precision']:.3f}  "
                      f"R={m['recall']:.3f}  ({m['time_s']}s)", file=sys.stderr)
            except Exception as exc:
                print(f"  {t:22s} ERROR: {exc}", file=sys.stderr)
                results[t].append({"f1": 0.0, "error": str(exc)})
    return results


def summarize(results: dict) -> None:
    print("\n" + "=" * 60)
    print(f"{'Transcriptor':24s} {'F1 medio':>9s} {'P medio':>9s} {'R medio':>9s}")
    print("-" * 60)
    ranking = []
    for t, runs in results.items():
        f1s = [r["f1"] for r in runs if "f1" in r]
        ps = [r.get("precision", 0) for r in runs if "precision" in r]
        rs = [r.get("recall", 0) for r in runs if "recall" in r]
        avg = sum(f1s) / len(f1s) if f1s else 0.0
        ap = sum(ps) / len(ps) if ps else 0.0
        ar = sum(rs) / len(rs) if rs else 0.0
        ranking.append((avg, t, ap, ar))
    for avg, t, ap, ar in sorted(ranking, reverse=True):
        print(f"{t:24s} {avg:9.3f} {ap:9.3f} {ar:9.3f}")
    print("=" * 60)
    if ranking:
        best = max(ranking)
        print(f"GANADOR por F1 medido: {best[1]}  (F1={best[0]:.3f})")


def main() -> int:
    ap = argparse.ArgumentParser(description="Benchmark de transcripción (Fase 1)")
    ap.add_argument("--dataset", choices=["guitarset", "dir"], default="guitarset")
    ap.add_argument("--path", help="Carpeta con <name>.wav + <name>.mid (dataset=dir)")
    ap.add_argument("--n", type=int, default=5, help="Nº de piezas (GuitarSet)")
    ap.add_argument("--transcribers", nargs="+", default=list(TRANSCRIBERS),
                    help="Transcriptores a comparar")
    ap.add_argument("--out", default="bench/results.json")
    args = ap.parse_args()

    if args.dataset == "dir":
        if not args.path:
            print("--path requerido con --dataset dir", file=sys.stderr)
            return 2
        items = load_dir(args.path)
    else:
        items = load_guitarset(args.n)

    if not items:
        print("No se cargaron piezas de evaluación.", file=sys.stderr)
        return 3

    results = run(items, args.transcribers)
    summarize(results)
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nResultados -> {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
