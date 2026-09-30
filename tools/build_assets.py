"""Builds uti260b/assets.npz from camera BMP files with known labels.

Extracts:
  * the camera palettes embedded in the BMPs
  * binary glyph templates of the digits used for the max/min labels next
    to the on-screen colour bar (used by uti260b.osd to read the range)

Usage:  python tools/build_assets.py
"""
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from uti260b import layout                     # noqa: E402
from uti260b.bmpfile import read_uti_bmp      # noqa: E402
from uti260b.osd import (CENTER_BAND, MAX_BAND, _big_glyph,  # noqa: E402
                         big_number_glyphs, cell_masks)
import cv2                                    # noqa: E402

SAMPLES = ROOT / "samples"
# Palette name by the camera's palette of each sample
PALETTE_OF = {
    "IMG_Typical.bmp": "iron",
    "IMG_LargeRange.bmp": "white_hot",
    "IMG_ROI.bmp": "rainbow",
}


# Large top-left readings visible in each screen: (band, text)
BIG_TRUTH = {
    "IMG_Fahrenheit.bmp": [(CENTER_BAND, "69.2")],
    "IMG_LargeRange.bmp": [(CENTER_BAND, "77.1"), (MAX_BAND, "150.0")],
    "IMG_NegativeTemp.bmp": [(CENTER_BAND, "7.0")],
    "IMG_ROI.bmp": [(CENTER_BAND, "59.5")],
    "IMG_ROI_Temps.bmp": [(CENTER_BAND, "33.0")],
    "IMG_Typical.bmp": [(MAX_BAND, "83.0")],
    "live_center31.5_max41.2.png": [(CENTER_BAND, "31.5"), (MAX_BAND, "41.2")],
}


# Live frames from the camera with their colour-bar labels: (max, min)
LIVE_LABELS = {
    "live_center31.5_max41.2.png": (41.2, 26.5),
    "live_max41.3_min26.7.png": (41.3, 26.7),
    "live_max41.3_min26.4.png": (41.3, 26.4),
}


def big_glyphs(screen, truth, out):
    for band, text in truth:
        items, _ = big_number_glyphs(screen, band)
        digits = [c for kind, c in (items or []) if kind == "digit"]
        want = [ch for ch in text if ch.isdigit()]
        if len(digits) != len(want):
            print(f"  skip {text}: found {len(digits)} digit glyphs")
            continue
        for ch, c in zip(want, digits):
            out.setdefault(ch, []).append(_big_glyph(c).astype(np.float32))


def label_text(value: float) -> str:
    return f"{value:.1f}"


def main():
    palettes = {}
    glyphs = {}
    big = {}
    for path in sorted(SAMPLES.glob("*.png")):
        screen = cv2.imread(str(path))[:320]
        if path.name in BIG_TRUTH:
            big_glyphs(screen, BIG_TRUTH[path.name], big)
        if path.name in LIVE_LABELS:
            t_max, t_min = LIVE_LABELS[path.name]
            for rows, value in ((layout.LABEL_MAX_Y, t_max), (layout.LABEL_MIN_Y, t_min)):
                for ch, m in zip(reversed(label_text(value)), cell_masks(screen, rows)):
                    glyphs.setdefault(ch, []).append(m.astype(np.float32))
    for path in sorted(SAMPLES.glob("*.bmp")):
        bmp = read_uti_bmp(path)
        if path.name in BIG_TRUTH:
            big_glyphs(bmp.screen_bgr, BIG_TRUTH[path.name], big)
        if path.name in PALETTE_OF:
            palettes[PALETTE_OF[path.name]] = bmp.palette_rgb
        for rows, value in ((layout.LABEL_MAX_Y, bmp.t_max), (layout.LABEL_MIN_Y, bmp.t_min)):
            text = label_text(value)
            masks = cell_masks(bmp.screen_bgr, rows)
            # cells are right to left
            for ch, m in zip(reversed(text), masks):
                glyphs.setdefault(ch, []).append(m.astype(np.float32))

    # keep every example: nearest-neighbour matching is more robust than averages
    tmpl_chars = [c for c in sorted(glyphs) if c != "." for _ in glyphs[c]]
    templates = np.stack([g for c in sorted(glyphs) if c != "." for g in glyphs[c]])
    big_chars = [c for c in sorted(big) for _ in big[c]]
    big_templates = np.stack([g for c in sorted(big) for g in big[c]])
    out = ROOT / "uti260b" / "assets.npz"
    np.savez_compressed(
        out,
        glyph_chars=np.array(tmpl_chars),
        glyph_templates=templates,
        big_glyph_chars=np.array(big_chars),
        big_glyph_templates=big_templates,
        **{f"palette_{k}": v for k, v in palettes.items()},
    )
    print("big glyphs:", {c: len(big[c]) for c in sorted(big)})
    print("palettes:", sorted(palettes))
    print("glyphs:", {c: len(glyphs[c]) for c in sorted(glyphs) if c != "."})
    missing = set("0123456789-") - set(tmpl_chars)
    if missing:
        print("WARNING: missing glyphs:", "".join(sorted(missing)))
    print("wrote", out)


if __name__ == "__main__":
    main()
