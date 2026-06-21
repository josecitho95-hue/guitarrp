"""Tests de la detección de estructura (riffs repetidos). Sin audio ni modelos.

Ejecutar:  python tests/test_structure.py
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np  # noqa: E402

from sidecar.pipeline import structure  # noqa: E402


class _N:
    """Nota mínima con .start y .pitch."""
    def __init__(self, start, pitch):
        self.start = start
        self.pitch = pitch


# 4 beats/compás a 0.5 s/beat -> 2 s/compás. 7 compases -> 29 beats.
_BEATS = np.arange(0, 14.0001, 0.5)


def _riff(bar, pitches):
    """Notas en las 4 negras del compás `bar` con las alturas dadas."""
    t0 = bar * 2.0
    return [_N(t0 + i * 0.5, p) for i, p in enumerate(pitches)]


def _song():
    notes = []
    # Riff A en compases 0,1,2 ; Riff B en 3,4,5 ; compás 6 único.
    for b in (0, 1, 2):
        notes += _riff(b, [40, 43, 45, 40])
    for b in (3, 4, 5):
        notes += _riff(b, [47, 50, 47, 52])
    notes.append(_N(12.0, 60))
    return notes


def test_detects_two_repeated_clusters():
    st = structure.detect_structure(_song(), _BEATS, min_instances=3)
    assert st["n_repeated_clusters"] == 2
    sizes = sorted(c["size"] for c in st["clusters"])
    assert sizes == [3, 3]


def test_distinct_riffs_not_merged():
    st = structure.detect_structure(_song(), _BEATS, min_instances=3)
    # los compases 0 y 3 son riffs distintos -> clusters distintos
    cl = {b["bar"]: b["cluster"] for b in st["bars"]}
    assert cl[0] != cl[3]
    assert cl[0] == cl[1] == cl[2]
    assert cl[3] == cl[4] == cl[5]


def test_unique_bar_has_no_cluster():
    st = structure.detect_structure(_song(), _BEATS, min_instances=3)
    cl = {b["bar"]: b["cluster"] for b in st["bars"]}
    assert cl[6] == -1                         # compás único


def test_bars_in_same_cluster_helper():
    st = structure.detect_structure(_song(), _BEATS, min_instances=3)
    others = structure.bars_in_same_cluster(st, 0)
    assert sorted(others) == [1, 2]            # propagar correccion a estos
    assert structure.bars_in_same_cluster(st, 6) == []   # único -> nada que propagar


def test_empty_and_no_beats():
    assert structure.detect_structure([], _BEATS)["clusters"] == []
    assert structure.detect_structure(_song(), None)["clusters"] == []
    assert structure.detect_structure(_song(), [0.0])["clusters"] == []


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS  {t.__name__}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"FAIL  {t.__name__}: {type(exc).__name__}: {exc}")
    print(f"\n{len(tests) - failed}/{len(tests)} tests OK")
    sys.exit(1 if failed else 0)
