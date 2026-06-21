"""Cache de iteración para afinar UNA canción sin re-separar/transcribir cada vez.

Paso 1 (lento, una vez):  python scripts/iterate_song.py prepare AUDIO.mp3 NOMBRE
  Separa por canal (estéreo) + transcribe guitarras L/R + bajo + batería, y guarda
  las notas crudas en storage/iter/NOMBRE.pkl

Paso 2 (rápido, N veces): python scripts/iterate_song.py build NOMBRE OFICIAL.gp3 \
                              [--bpm B] [--ref-tracks 0] [--snap] [--clean]
  Reconstruye el GP con los parámetros dados y lo compara vs el oficial.
"""
from __future__ import annotations

import argparse
import os
import pickle

import guitarpro as gp

from compare_gp import extract_notes, dtw_similarity, global_chroma_sim, windowed_similarity
from sidecar.pipeline import separate, transcribe, to_tab, to_gp, techniques, preprocess
from sidecar.pipeline.types import Note

ITER_DIR = "storage/iter"


def _notes_to_tuples(notes):
    return [(n.pitch, n.start, n.end, n.velocity) for n in notes]


def _tuples_to_notes(tup):
    return [Note(pitch=p, start=s, end=e, velocity=v) for (p, s, e, v) in tup]


def prepare(audio, name, device="cuda"):
    os.makedirs(ITER_DIR, exist_ok=True)
    work = os.path.join(ITER_DIR, f"{name}_sep")
    stems = separate.separate_stereo(audio, work, device=device)
    data = {"audio": audio, "stems": stems}
    gl = stems.get("guitar_l") or stems.get("guitar")
    gr = stems.get("guitar_r")
    data["gl"] = _notes_to_tuples(transcribe.transcribe_audio(gl)) if gl else []
    data["gr"] = _notes_to_tuples(transcribe.transcribe_audio(gr)) if gr else []
    if "bass" in stems:
        data["bass"] = _notes_to_tuples(
            transcribe.transcribe_audio(stems["bass"], min_freq=30.0, max_freq=500.0))
    if "drums" in stems:
        data["drums"] = _notes_to_tuples(transcribe.transcribe_mt3(
            stems["drums"], model="mr_mt3", device=device, drums_only=True))
    bpm = preprocess.estimate_tempo(audio)
    data["bpm_auto"] = bpm
    with open(os.path.join(ITER_DIR, f"{name}.pkl"), "wb") as f:
        pickle.dump(data, f)
    print(f"[prepare] {name}: gl={len(data['gl'])} gr={len(data['gr'])} "
          f"bass={len(data.get('bass', []))} drums={len(data.get('drums', []))} "
          f"bpm_auto={bpm}")


def build(name, official, bpm=None, ref_tracks=None, est_tracks="0,1",
          tuning="standard"):
    with open(os.path.join(ITER_DIR, f"{name}.pkl"), "rb") as f:
        data = pickle.load(f)
    bpm = bpm or data["bpm_auto"]
    tun = to_tab.TUNINGS.get(tuning, to_tab.STANDARD_TUNING)

    def tab_of(tup):
        return techniques.detect_techniques(
            to_tab.assign_tab(_tuples_to_notes(tup), tuning=tun)) if tup else []

    insts = [
        {"name": "Guitar L", "tuning": tun, "tab_notes": tab_of(data["gl"]), "midi_program": 30},
        {"name": "Guitar R", "tuning": tun, "tab_notes": tab_of(data["gr"]), "midi_program": 30},
    ]
    out = os.path.join(ITER_DIR, f"{name}_out.gp5")
    to_gp.write_multitrack_gp(insts, out, bpm=bpm, title=name)

    ref_song = gp.parse(official)
    rt = [int(x) for x in ref_tracks.split(",")] if ref_tracks else None
    from compare_gp import parse_tracks
    rt = rt or parse_tracks("", ref_song)
    et = [int(x) for x in est_tracks.split(",")]
    ref = extract_notes(ref_song, rt)
    est = extract_notes(gp.parse(out), et)
    dtw = dtw_similarity(ref, est, 300, True) * 100
    win = windowed_similarity(ref, est, 300, True) * 100
    glob = global_chroma_sim(ref, est, True) * 100
    n_meas = len(gp.parse(out).tracks[0].measures)
    print(f"[build] {name} bpm={bpm} tuning={tuning} ref{rt} est{et} | "
          f"DTW={dtw:.1f}% ventana={win:.1f}% contenido={glob:.1f}% | "
          f"compases={n_meas} (oficial={len(ref_song.tracks[rt[0]].measures)})")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("prepare"); p.add_argument("audio"); p.add_argument("name")
    p.add_argument("--device", default="cuda")
    b = sub.add_parser("build"); b.add_argument("name"); b.add_argument("official")
    b.add_argument("--bpm", type=float); b.add_argument("--ref-tracks")
    b.add_argument("--est-tracks", default="0,1"); b.add_argument("--tuning", default="standard")
    a = ap.parse_args()
    if a.cmd == "prepare":
        prepare(a.audio, a.name, a.device)
    else:
        build(a.name, a.official, a.bpm, a.ref_tracks, a.est_tracks, a.tuning)


if __name__ == "__main__":
    main()
