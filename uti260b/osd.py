"""Reads the max/min temperature labels drawn next to the on-screen colour bar.

The camera auto-ranges its palette between the scene minimum and maximum and
prints those two values above/below the colour bar. Reading them from the
live frame gives the temperature scale needed to turn palette colours back
into temperatures.
"""
from functools import lru_cache
from pathlib import Path

import numpy as np

from . import layout

GLYPH_H = 13
GLYPH_W = 12
ASSETS = Path(__file__).with_name("assets.npz")


def _luma(bgr: np.ndarray) -> np.ndarray:
    b, g, r = (bgr[..., i].astype(np.float32) for i in range(3))
    return 0.114 * b + 0.587 * g + 0.299 * r


def _ink(region_bgr: np.ndarray, level: float) -> np.ndarray:
    # Luma only: USB YUYV video halves the chroma resolution, which tints the
    # white strokes with the colour of the neighbouring background.
    return _luma(region_bgr) >= level


def _ink_level(label_bgr: np.ndarray) -> float:
    """White text sits on a translucent dark box; threshold relative to the box."""
    bg = float(np.median(_luma(label_bgr)))
    return min(225.0, max(150.0, bg + 60.0))


def _center_glyph(mask: np.ndarray) -> np.ndarray:
    """Places the ink of one cell horizontally centred on a GLYPH_H x GLYPH_W canvas."""
    out = np.zeros((GLYPH_H, GLYPH_W), bool)
    cols = np.where(mask.any(0))[0]
    if len(cols) == 0:
        return out
    ink = mask[:, cols[0]:cols[-1] + 1][:, :GLYPH_W]
    x = (GLYPH_W - ink.shape[1]) // 2
    out[:, x:x + ink.shape[1]] = ink[:GLYPH_H]
    return out


def _is_minus(mask: np.ndarray) -> bool:
    """A minus is one short horizontal stroke at mid height, nothing else in the cell."""
    rows = np.where(mask.any(1))[0]
    cols = np.where(mask.any(0))[0]
    return (len(rows) > 0 and rows[-1] - rows[0] <= 2 and 4 <= rows[0] <= 9
            and cols[-1] - cols[0] >= 3)


def cell_masks(screen_bgr: np.ndarray, rows) -> list:
    """Binary glyph masks of the label cells, right to left (dot cell included)."""
    y0, y1 = rows
    x_left = layout.LABEL_CELLS[3][0]
    level = _ink_level(screen_bgr[y0:y1, x_left:layout.LABEL_CELLS[0][1]])
    masks = []
    for x0, x1 in layout.LABEL_CELLS:
        masks.append(_center_glyph(_ink(screen_bgr[y0:y1, x0:x1], level)))
    return masks


@lru_cache(maxsize=1)
def _templates():
    if not ASSETS.exists():
        return None, None
    a = np.load(ASSETS)
    return list(a["glyph_chars"]), a["glyph_templates"]


def read_label(screen_bgr: np.ndarray, rows, max_dist: float = 0.14):
    """Returns (value, confidence) or (None, 0.0) if the label is unreadable."""
    chars, templates = _templates()
    if chars is None:
        return None, 0.0
    masks = cell_masks(screen_bgr, rows)
    text = []
    worst = 0.0
    for i, m in enumerate(masks):
        if i == layout.DOT_CELL:
            if m.sum() < 1:
                return None, 0.0
            text.append(".")
            continue
        if m.sum() < 4:
            break                       # blank cell: start of the number
        d = np.abs(templates - m[None].astype(np.float32)).mean((1, 2))
        k = int(d.argmin())
        # leading digits (tens and beyond) must match closely: background
        # clutter left of a short number can look like a faint '1'
        limit = max_dist if i <= layout.DOT_CELL + 2 else 0.08
        if d[k] > limit:
            if i <= layout.DOT_CELL + 1:
                return None, 0.0        # the mandatory digits must be clean
            break                       # background clutter left of the number
        if chars[k] == "-" and not _is_minus(m):
            break                       # clutter left of the number, not a minus sign
        worst = max(worst, float(d[k]))
        text.append(chars[k])
    s = "".join(reversed(text))
    if s.count("-") > 1 or ("-" in s and not s.startswith("-")):
        return None, 0.0
    try:
        value = float(s)
    except ValueError:
        return None, 0.0
    return value, max(0.0, 1.0 - worst / max_dist)


def read_range(screen_bgr: np.ndarray):
    """Returns (t_min, t_max, confidence) read from a 240x320 screen frame."""
    t_max, c1 = read_label(screen_bgr, layout.LABEL_MAX_Y)
    t_min, c2 = read_label(screen_bgr, layout.LABEL_MIN_Y)
    if t_max is None or t_min is None or t_max < t_min:
        return None, None, 0.0
    if not (-60 <= t_min <= 1100 and -60 <= t_max <= 1100):   # up to 550 C / 1022 F
        return None, None, 0.0
    return t_min, t_max, min(c1, c2)


