"""Lazy-loaded model singletons (YuNet, Haar cascades, open_clip ViT-B/32, aesthetic head).

Lifted from cull_server.py's module-level loading, made lazy so importing the package is
cheap and the heavy models load once on first use (or via warmup() at container build).
"""
from __future__ import annotations

import os
import sys
import traceback
import urllib.request
from pathlib import Path

import cv2
import open_clip
import torch


def _weights_dir() -> Path:
    """Where the downloaded model weights live (YuNet, aesthetic head).

    From source this is `pipeline/weights/`. But when frozen (the packaged desktop app) `__file__`
    points into PyInstaller's `_MEIPASS` extraction dir, which is **ephemeral** (wiped each launch)
    and not a real package directory — writing there fails and would re-download ~GB every run. So
    persist under the user's app-data dir (the same default the server uses for `CULL_DATA_DIR`).
    `CULL_WEIGHTS_DIR` overrides either way.
    """
    env = os.environ.get("CULL_WEIGHTS_DIR")
    if env:
        return Path(env).expanduser()
    if getattr(sys, "frozen", False):
        base = Path(os.environ.get("CULL_DATA_DIR", Path.home() / ".photo-cherrypick-desktop"))
        return base / "weights"
    return Path(__file__).resolve().parent / "weights"


_WEIGHTS = _weights_dir()
_WEIGHTS.mkdir(parents=True, exist_ok=True)

YUNET_URL = ("https://github.com/opencv/opencv_zoo/raw/main/models/"
             "face_detection_yunet/face_detection_yunet_2023mar.onnx")
YUNET_PATH = _WEIGHTS / "face_detection_yunet_2023mar.onnx"
AES_URL = "https://github.com/LAION-AI/aesthetic-predictor/raw/main/sa_0_4_vit_b_32_linear.pth"
AES_PATH = _WEIGHTS / "aesthetic_vit_b_32_linear.pth"

# YuNet confidence threshold. Lowered 0.7 -> 0.6 to recover lower-confidence faces (children at an
# angle, slight motion) that the family-shoot audit showed being missed entirely. The area filter in
# faces.detect_faces (drop faces < 15% of the largest) guards precision against small false positives.
# Env-tunable so the eval harness can sweep it. See docs/SCORING-ITERATION-LOG.md.
SCORE_THRESHOLD = float(os.environ.get("YUNET_SCORE", "0.6"))
_EXPR_PROMPTS = {
    "smile": ("a person smiling, happy joyful expression",
              "a person with a neutral, flat or unhappy expression"),
    "gaze":  ("a person looking directly at the camera",
              "a person looking away from the camera"),
    # eye-occlusion probe: when high, the eyes aren't visible, so eyes_open/eye_sharpness/
    # eye_contact become noise and scoring must fall back to expression/pose/framing.
    "sunglasses": ("a close-up of a person wearing dark opaque sunglasses covering the eyes",
                   "a close-up of a person's face with bare visible eyes and no sunglasses"),
    # NOTE: CLIP "facing" (front/back) and "eyes_open" probes were tested (iter 3-4) and gave
    # net-neutral-or-worse results on the audit shoot — removed. See docs/SCORING-ITERATION-LOG.md.
}

_state: dict = {}


def device() -> str:
    return os.environ.get("TORCH_DEVICE") or ("cuda" if torch.cuda.is_available() else "cpu")


def _log(msg: str):
    """Diagnostics go to stderr, which the sidecar forwards to the Tauri shell's log."""
    print(f"[models] {msg}", file=sys.stderr, flush=True)


def _download(url: str, path: Path):
    if not path.exists():
        _log(f"downloading {path.name} from {url} -> {path}")
        urllib.request.urlretrieve(url, path)
        _log(f"downloaded {path.name} ({path.stat().st_size} bytes)")


def yunet():
    if "yunet" not in _state:
        try:
            _download(YUNET_URL, YUNET_PATH)
            _state["yunet"] = cv2.FaceDetectorYN_create(str(YUNET_PATH), "", (0, 0), SCORE_THRESHOLD)
            _log(f"loaded YuNet face detector from {YUNET_PATH}")
        except Exception as e:
            _log(f"YuNet load FAILED (url={YUNET_URL}, path={YUNET_PATH}): {e!r} "
                 f"-- detection degrades to the Haar cascade fallback")
            traceback.print_exc(file=sys.stderr)
            _state["yunet"] = None
    return _state["yunet"]


def haar():
    if "haar" not in _state:
        path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        cascade = cv2.CascadeClassifier(path)
        # CascadeClassifier never raises on a bad path -- it returns an empty classifier that
        # silently detects nothing. Since this is YuNet's fallback, an empty one means no face
        # detection at all, so surface it rather than degrading without a trace.
        if cascade.empty():
            _log(f"Haar frontalface cascade FAILED to load from {path} -- face detection will be empty")
        _state["haar"] = cascade
    return _state["haar"]


def eye_cascade():
    if "eye" not in _state:
        path = cv2.data.haarcascades + "haarcascade_eye.xml"
        cascade = cv2.CascadeClassifier(path)
        if cascade.empty():
            _log(f"Haar eye cascade FAILED to load from {path} -- eye detection will be empty")
        _state["eye"] = cascade
    return _state["eye"]


def clip():
    """(model, preprocess, tokenizer, device)."""
    if "clip" not in _state:
        dev = device()
        try:
            model, _, pre = open_clip.create_model_and_transforms("ViT-B-32-quickgelu", pretrained="openai")
            model = model.to(dev).eval()
            tok = open_clip.get_tokenizer("ViT-B-32-quickgelu")
        except Exception as e:
            # No fallback for CLIP -- it backs embeddings, scene grouping and expression probes.
            # Log enough to diagnose (often a weight download failure), then re-raise so the
            # failure propagates to the caller instead of being swallowed.
            _log(f"CLIP (ViT-B-32-quickgelu/openai, device={dev}) load FAILED: {e!r}")
            traceback.print_exc(file=sys.stderr)
            raise
        _state["clip"] = (model, pre, tok, dev)
        _log(f"loaded CLIP ViT-B-32-quickgelu (openai) on {dev}")
    return _state["clip"]


def expr_text():
    """{name: normalized [pos,neg] text embeddings} for CLIP zero-shot expression."""
    if "expr_text" not in _state:
        model, _, tok, dev = clip()
        out = {}
        with torch.no_grad():
            for k, (pos, neg) in _EXPR_PROMPTS.items():
                t = model.encode_text(tok([pos, neg]).to(dev))
                out[k] = t / t.norm(dim=-1, keepdim=True)
        _state["expr_text"] = out
    return _state["expr_text"]


def aes_head():
    if "aes" not in _state:
        try:
            _download(AES_URL, AES_PATH)
            head = torch.nn.Linear(512, 1)
            head.load_state_dict(torch.load(str(AES_PATH), map_location="cpu"))
            head.eval()
            _state["aes"] = head
            _log(f"loaded aesthetic head from {AES_PATH}")
        except Exception as e:
            _log(f"aesthetic head load FAILED (url={AES_URL}, path={AES_PATH}): {e!r} "
                 f"-- aesthetic scoring is skipped for this run")
            traceback.print_exc(file=sys.stderr)
            _state["aes"] = None
    return _state["aes"]


def warmup():
    """Force all models to load (used at container build / worker startup)."""
    for loader in (yunet, haar, eye_cascade, clip, expr_text, aes_head):
        loader()
