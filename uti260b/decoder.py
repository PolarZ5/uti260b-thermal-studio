"""Turns UTi260B video frames into per-pixel temperatures.

The "PC Camera" stream carries the camera screen as colour video, not raw
sensor data. Decoding therefore works backwards from what is on screen:

  1. find the colour bar -> which palette the camera is using
  2. map every pixel colour back to its palette index (0..254)
  3. read the max/min labels next to the bar (or use a manual range)
  4. temperature = min + (max - min) * index / 254

Pixels covered by the on-screen display (text, crosshairs, icons) or whose
colour is not in the palette are marked NaN and excluded from measurements.

Accuracy note: the camera applies contrast enhancement before colouring, so
the index is not exactly linear in temperature. Max/min are exact (they are
the camera's own readings), values in between can be off by several degrees
in scenes with a wide temperature span. Use a narrow scene span, or the
camera's saved BMP files, for the best results.
"""
from dataclasses import dataclass, field
import time
from typing import Callable, Optional

import cv2
import numpy as np

from . import layout
from .bmpfile import UtiBmp
from .markers import find_markers
from .osd import read_center, read_label, read_range
from .palettes import camera_palettes

ROTATIONS = {
    0: None,
    90: cv2.ROTATE_90_CLOCKWISE,
    180: cv2.ROTATE_180,
    270: cv2.ROTATE_90_COUNTERCLOCKWISE,
}


@dataclass
class ThermalFrame:
    screen: np.ndarray                  # BGR frame, orientation normalised
    index: np.ndarray                   # float32 palette index 0..254, NaN = not measurable
    temps: np.ndarray                   # float32 temperatures, NaN = not measurable
    t_min: Optional[float]
    t_max: Optional[float]
    range_source: str                   # osd | manual | hold | bmp | none
    palette: str                        # camera palette in use ('bar' = read from colour bar)
    layout: str                         # screen | raw | bmp
    unit: str = "C"
    center_temp: Optional[float] = None  # camera's own centre reading (BMP only)
    menu_open: bool = False             # camera menu bar covers the bottom of the screen
    hot_xy: Optional[tuple] = None      # camera's hot-spot tracker (red brackets)
    cold_xy: Optional[tuple] = None     # camera's cold-spot tracker (green brackets)
    cam_points: dict = field(default_factory=dict)   # camera Point Temperature n -> (x, y, temp)
    calibration: list = field(default_factory=list)  # [(index, temp)] used for the mapping
    timestamp: float = field(default_factory=time.time)
    index_to_temp: Optional[Callable] = None
    _filled: Optional[np.ndarray] = None

    @property
    def has_scale(self) -> bool:
        return self.t_min is not None and self.t_max is not None

    @property
    def shape(self):
        return self.index.shape

    def filled_index(self) -> np.ndarray:
        """uint8 index with masked pixels inpainted (for clean display)."""
        if self._filled is None:
            bad = np.isnan(self.index)
            idx8 = np.nan_to_num(self.index, nan=0).clip(0, 255).astype(np.uint8)
            if bad.any() and not bad.all():
                idx8 = cv2.inpaint(idx8, bad.astype(np.uint8), 3, cv2.INPAINT_TELEA)
            self._filled = idx8
        return self._filled

    def filled_temps(self) -> Optional[np.ndarray]:
        if not self.has_scale:
            return None
        return self.index_to_temp(self.filled_index().astype(np.float32))

    def temp_at(self, x: int, y: int, radius: int = 1) -> Optional[float]:
        h, w = self.temps.shape
        x0, x1 = max(0, x - radius), min(w, x + radius + 1)
        y0, y1 = max(0, y - radius), min(h, y + radius + 1)
        if x0 >= x1 or y0 >= y1:
            return None
        patch = self.temps[y0:y1, x0:x1]
        if np.isnan(patch).all():
            return None
        return float(np.nanmean(patch))

    def stats(self, rect=None) -> Optional[dict]:
        """max/min/mean (+ positions) over rect=(x0, y0, x1, y1) or the whole frame."""
        t = self.temps
        ox = oy = 0
        if rect is not None:
            x0, y0, x1, y1 = rect
            x0, x1 = sorted((int(x0), int(x1)))
            y0, y1 = sorted((int(y0), int(y1)))
            h, w = t.shape
            x0, y0 = max(0, x0), max(0, y0)
            x1, y1 = min(w, x1), min(h, y1)
            if x1 - x0 < 1 or y1 - y0 < 1:
                return None
            t = t[y0:y1, x0:x1]
            ox, oy = x0, y0
        if np.isnan(t).all():
            return None
        imax = np.nanargmax(t)
        imin = np.nanargmin(t)
        ymax, xmax = np.unravel_index(imax, t.shape)
        ymin, xmin = np.unravel_index(imin, t.shape)
        return {
            "max": float(t.flat[imax]), "max_xy": (int(xmax + ox), int(ymax + oy)),
            "min": float(t.flat[imin]), "min_xy": (int(xmin + ox), int(ymin + oy)),
            "mean": float(np.nanmean(t)),
        }


