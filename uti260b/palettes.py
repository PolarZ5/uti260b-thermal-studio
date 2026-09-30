"""Colour palettes: the camera's own (for decoding) and extra ones for display."""
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np

ASSETS = Path(__file__).with_name("assets.npz")

_CV_MAPS = {
    "inferno": cv2.COLORMAP_INFERNO,
    "magma": cv2.COLORMAP_MAGMA,
    "plasma": cv2.COLORMAP_PLASMA,
    "turbo": cv2.COLORMAP_TURBO,
    "jet": cv2.COLORMAP_JET,
    "hot": cv2.COLORMAP_HOT,
}


@lru_cache(maxsize=1)
def camera_palettes() -> dict:
    """name -> 256x3 RGB uint8, as used by the camera firmware."""
    out = {}
    if ASSETS.exists():
        a = np.load(ASSETS)
        for k in a.files:
            if k.startswith("palette_"):
                out[k[len("palette_"):]] = a[k]
    if "white_hot" in out:
        out["black_hot"] = out["white_hot"][::-1].copy()
    return out


@lru_cache(maxsize=None)
def display_palette(name: str) -> np.ndarray:
    """256x3 BGR lookup table for rendering."""
    cams = camera_palettes()
    if name in cams:
        return cams[name][:, ::-1].copy()
    if name in _CV_MAPS:
        ramp = np.arange(256, dtype=np.uint8).reshape(-1, 1)
        return cv2.applyColorMap(ramp, _CV_MAPS[name]).reshape(256, 3)
    if name == "gray":
        g = np.arange(256, dtype=np.uint8)
        return np.stack([g, g, g], 1)
    raise KeyError(name)


def display_palette_names() -> list:
    return sorted(camera_palettes()) + list(_CV_MAPS) + ["gray"]


def colorbar(name: str, height: int, width: int = 16) -> np.ndarray:
    lut = display_palette(name)
    idx = np.linspace(255, 0, height).astype(np.uint8)
    return np.repeat(lut[idx][:, None, :], width, 1)
