"""Measurements taken on one decoded frame: scene max/min, centre, user spots, ROI."""
from dataclasses import dataclass, field
import time
from typing import Optional

from .decoder import ThermalFrame

MAX_SPOTS = 6


@dataclass
class Spot:
    slot: int           # 1..MAX_SPOTS, becomes column P<slot> in the CSV
    x: int
    y: int


@dataclass
class Measurement:
    t: float
    unit: str
    scale_min: Optional[float]
    scale_max: Optional[float]
    scale_source: str
    max: Optional[float] = None
    max_xy: Optional[tuple] = None
    min: Optional[float] = None
    min_xy: Optional[tuple] = None
    mean: Optional[float] = None
    center: Optional[float] = None
    spots: dict = field(default_factory=dict)      # slot -> (x, y, temp or None)
    roi: Optional[dict] = None                     # max/min/mean/max_xy/min_xy
    cam_points: dict = field(default_factory=dict)  # camera Point Temperature n -> (x, y, temp)
    from_camera: bool = False                       # max/min taken from the camera trackers


def free_slot(spots) -> Optional[int]:
    used = {s.slot for s in spots}
    return next((i for i in range(1, MAX_SPOTS + 1) if i not in used), None)


def center_temp(frame: ThermalFrame) -> Optional[float]:
    if frame.center_temp is not None:
        return frame.center_temp
    h, w = frame.shape
    for r in range(1, 9):               # the camera's crosshair may cover the centre pixels
        t = frame.temp_at(w // 2, h // 2, r)
        if t is not None:
            return t
    return None


def measure(frame: ThermalFrame, spots=(), roi=None, unit: Optional[str] = None) -> Measurement:
    m = Measurement(frame.timestamp, unit or frame.unit, frame.t_min, frame.t_max, frame.range_source)
    st = frame.stats()
    if st:
        m.max, m.max_xy, m.min, m.min_xy, m.mean = st["max"], st["max_xy"], st["min"], st["min_xy"], st["mean"]
    exact = frame.range_source in ("osd", "hold", "partial")
    if exact and frame.hot_xy is not None:
        m.max, m.max_xy, m.from_camera = frame.t_max, frame.hot_xy, True
    if exact and frame.cold_xy is not None and frame.range_source != "partial":
        m.min, m.min_xy, m.from_camera = frame.t_min, frame.cold_xy, True
    m.cam_points = dict(frame.cam_points)
    m.center = center_temp(frame)
    for s in spots:
        m.spots[s.slot] = (s.x, s.y, frame.temp_at(s.x, s.y, 1))
    if roi:
        m.roi = frame.stats(roi)
    return m


def now() -> float:
    return time.time()
