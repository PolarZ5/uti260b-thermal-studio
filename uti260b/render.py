"""Colourises a decoded frame for display."""
import numpy as np

from .decoder import ThermalFrame
from .palettes import display_palette, display_palette_names


def palette_for(frame: ThermalFrame, name: str) -> str:
    if name != "original":
        return name
    return frame.palette if frame.palette in display_palette_names() else "iron"


def base_image(frame: ThermalFrame, palette: str = "original", clean: bool = False,
               span=None) -> np.ndarray:
    """BGR image at frame resolution.

    palette 'original' without clean shows the camera screen unchanged.
    span=(lo, hi) locks the colour scale to fixed temperatures.
    """
    if palette == "original" and not clean:
        return frame.screen.copy()
    lut = display_palette(palette_for(frame, palette))
    if span is not None and frame.has_scale:
        lo, hi = span
        t = frame.filled_temps()
        idx = np.clip((t - lo) / max(1e-6, hi - lo) * 255, 0, 255).astype(np.uint8)
    else:
        idx = np.clip(frame.filled_index().astype(np.int32) * 255 // 254, 0, 255).astype(np.uint8)
    return lut[idx]


def display_span(frame: ThermalFrame, span):
    """Temperatures at the bottom/top of the displayed colour scale."""
    if span is not None and frame.has_scale:
        return span
    return frame.t_min, frame.t_max
