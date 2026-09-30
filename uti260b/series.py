"""Time-series recording of measurements, with CSV export.

The column layout is fixed so a CSV can be written while recording:
spots occupy slots P1..P6, each with its own x/y columns, because spots can
be added or removed in the middle of a session.
"""
import csv
from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np

from .measure import MAX_SPOTS, Measurement

SPOT_KEYS = [f"P{i}" for i in range(1, MAX_SPOTS + 1)]
CAM_KEYS = ["cam1", "cam2", "cam3"]              # the camera's own Point Temperature 1..3
COLUMNS = (["time", "elapsed_s", "unit", "scale_min", "scale_max", "scale_source",
            "max", "max_x", "max_y", "min", "min_x", "min_y", "mean", "center",
            "roi_max", "roi_min", "roi_mean"]
           + [c for k in SPOT_KEYS for c in (k, f"{k}_x", f"{k}_y")]
           + [c for k in CAM_KEYS for c in (k, f"{k}_x", f"{k}_y")])
NUMERIC = [c for c in COLUMNS if c not in ("time", "unit", "scale_source")]
PLOT_KEYS = ["max", "min", "center", "mean", "roi_max", "roi_min", "roi_mean"] + SPOT_KEYS + CAM_KEYS


def _row(m: Measurement, t0: float) -> dict:
    r = {
        "time": m.t, "elapsed_s": m.t - t0, "unit": m.unit,
        "scale_min": m.scale_min, "scale_max": m.scale_max, "scale_source": m.scale_source,
        "max": m.max, "max_x": m.max_xy[0] if m.max_xy else None, "max_y": m.max_xy[1] if m.max_xy else None,
        "min": m.min, "min_x": m.min_xy[0] if m.min_xy else None, "min_y": m.min_xy[1] if m.min_xy else None,
        "mean": m.mean, "center": m.center,
        "roi_max": m.roi["max"] if m.roi else None,
        "roi_min": m.roi["min"] if m.roi else None,
        "roi_mean": m.roi["mean"] if m.roi else None,
    }
    for n, (x, y, t) in m.cam_points.items():
        if 1 <= n <= len(CAM_KEYS):
            k = f"cam{n}"
            r[k], r[f"{k}_x"], r[f"{k}_y"] = t, x, y
    for slot, (x, y, t) in m.spots.items():
        k = f"P{slot}"
        r[k], r[f"{k}_x"], r[f"{k}_y"] = t, x, y
    return r


def _fmt(col, v):
    if v is None:
        return ""
    if col == "time":
        return datetime.fromtimestamp(v).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    if isinstance(v, float):
        if np.isnan(v):
            return ""
        return f"{v:.3f}" if col == "elapsed_s" else f"{v:.2f}"
    return str(v)


class SeriesRecorder:
    """Keeps measurement rows; `offer()` stores one every `interval` seconds while recording."""

    def __init__(self, interval: float = 1.0, max_age: Optional[float] = None):
        self.interval = interval
        self.max_age = max_age          # seconds of history to keep (None = unlimited)
        self.state = "idle"             # idle | recording | paused
        self.t0 = None
        self._last = -1e18
        self.rows = []
        self._cols = {c: [] for c in NUMERIC}
        self._times = []
        self._stream_fp = None
        self._stream = None
        self.stream_path = None

    # ------------------------------------------------------------ control
    def start(self, stream_path=None):
        if self.state == "paused":
            self.state = "recording"
            return
        self.clear()
        self.state = "recording"
        if stream_path:
            self.stream_path = Path(stream_path)
            self.stream_path.parent.mkdir(parents=True, exist_ok=True)
            self._stream_fp = open(self.stream_path, "w", newline="", encoding="utf-8-sig")
            self._stream = csv.writer(self._stream_fp)
            self._stream.writerow(COLUMNS)

    def pause(self):
        if self.state == "recording":
            self.state = "paused"

    def stop(self):
        self.state = "idle"
        if self._stream_fp:
            self._stream_fp.close()
            self._stream_fp = self._stream = None

    def clear(self):
        self.rows.clear()
        for v in self._cols.values():
            v.clear()
        self._times.clear()
        self.t0 = None
        self._last = -1e18

    # --------------------------------------------------------------- data
    def offer(self, m: Measurement) -> bool:
        if self.state != "recording" or m.t - self._last < self.interval - 1e-3:
            return False
        self._last = m.t
        if self.t0 is None:
            self.t0 = m.t
        r = _row(m, self.t0)
        self.rows.append(r)
        self._times.append(m.t)
        for c in NUMERIC:
            v = r.get(c)
            self._cols[c].append(np.nan if v is None else float(v))
        if self._stream:
            self._stream.writerow([_fmt(c, r.get(c)) for c in COLUMNS])
            self._stream_fp.flush()
        if self.max_age is not None:
            cut = 0
            while cut < len(self._times) and m.t - self._times[cut] > self.max_age:
                cut += 1
            if cut:
                del self.rows[:cut], self._times[:cut]
                for v in self._cols.values():
                    del v[:cut]
        return True

    def __len__(self):
        return len(self.rows)

    def times(self) -> np.ndarray:
        return np.asarray(self._times, dtype=np.float64)

    def series(self, key: str) -> np.ndarray:
        return np.asarray(self._cols[key], dtype=np.float64)

    def has_data(self, key: str) -> bool:
        a = self._cols[key]
        return bool(a) and not np.isnan(np.asarray(a)).all()

    def stats(self, key: str):
        a = self.series(key)
        if a.size == 0 or np.isnan(a).all():
            return None
        return {"min": float(np.nanmin(a)), "max": float(np.nanmax(a)), "mean": float(np.nanmean(a)),
                "last": float(a[~np.isnan(a)][-1])}

    def export_csv(self, path, columns=None):
        cols = columns or [c for c in COLUMNS if c in ("time", "elapsed_s", "unit")
                           or c not in NUMERIC or self.has_data(c)]
        with open(path, "w", newline="", encoding="utf-8-sig") as fp:
            w = csv.writer(fp)
            w.writerow(cols)
            for r in self.rows:
                w.writerow([_fmt(c, r.get(c)) for c in cols])
        return len(self.rows)
