"""Finds the camera's own measurement markers on the screen and reads their values.

* hot tracker   - red corner brackets around the hottest point
* cold tracker  - green corner brackets around the coldest point
* point 1..3    - "Point Temperature": small white ring with a dashed cross,
                  the point number at its top-left and the temperature label
                  (small font, translucent box) next to it

Temperature labels anywhere in the scene are read with the same glyph
templates as the colour-bar labels.
"""
from dataclasses import dataclass, field
from typing import Optional

import cv2
import numpy as np

from . import layout
from .osd import GLYPH_H, GLYPH_W, _luma, _templates

SCENE_Y0 = 34                    # below the top bar
SCENE_X1 = 220                   # left of the colour bar


@dataclass
class Label:
    value: float
    x0: int
    y0: int
    x1: int
    y1: int

    @property
    def center(self):
        return ((self.x0 + self.x1) / 2, (self.y0 + self.y1) / 2)


@dataclass
class CameraMarkers:
    hot_xy: Optional[tuple] = None
    cold_xy: Optional[tuple] = None
    points: dict = field(default_factory=dict)      # n -> (x, y, temp)
    labels: list = field(default_factory=list)


# ------------------------------------------------------------------ labels
def _ink_mask(screen_bgr):
    g = _luma(screen_bgr)
    bg = cv2.blur(g, (15, 15))
    return ((g >= bg + 45) & (g >= 150)).astype(np.uint8), g


def _glyph_from_component(mask) -> np.ndarray:
    """Places a component's ink like a label cell: top at row 0, centred horizontally."""
    out = np.zeros((GLYPH_H, GLYPH_W), bool)
    h, w = mask.shape
    h, w = min(h, GLYPH_H), min(w, GLYPH_W)
    x = (GLYPH_W - w) // 2
    out[:h, x:x + w] = mask[:h, :w]
    return out


def find_labels(screen_bgr, max_dist: float = 0.15) -> list:
    """All small-font numbers like '26.4' in the scene area."""
    chars, templates = _templates()
    if chars is None:
        return []
    ink, _ = _ink_mask(screen_bgr)
    ink[:SCENE_Y0] = 0
    n, lab, st, _ = cv2.connectedComponentsWithStats(ink, connectivity=8)
    comps = []
    for i in range(1, n):
        x, y, w, h, a = (int(v) for v in st[i])
        if 9 <= h <= 12 and 3 <= w <= 9:
            kind = "digit"
        elif h <= 3 and w <= 3 and a >= 2:
            kind = "."
        elif h <= 2 and 4 <= w <= 8:
            kind = "-"
        else:
            continue
        comps.append({"kind": kind, "x": x, "y": y, "w": w, "h": h, "i": i})
    digits = [c for c in comps if c["kind"] == "digit"]
    used = set()
    labels = []
    for c in sorted(digits, key=lambda c: (c["y"], c["x"])):
        if c["i"] in used:
            continue
        top = c["y"]
        line = [d for d in comps if d["i"] not in used and
                ((d["kind"] == "digit" and abs(d["y"] - top) <= 2) or
                 (d["kind"] == "." and top + 8 <= d["y"] <= top + 12) or
                 (d["kind"] == "-" and top + 3 <= d["y"] <= top + 7))]
        line.sort(key=lambda d: d["x"])
        # chain from c to the right / left with small gaps
        k = line.index(c)
        group = [c]
        for step in (1, -1):
            j = k + step
            edge = c
            while 0 <= j < len(line):
                d = line[j]
                gap = d["x"] - (edge["x"] + edge["w"]) if step == 1 else edge["x"] - (d["x"] + d["w"])
                if gap > 4:
                    break
                group.append(d)
                edge = d
                j += step
        group.sort(key=lambda d: d["x"])
        text = ""
        ok = True
        for d in group:
            if d["kind"] == ".":
                text += "."
            elif d["kind"] == "-":
                text += "-"
            else:
                m = _glyph_from_component(lab[d["y"]:d["y"] + d["h"], d["x"]:d["x"] + d["w"]] == d["i"])
                dist = np.abs(templates - m[None].astype(np.float32)).mean((1, 2))
                kk = int(dist.argmin())
                if dist[kk] > max_dist or chars[kk] == "-":
                    ok = False
                    break
                text += chars[kk]
        for d in group:
            used.add(d["i"])
        if not ok or text.count(".") != 1 or not text.split(".")[-1].isdigit() or len(text.split(".")[-1]) != 1:
            continue
        if text.startswith("-"):
            m = [d for d in group if d["kind"] == "-"]
            if not m or m[0] is not group[0]:
                continue
        try:
            v = float(text)
        except ValueError:
            continue
        x0 = min(d["x"] for d in group)
        x1 = max(d["x"] + d["w"] for d in group)
        labels.append(Label(v, x0, top, x1, top + c["h"]))
    return labels


