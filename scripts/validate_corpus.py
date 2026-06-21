"""Validación por lotes: corre el pipeline sobre varios pares (audio + GP oficial)
y reporta la cercanía por canción y agregada. Para probar otros artistas/géneros.

Estructura del corpus: una carpeta con pares por nombre:
    corpus/
      cancion1.mp3   cancion1.gp5      (tab oficial)
      cancion2.wav   cancion2.gp3
      ...
(Las pistas de guitarra del oficial y de nuestra salida se autodetectan por nombre.)

Uso:
    python scripts/validate_corpus.py corpus/ [--device cuda] [--mono] [--out report.md]
"""
from __future__ import annotations

import argparse
import os
import tempfile

import guitarpro as gp

from compare_gp import (parse_tracks, extract_notes, dtw_similarity,
                        global_chroma_sim)
from sidecar.pipeline import preprocess
from sidecar.pipeline.runner import PipelineParams, run_pipeline

AUDIO_EXT = (".mp3", ".wav", ".flac", ".m4a")
GP_EXT = (".gp3", ".gp4", ".gp5")
STRING_NAMES = {40: "Mi", 45: "La", 50: "Re", 55: "Sol", 59: "Si", 64: "mi"}


def find_pairs(corpus_dir: str):
    files = os.listdir(corpus_dir)
    pairs = []
    for f in sorted(files):
        base, ext = os.path.splitext(f)
        if ext.lower() in AUDIO_EXT:
            gpf = next((g for g in files
                        if os.path.splitext(g)[0] == base
                        and os.path.splitext(g)[1].lower() in GP_EXT), None)
            if gpf:
                pairs.append((base, os.path.join(corpus_dir, f),
                              os.path.join(corpus_dir, gpf)))
    return pairs


def lowest_string(song) -> str:
    """Afinación de la 6ª cuerda de la 1ª pista de guitarra del oficial (proxy de tuning)."""
    for t in song.tracks:
        name = (t.name or "").lower()
        if ("gtr" in name or "guit" in name) and t.strings:
            low = min(s.value for s in t.strings)
            return f"{STRING_NAMES.get(low, low)} ({low})"
    return "?"


def run_one(name, audio, gp_path, device, mono):
    ref_song = gp.parse(gp_path)
    ref_tracks = parse_tracks("", ref_song)
    ref_notes = extract_notes(ref_song, ref_tracks)

    params = PipelineParams(
        transcriber="basic_pitch", separate=True, device=device,
        multi_instrument=not mono, stereo_guitars=not mono, auto_bpm=True,
        output_format="gp5",
    )
    with tempfile.TemporaryDirectory() as work:
        out = os.path.join(work, f"{name}.gp5")
        res = run_pipeline(audio, out, params, work)
        est_song = gp.parse(res["output"])
        est_tracks = parse_tracks("", est_song)
        est_notes = extract_notes(est_song, est_tracks)

    dtw = dtw_similarity(ref_notes, est_notes, 300, True) * 100
    glob = global_chroma_sim(ref_notes, est_notes, True) * 100
    bpm = preprocess.estimate_tempo(audio)
    return {
        "name": name, "tuning": lowest_string(ref_song), "bpm": round(bpm, 0),
        "ref_notes": len(ref_notes), "est_notes": len(est_notes),
        "dtw": round(dtw, 1), "content": round(glob, 1),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("corpus")
    ap.add_argument("--device", default="cuda", choices=["cpu", "cuda"])
    ap.add_argument("--mono", action="store_true", help="mono (sin estéreo) para baseline")
    ap.add_argument("--out", default="storage/corpus_report.md")
    args = ap.parse_args()

    pairs = find_pairs(args.corpus)
    if not pairs:
        print(f"No se encontraron pares (audio + .gp*) en {args.corpus}")
        return 1
    print(f"{len(pairs)} canciones encontradas.\n")

    rows = []
    for name, audio, gp_path in pairs:
        print(f"=== {name} ===", flush=True)
        try:
            r = run_one(name, audio, gp_path, args.device, args.mono)
            rows.append(r)
            print(f"  tuning={r['tuning']} bpm={r['bpm']} | DTW={r['dtw']}% "
                  f"contenido={r['content']}% (ref {r['ref_notes']} / est {r['est_notes']})")
        except Exception as exc:  # noqa: BLE001
            print(f"  ERROR: {exc}")

    if not rows:
        return 1
    mean_dtw = sum(r["dtw"] for r in rows) / len(rows)
    mean_content = sum(r["content"] for r in rows) / len(rows)

    lines = ["# Reporte de validación de corpus\n",
             f"Modo: {'mono' if args.mono else 'estéreo (2 guitarras)'} | "
             f"canciones: {len(rows)}\n",
             "| Canción | Afinación | BPM | DTW | Contenido | Notas ref/est |",
             "|---------|-----------|-----|-----|-----------|---------------|"]
    for r in rows:
        lines.append(f"| {r['name']} | {r['tuning']} | {r['bpm']:.0f} | {r['dtw']}% | "
                     f"{r['content']}% | {r['ref_notes']}/{r['est_notes']} |")
    lines.append(f"\n**Media: DTW {mean_dtw:.1f}% · contenido {mean_content:.1f}%**")
    report = "\n".join(lines)

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"\n{report}\n\nReporte -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