def _rgb565_keys(bgr: np.ndarray) -> np.ndarray:
    b = bgr[..., 0].astype(np.uint16) >> 3
    g = bgr[..., 1].astype(np.uint16) >> 2
    r = bgr[..., 2].astype(np.uint16) >> 3
    return (r << 11) | (g << 5) | b


def _build_lut(palette_bgr: np.ndarray):
    """Nearest palette index and colour distance for all 65536 RGB565 colours."""
    keys = np.arange(65536, dtype=np.int32)
    colors = np.stack([
        (keys & 0x1F) * 255 // 31,          # B
        ((keys >> 5) & 0x3F) * 255 // 63,   # G
        ((keys >> 11) & 0x1F) * 255 // 31,  # R
    ], 1).astype(np.int32)
    pal = palette_bgr.astype(np.int32)[:255]            # indices 0..254 are used
    idx = np.empty(65536, np.uint8)
    dist = np.empty(65536, np.float32)
    for s in range(0, 65536, 4096):
        d = ((colors[s:s + 4096, None, :] - pal[None]) ** 2).sum(-1)
        k = d.argmin(1)
        idx[s:s + 4096] = k
        dist[s:s + 4096] = np.sqrt(d[np.arange(len(k)), k])
    return idx, dist


def _isotonic(ys, ws):
    """Pool-adjacent-violators: closest non-decreasing sequence (weighted)."""
    blocks = [[y, w, 1] for y, w in zip(ys, ws)]
    i = 0
    while i < len(blocks) - 1:
        if blocks[i][0] > blocks[i + 1][0]:
            y0, w0, n0 = blocks[i]
            y1, w1, n1 = blocks[i + 1]
            blocks[i] = [(y0 * w0 + y1 * w1) / (w0 + w1), w0 + w1, n0 + n1]
            del blocks[i + 1]
            i = max(0, i - 1)
        else:
            i += 1
    out = []
    for y, _, n in blocks:
        out += [y] * n
    return out


def calibration_map(points):
    """Monotone piecewise-linear index -> temperature through the given (index, temp) points."""
    pts = sorted(points)
    xs = np.array([q[0] for q in pts], np.float32)
    # the colour-bar ends are exact; interior points are pulled into order if they conflict
    ws = [100.0 if i in (0, len(pts) - 1) else 1.0 for i in range(len(pts))]
    ys = np.array(_isotonic([q[1] for q in pts], ws), np.float32)

    def to_temp(i):
        return np.interp(np.asarray(i, np.float32), xs, ys).astype(np.float32)
    return to_temp