# ----------------------------------------------------------------- trackers
def _bracket_center(screen_bgr, color):
    """Centre of the red/green corner brackets: 3-5 small saturated pieces
    (4 corners + a small cross) arranged in a ~24 px square."""
    b, g, r = (screen_bgr[..., i].astype(np.int16) for i in range(3))
    if color == "red":
        m = (r >= 200) & (g <= 60) & (b <= 60)
    else:
        m = (g >= 190) & (r <= 90) & (b <= 90)
    m[:SCENE_Y0] = False
    m[:, SCENE_X1:] = False
    n, lab, st, cen = cv2.connectedComponentsWithStats(m.astype(np.uint8), connectivity=8)
    parts = [i for i in range(1, n) if 3 <= st[i, 2] <= 20 and 3 <= st[i, 3] <= 20 and 6 <= st[i, 4] <= 90]
    best = None
    for i in parts:
        cx, cy = cen[i]
        group = [j for j in parts if abs(cen[j][0] - cx) <= 26 and abs(cen[j][1] - cy) <= 26]
        x0 = min(st[j, 0] for j in group)
        y0 = min(st[j, 1] for j in group)
        x1 = max(st[j, 0] + st[j, 2] for j in group)
        y1 = max(st[j, 1] + st[j, 3] for j in group)
        w, h = x1 - x0, y1 - y0
        if len(group) >= 3 and 14 <= w <= 30 and 14 <= h <= 30 and abs(w - h) <= 6:
            score = len(group) - abs(w - h) * 0.1
            if best is None or score > best[0]:
                best = (score, (x0 + x1 - 1) / 2, (y0 + y1 - 1) / 2)
    if best is None:
        return None
    return int(round(best[1])), int(round(best[2]))


# ------------------------------------------------------------------ points
def _ring_template():
    t = np.zeros((12, 12), np.float32)
    yy, xx = np.mgrid[0:12, 0:12]
    d = np.hypot(xx - 5.5, yy - 5.5)
    t[(d >= 2.6) & (d <= 4.2)] = 1.0
    return t


RING = _ring_template()


def _ring_ok(ink, cx, cy) -> bool:
    """A point marker has a hollow centre, a clear gap ~5 px out and dashed
    arms 7-11 px out; a digit loop inside a label has none of these."""
    H, W = ink.shape
    c0 = int(np.floor(cx - 0.5))            # the ring centre falls between two pixels
    r0 = int(np.floor(cy - 0.5))

    def px(x, y):
        return int(ink[y, x]) if 0 <= x < W and 0 <= y < H else 0

    if any(px(c0 + dx, r0 + dy) for dx in (0, 1) for dy in (0, 1)):
        return False

    def ray(direction, r):
        if direction == "up":
            return max(px(c0, int(round(cy - r))), px(c0 + 1, int(round(cy - r))))
        if direction == "down":
            return max(px(c0, int(round(cy + r))), px(c0 + 1, int(round(cy + r))))
        if direction == "left":
            return max(px(int(round(cx - r)), r0), px(int(round(cx - r)), r0 + 1))
        return max(px(int(round(cx + r)), r0), px(int(round(cx + r)), r0 + 1))

    arms = {}
    for d in ("up", "down", "left", "right"):
        gap = ray(d, 5) == 0 or ray(d, 5.5) == 0
        arm = sum(ray(d, r) for r in (7, 8, 9, 10, 11)) >= 2
        arms[d] = (gap, arm)
    if sum(g for g, _ in arms.values()) < 3:
        return False
    vertical = arms["up"][1] + arms["down"][1]
    horizontal = arms["left"][1] + arms["right"][1]
    return vertical == 2 or (vertical + horizontal >= 3)