# ---------------------------------------------------------------------------
# Large readings in the top-left corner: "+ 31.5°C" (centre spot) on the first
# line, "Max 41.2°C" on the second. Digits are 17 px tall, fixed size.
BIG_H = 17
BIG_W = 14
CENTER_BAND = (4, 34)
MAX_BAND = (36, 66)


def _components(screen_bgr, band, x1=150):
    y0, y1 = band
    reg = screen_bgr[y0:y1, :x1]
    g = _luma(reg)
    level = min(225.0, max(150.0, float(np.median(g)) + 60.0))
    mask = (g >= level).astype(np.uint8)
    import cv2
    n, lab, st, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    comps = []
    for i in range(1, n):
        x, y, w, h, a = st[i]
        if a >= 3:
            comps.append({"x": int(x), "y": int(y + y0), "w": int(w), "h": int(h), "a": int(a),
                          "mask": lab[y:y + h, x:x + w] == i})
    return sorted(comps, key=lambda c: c["x"])


def _big_glyph(c) -> np.ndarray:
    out = np.zeros((BIG_H, BIG_W), bool)
    m = c["mask"][:BIG_H, :BIG_W]
    x = (BIG_W - m.shape[1]) // 2
    out[:m.shape[0], x:x + m.shape[1]] = m
    return out


def big_number_glyphs(screen_bgr, band):
    """Components making up the number before the degree sign, left to right,
    each tagged 'digit', '.' or '-'. Returns (items, prefix_components) or (None, None)."""
    comps = _components(screen_bgr, band)
    digits_top = None
    deg = None
    for i, c in enumerate(comps):
        if c["h"] >= 15:
            digits_top = c["y"] if digits_top is None else min(digits_top, c["y"])
    if digits_top is None:
        return None, None
    for i, c in enumerate(comps[:-1]):
        nxt = comps[i + 1]
        if (c["w"] <= 9 and c["h"] <= 9 and abs(c["y"] - digits_top) <= 2 and nxt["h"] >= 15
                and 0 <= nxt["x"] - (c["x"] + c["w"]) <= 6):
            deg = i                                     # '°' followed by 'C'/'F'
            break
    if deg is None:
        return None, None
    items = []
    right = comps[deg]["x"]
    j = deg - 1
    while j >= 0:
        c = comps[j]
        if right - (c["x"] + c["w"]) > 9:
            break
        if c["h"] >= 15:
            kind = "digit"
        elif c["w"] <= 4 and c["h"] <= 4 and c["y"] >= digits_top + 12:
            kind = "."
        elif c["h"] <= 3 and c["w"] >= 5 and digits_top + 5 <= c["y"] <= digits_top + 11:
            kind = "-"
        else:
            break
        items.append((kind, c))
        right = c["x"]
        j -= 1
    items.reverse()
    return items, comps[:j + 1]


@lru_cache(maxsize=1)
def _big_templates():
    if not ASSETS.exists():
        return None, None
    a = np.load(ASSETS)
    if "big_glyph_chars" not in a.files:
        return None, None
    return list(a["big_glyph_chars"]), a["big_glyph_templates"]


def read_big_number(screen_bgr, band, max_dist: float = 0.16):
    """Reads e.g. '31.5' from a line like '+ 31.5°C'. Returns (value, prefix) or (None, None).
    prefix: 'center' (solid + icon), 'point' (dashed icon), 'max' ('Max' text) or 'unknown'."""
    chars, templates = _big_templates()
    if chars is None:
        return None, None
    items, prefix = big_number_glyphs(screen_bgr, band)
    if not items:
        return None, None
    text = ""
    for kind, c in items:
        if kind != "digit":
            text += kind
            continue
        g = _big_glyph(c).astype(np.float32)
        d = np.abs(templates - g[None]).mean((1, 2))
        k = int(d.argmin())
        if d[k] > max_dist:
            return None, None
        text += chars[k]
    if (text.count(".") != 1 or text.endswith(".") or text.count("-") > 1
            or ("-" in text and not text.startswith("-"))):
        return None, None
    try:
        value = float(text)
    except ValueError:
        return None, None
    return value, _prefix_kind(prefix)


def _prefix_kind(prefix) -> str:
    left = [c for c in prefix if c["x"] < 36]
    if (any(c["h"] in (11, 12, 13) and c["w"] >= 9 and c["x"] < 6 for c in left)
            and sum(1 for c in left if 7 <= c["h"] <= 10) >= 2):
        return "max"                                    # 'M' 'a' 'x'
    thin = [c for c in left if min(c["w"], c["h"]) <= 2 and max(c["w"], c["h"]) >= 7]
    if len(thin) >= 3:
        return "point"                                  # dashed crosshair icon
    return "center"


def read_center(screen_bgr):
    """The camera's own centre-spot reading, or None."""
    v, kind = read_big_number(screen_bgr, CENTER_BAND)
    return v if kind == "center" else None