class Decoder:
    def __init__(self):
        self.rotation = "auto"          # 'auto' or 0/90/180/270
        self.range_mode = "osd"         # 'osd' or 'manual'
        self.manual_range = (20.0, 40.0)
        self.unit = "C"
        self.max_color_dist = 32.0
        self.hold_seconds = 2.0
        self.menu_hold_seconds = 30.0
        # Use the camera's own centre reading (top-left) as a third calibration
        # point: the palette index is not linear in temperature.
        self.use_center_fix = True
        # Read the camera's hot/cold trackers and Point Temperature markers.
        self.use_camera_markers = True
        # The thermal image is upscaled and smooth; text, crosshairs and the
        # hot-spot tracker the camera draws on top have hard edges.
        self.detect_overlay = True
        self.edge_threshold = 70.0
        self.exclude_rects = []         # user-defined (x0, y0, x1, y1) regions to ignore
        self._auto_rot = None
        self._auto_rot_misses = 0
        self._luts = {}
        self._bar_palette = None
        self._raw_palette = None
        self._last_osd = None           # (t_min, t_max, time)

    # ---------------------------------------------------------------- layout
    @staticmethod
    def bar_score(screen: np.ndarray) -> float:
        """0..1: how much the frame looks like the camera screen with its colour bar."""
        if screen.shape[:2] != (layout.SCREEN_H, layout.SCREEN_W):
            return 0.0
        bar = screen[layout.BAR_TOP:layout.BAR_BOTTOM + 1, layout.BAR_X0 + 1:layout.BAR_X1 - 1].astype(np.int16)
        row_spread = (bar.max(1) - bar.min(1)).max(1)           # per row, across x
        uniform = (row_spread <= 14).mean()
        col = np.median(bar, 1)
        variation = np.abs(np.diff(col, axis=0)).sum() / len(col)
        left = screen[layout.BAR_TOP:layout.BAR_BOTTOM + 1, layout.BAR_X0 - 3].astype(np.int16)
        edge = np.abs(left - col).mean() > 6 or variation > 1.0
        return float(uniform) if (variation > 0.3 and edge) else 0.0

    @staticmethod
    def _strip_padding(frame: np.ndarray) -> np.ndarray:
        """The UVC stream is 240x321: one padding row (solid green) below the 240x320 screen."""
        h, w = frame.shape[:2]
        if w == layout.SCREEN_W and layout.SCREEN_H < h <= layout.SCREEN_H + 4:
            return frame[:layout.SCREEN_H]
        if h == layout.SCREEN_W and layout.SCREEN_H < w <= layout.SCREEN_H + 4:
            return frame[:, :layout.SCREEN_H]
        return frame

    def _to_screen(self, frame: np.ndarray, rot) -> np.ndarray:
        frame = self._strip_padding(frame)
        code = ROTATIONS.get(rot)
        img = cv2.rotate(frame, code) if code is not None else frame
        h, w = img.shape[:2]
        if (h, w) != (layout.SCREEN_H, layout.SCREEN_W) and abs(h / w - 4 / 3) < 0.02:
            img = cv2.resize(img, (layout.SCREEN_W, layout.SCREEN_H), interpolation=cv2.INTER_AREA)
        return img

    def normalise(self, frame: np.ndarray):
        """Returns (image, layout_name)."""
        if self.rotation != "auto":
            img = self._to_screen(frame, int(self.rotation))
            return img, ("screen" if self.bar_score(img) > 0.6 else "raw")
        if self._auto_rot is not None:
            img = self._to_screen(frame, self._auto_rot)
            if self.bar_score(img) > 0.6:
                self._auto_rot_misses = 0
                return img, "screen"
            self._auto_rot_misses += 1
            if self._auto_rot_misses < 25:
                return img, "screen"
            self._auto_rot = None
        best, best_rot = 0.0, None
        for rot in (0, 90, 270, 180):
            s = self.bar_score(self._to_screen(frame, rot))
            if s > best:
                best, best_rot = s, rot
        if best > 0.6:
            self._auto_rot, self._auto_rot_misses = best_rot, 0
            return self._to_screen(frame, best_rot), "screen"
        return frame, "raw"

    @staticmethod
    def menu_open(screen: np.ndarray) -> bool:
        """The camera's main menu is a dark bar with near-black borders at the bottom of the screen."""
        if screen.shape[:2] != (layout.SCREEN_H, layout.SCREEN_W):
            return False
        g = cv2.cvtColor(screen, cv2.COLOR_BGR2GRAY).astype(np.float32)
        rows = g[:, layout.MENU_X0:layout.MENU_X1].mean(1)
        top = rows[layout.MENU_TOP_EDGE[0]:layout.MENU_TOP_EDGE[1]].min()
        bottom = rows[layout.MENU_BOTTOM_EDGE[0]:layout.MENU_BOTTOM_EDGE[1]].min()
        band = rows[layout.MENU_TOP_EDGE[1]:layout.MENU_BOTTOM_EDGE[0]].mean()
        return bool(top < 25 and bottom < 25 and band < 95)

    # --------------------------------------------------------------- palette
    def _lut(self, name: str, palette_bgr: np.ndarray):
        key = (name, palette_bgr.tobytes())
        lut = self._luts.get(key)
        if lut is None:
            if len(self._luts) > 12:
                self._luts.clear()
            lut = self._luts[key] = _build_lut(palette_bgr)
        return lut

    def _palette_from_bar(self, screen: np.ndarray):
        bar = screen[layout.BAR_TOP:layout.BAR_BOTTOM + 1, layout.BAR_X0 + 1:layout.BAR_X1 - 1]
        col = np.median(bar, 1).astype(np.float32)                  # top (hot) .. bottom (cold)
        ys = np.arange(layout.BAR_TOP, layout.BAR_BOTTOM + 1)
        idx_of_row = 254.0 * (layout.BAR_BOTTOM - ys) / (layout.BAR_BOTTOM - layout.BAR_TOP)
        # compare with the known camera palettes
        best_name, best_err = None, 1e9
        ii = np.round(idx_of_row).astype(int)
        for name, rgb in camera_palettes().items():
            err = np.abs(rgb[ii][:, ::-1].astype(np.float32) - col).mean()
            if err < best_err:
                best_name, best_err = name, err
        if best_name is not None and best_err < 14:
            return best_name, camera_palettes()[best_name][:, ::-1].copy()
        # unknown palette: interpolate the bar itself into a 256 entry table
        order = np.argsort(idx_of_row)
        grid = np.arange(256, dtype=np.float32)
        pal = np.stack([np.interp(grid, idx_of_row[order], col[order, c]) for c in range(3)], 1)
        pal = np.round(pal).astype(np.uint8)
        if self._bar_palette is not None and np.abs(self._bar_palette.astype(int) - pal).mean() < 6:
            pal = self._bar_palette                                  # keep LUT cached
        self._bar_palette = pal
        return "bar", pal

    def _palette_for_raw(self, img: np.ndarray):
        if self._raw_palette is None or time.time() - self._raw_palette[2] > 3:
            sample = img[::8, ::8].reshape(-1, 3)
            keys = _rgb565_keys(sample)
            best = None
            for name, rgb in camera_palettes().items():
                _, dist = self._lut(name, rgb[:, ::-1].copy())
                err = float(np.median(dist[keys]))
                if best is None or err < best[0]:
                    best = (err, name)
            name = best[1] if best else "white_hot"
            self._raw_palette = (name, camera_palettes()[name][:, ::-1].copy(), time.time())
        return self._raw_palette[0], self._raw_palette[1]

    # ----------------------------------------------------------------- range
    def _range(self, screen, layout_name, menu=False):
        if self.range_mode == "manual":
            lo, hi = self.manual_range
            return float(lo), float(hi), "manual"
        if layout_name == "screen":
            lo, hi, conf = read_range(screen)
            now = time.time()
            if lo is not None:
                self._last_osd = (lo, hi, now)
                return lo, hi, "osd"
            last = self._last_osd
            if last and now - last[2] < self.hold_seconds:
                return last[0], last[1], "hold"
            if menu and last and now - last[2] < self.menu_hold_seconds:
                # the menu hides the min label: keep the last min, follow the (still visible) max
                t_max, _ = read_label(screen, layout.LABEL_MAX_Y)
                if t_max is not None and t_max >= last[0]:
                    return last[0], t_max, "partial"
        return None, None, "none"

    # ---------------------------------------------------------------- decode
    def decode(self, frame_bgr: np.ndarray) -> ThermalFrame:
        img, layout_name = self.normalise(frame_bgr)
        if layout_name == "screen":
            pal_name, pal = self._palette_from_bar(img)
        else:
            pal_name, pal = self._palette_for_raw(img)
        lut_idx, lut_dist = self._lut(pal_name, pal)
        keys = _rgb565_keys(img)
        index = lut_idx[keys].astype(np.float32)
        color_dist = lut_dist[keys]
        raw_index = np.where(color_dist <= self.max_color_dist, index, np.nan)
        bad = color_dist > self.max_color_dist
        if self.detect_overlay:
            y = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype(np.float32)
            grad = cv2.magnitude(cv2.Sobel(y, cv2.CV_32F, 1, 0), cv2.Sobel(y, cv2.CV_32F, 0, 1)) / 4
            bad = cv2.dilate(((grad > self.edge_threshold) | bad).astype(np.uint8), np.ones((3, 3), np.uint8)) > 0
        menu = layout_name == "screen" and self.menu_open(img)
        if layout_name == "screen":
            for x0, y0, x1, y1 in layout.OSD_MASK_RECTS:
                bad[y0:y1, x0:x1] = True
            if menu:
                bad[layout.MENU_MASK_Y0:, :] = True
        for x0, y0, x1, y1 in self.exclude_rects:
            bad[min(y0, y1):max(y0, y1), min(x0, x1):max(x0, x1)] = True
        index[bad] = np.nan

        t_min, t_max, src = self._range(img, layout_name, menu)
        t_center = None
        markers = None
        calib = []
        if t_min is not None:
            calib = [(0.0, t_min), (254.0, t_max)]
            camera_readings = layout_name == "screen" and src != "manual"
            if camera_readings and self.use_camera_markers:
                markers = find_markers(img, t_min, t_max)
            if camera_readings and self.use_center_fix:
                t_center = read_center(img)
                c = self._center_index(index)
                if t_center is not None and c is not None and t_min <= t_center <= t_max:
                    calib.append((c, t_center))
                else:
                    t_center = None
                if markers is not None:
                    for x, y, t in markers.points.values():
                        c = self._index_at(raw_index, x, y)
                        if c is not None and t_min <= t <= t_max:
                            calib.append((c, t))
            to_temp = calibration_map(calib)
            temps = to_temp(index)
        else:
            to_temp = None
            temps = np.full(index.shape, np.nan, np.float32)
        tf = ThermalFrame(img, index, temps, t_min, t_max, src, pal_name, layout_name,
                          unit=self.unit, center_temp=t_center, index_to_temp=to_temp, menu_open=menu,
                          calibration=calib)
        if markers is not None:
            tf.hot_xy, tf.cold_xy, tf.cam_points = markers.hot_xy, markers.cold_xy, dict(markers.points)
        return tf

    @staticmethod
    def _index_at(raw_index, x, y):
        """Palette index inside a point marker's hollow ring (2x2 pixels at its centre)."""
        patch = raw_index[max(0, y):y + 2, max(0, x):x + 2]
        if patch.size == 0 or np.isnan(patch).all():
            return None
        c = float(np.nanmedian(patch))
        return c if 0.5 <= c <= 253.5 else None

    @staticmethod
    def _center_index(index: np.ndarray):
        """Palette index at the centre spot, from the pixels around the camera's crosshair."""
        h, w = index.shape
        cy, cx = h // 2, w // 2
        for r in (2, 4, 6, 9):
            patch = index[cy - r:cy + r + 1, cx - r:cx + r + 1]
            if np.count_nonzero(~np.isnan(patch)) >= 6:
                c = float(np.nanmedian(patch))
                return c if 1.0 <= c <= 253.0 else None
        return None

    # ------------------------------------------------------------------ bmp
    @staticmethod
    def from_bmp(bmp: UtiBmp, use_fix: bool = True) -> ThermalFrame:
        raw = bmp.raw.astype(np.float32)
        temps = bmp.temperatures(use_fix)
        lo, hi, tc = bmp.t_min, bmp.t_max, bmp.t_center
        cx, cy = bmp.center_pos
        c = float(bmp.raw[cy, cx]) if use_fix and 0 <= cy < raw.shape[0] and 0 <= cx < raw.shape[1] else -1

        def to_temp(i, lo=lo, hi=hi, tc=tc, c=c):
            if 0 < c < 254:
                return np.where(i >= c, tc + (hi - tc) * (i - c) / (254.0 - c),
                                lo + (tc - lo) * i / c).astype(np.float32)
            return (lo + (hi - lo) * i / 254.0).astype(np.float32)

        name = "bmp"
        for k, rgb in camera_palettes().items():
            if np.array_equal(rgb, bmp.palette_rgb):
                name = k
        return ThermalFrame(bmp.screen_bgr, raw, temps.astype(np.float32), lo, hi, "bmp", name, "bmp",
                            unit=bmp.unit, center_temp=tc, index_to_temp=to_temp)