def find_rings(screen_bgr, thresh: float = 0.55) -> list:
    ink, _ = _ink_mask(screen_bgr)
    ink[:SCENE_Y0] = 0
    ink[:, SCENE_X1:] = 0
    res = cv2.matchTemplate(ink.astype(np.float32), RING, cv2.TM_CCOEFF_NORMED)
    out = []
    while True:
        _, v, _, (x, y) = cv2.minMaxLoc(res)
        if v < thresh:
            break
        cx, cy = x + 5.5, y + 5.5
        res[max(0, y - 6):y + 7, max(0, x - 6):x + 7] = -1
        if _ring_ok(ink, cx, cy):
            out.append((cx, cy))
    return out


def _point_number(screen_bgr, cx, cy):
    """Reads the 1/2/3 drawn at the top-left of a point ring."""
    chars, templates = _templates()
    ink, _ = _ink_mask(screen_bgr)
    x0, x1 = int(cx) - 16, int(cx) - 3
    y0, y1 = int(cy) - 15, int(cy) + 1
    if x0 < 0 or y0 < 0:
        return None
    reg = ink[y0:y1, x0:x1]
    n, lab, st, _ = cv2.connectedComponentsWithStats(reg, connectivity=8)
    best = None
    for i in range(1, n):
        x, y, w, h, a = st[i]
        if 9 <= h <= 13 and 2 <= w <= 9:
            m = _glyph_from_component(lab[y:y + h, x:x + w] == i)
            d = np.abs(templates - m[None].astype(np.float32)).mean((1, 2))
            for k in np.argsort(d):
                if chars[k] in "123":
                    if best is None or d[k] < best[1]:
                        best = (int(chars[k]), float(d[k]))
                    break
    return best[0] if best and best[1] < 0.2 else None


# ------------------------------------------------------------------- main
def find_markers(screen_bgr, t_min=None, t_max=None, center=None) -> CameraMarkers:
    cm = CameraMarkers()
    if screen_bgr.shape[:2] != (layout.SCREEN_H, layout.SCREEN_W):
        return cm
    cm.hot_xy = _bracket_center(screen_bgr, "red")
    cm.cold_xy = _bracket_center(screen_bgr, "green")
    labels = find_labels(screen_bgr)
    cm.labels = labels
    # labels that belong to the trackers or the colour bar are not point readings
    free = []
    for lb in labels:
        if lb.x0 >= 180 and (lb.y0 < 58 or lb.y0 > 250):
            continue                                        # colour-bar max/min labels
        near_tracker = False
        for xy, val in ((cm.hot_xy, t_max), (cm.cold_xy, t_min)):
            if xy and val is not None and abs(lb.value - val) < 0.05:
                cx, cy = lb.center
                if abs(cx - xy[0]) < 45 and abs(cy - xy[1]) < 20:
                    near_tracker = True
        if not near_tracker:
            free.append(lb)
    rings = find_rings(screen_bgr)
    taken = set()
    for k, (cx, cy) in enumerate(sorted(rings, key=lambda p: p[0])):
        cand = []
        for j, lb in enumerate(free):
            if j in taken:
                continue
            lx, ly = lb.center
            # label box sits beside the ring, usually below-right
            if abs(ly - cy) <= 24 and abs(lx - cx) <= 45:
                cand.append((abs(ly - (cy + 12)) + 0.3 * abs(lx - (cx + 22)), j))
        if not cand:
            continue
        _, j = min(cand)
        taken.add(j)
        num = _point_number(screen_bgr, cx, cy)
        if num is None or num in cm.points:
            num = next(i for i in (1, 2, 3, 4, 5, 6) if i not in cm.points)
        cm.points[num] = (int(round(cx - 0.5)), int(round(cy - 0.5)), free[j].value)
    return cm
