"""Shared fixtures + synthetic data for the desktop culler tests.

The hermetic tests never execute the torch/CV models — they either exercise pure-numpy pipeline
code (score/group) with hand-built measurement dicts, or monkeypatch `analyze` with a synthetic
meta. A real end-to-end analyze run is exercised separately (CLI / `CULL_REAL=1`).
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

# make the repo root importable (desktop_core, pipeline, server)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def write_jpeg(path: Path, size=(64, 48), color=(120, 120, 120)) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, color).save(path, "JPEG")
    return path


def write_png(path: Path, size=(64, 48), color=(80, 160, 200)) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, color).save(path, "PNG")
    return path


def _unit_emb(seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    v = rng.standard_normal(512).astype(np.float32)
    return v / (np.linalg.norm(v) + 1e-8)


def make_meta(
    *, name: str, emb: np.ndarray | None = None, ctime: float | None = 1000.0,
    camera: str = "model:TestCam", faced: bool = True, eyes: int = 2, seed: int = 0, **overrides,
) -> dict:
    """A complete measurement dict accepted by compute_refs / axis_scores / build_groups."""
    m = {
        "name": name,
        "camera": camera,
        "ctime": ctime,
        "emb": emb if emb is not None else _unit_emb(seed),
        # sharpness / separation
        "sharp": 120.0, "face_sharp": 150.0, "eye_sharp": 160.0, "sep": 0.6,
        # exposure / tone / color
        "exp_mean": 0.48, "clip_hi": 0.001, "clip_lo": 0.001,
        "contrast": 0.22, "dyn": 0.7, "color": 0.5, "is_bw": False, "cast": 0.05,
        # face lighting / eyes
        "evenness": 0.8, "catch": 1,
        # face geometry
        "offset": 0.1 if faced else None, "face_frac": 0.12, "face_cy": 0.45,
        "face_top": 0.2, "roll": 2.0, "frontal": 0.8, "eyes": eyes,
        "thirds": 0.7, "clutter": 0.2,
        # expression
        "smile": 0.6, "gaze": 0.7,
        # aesthetic
        "aesthetic": 6.0,
    }
    m.update(overrides)
    return m


@pytest.fixture
def tmp_store(tmp_path):
    from desktop_core.store import CullStore
    s = CullStore(tmp_path / "cull.db")
    yield s
    s.close()
