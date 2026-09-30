"""Snapshots and video recording; every video gets a CSV with the same name."""
import json
from pathlib import Path
import time

import cv2
import numpy as np

from ..decoder import ThermalFrame
from ..measure import Measurement
from ..series import SeriesRecorder
from ..i18n import tr


def stamp() -> str:
    return time.strftime("%Y%m%d_%H%M%S")


def fmt_duration(seconds: float) -> str:
    s = int(max(0, seconds))
    return f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}"


class VideoSession:
    """MP4 written in real time (frames repeated when the camera is slower than the
    file's frame rate) plus a CSV of the measurements with the same base name."""

    def __init__(self, base: Path, size, fps: float, series: SeriesRecorder, feed: bool):
        self.base = base
        self.video_path = base.with_suffix(".mp4")
        self.csv_path = base.with_suffix(".csv")
        self.fps = max(1.0, round(fps))
        self.size = size
        self.writer = cv2.VideoWriter(str(self.video_path), cv2.VideoWriter_fourcc(*"mp4v"), self.fps, size)
        if not self.writer.isOpened():
            raise RuntimeError(tr("เขียนไฟล์วิดีโอไม่ได้: {path}", path=self.video_path))
        self.series = series
        self.feed = feed                        # False when the graph's recorder already gets every frame
        self.t0 = time.time()
        self.frames = 0
        self._last = None

    @property
    def elapsed(self) -> float:
        return time.time() - self.t0

    def write(self, view_bgr: np.ndarray, m: Measurement):
        if view_bgr.shape[1::-1] != self.size:
            view_bgr = cv2.resize(view_bgr, self.size)
        self._last = view_bgr
        due = int(self.elapsed * self.fps) + 1
        n = max(1 if self.frames == 0 else 0, due - self.frames)
        for _ in range(min(n, int(self.fps) * 2)):
            self.writer.write(view_bgr)
            self.frames += 1
        if self.feed:
            self.series.offer(m)

    def close(self):
        # pad the tail so the clip length matches the wall-clock duration
        if self._last is not None:
            due = int(self.elapsed * self.fps)
            while self.frames < due:
                self.writer.write(self._last)
                self.frames += 1
        self.writer.release()
        self.series.stop()


class CaptureManager:
    def __init__(self, folder: Path):
        self.folder = Path(folder)
        self.video: VideoSession | None = None

    def set_folder(self, folder):
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=True)

    def base(self) -> Path:
        self.folder.mkdir(parents=True, exist_ok=True)
        return self.folder / f"uti_{stamp()}"

    # ------------------------------------------------------------ snapshot
    def snapshot(self, frame: ThermalFrame, m: Measurement, view_bgr: np.ndarray, extra: dict) -> list:
        base = self.base()
        paths = [Path(str(base) + "_view.png"), Path(str(base) + "_screen.png")]
        cv2.imwrite(str(paths[0]), view_bgr)
        cv2.imwrite(str(paths[1]), frame.screen)
        if frame.has_scale:
            p = Path(str(base) + "_temps.csv")
            with open(p, "w", encoding="utf-8") as fp:
                for row in frame.temps:
                    fp.write(",".join("" if np.isnan(v) else f"{v:.2f}" for v in row) + "\n")
            paths.append(p)
        meta = {
            "time": time.strftime("%Y-%m-%d %H:%M:%S"), "unit": m.unit,
            "scale": [frame.t_min, frame.t_max], "scale_source": frame.range_source, "palette": frame.palette,
            "calibration": [[round(float(i), 2), t] for i, t in frame.calibration],
            "max": m.max, "max_xy": m.max_xy, "min": m.min, "min_xy": m.min_xy, "mean": m.mean,
            "center": m.center, "roi": m.roi,
            "spots": [{"name": f"P{s}", "xy": [x, y], "temp": t} for s, (x, y, t) in m.spots.items()],
            "camera_points": [{"name": f"cam{n}", "xy": [x, y], "temp": t} for n, (x, y, t) in m.cam_points.items()],
            "note": "temps.csv: rows = y, cols = x; empty = covered by the camera's on-screen display",
            **extra,
        }
        p = Path(str(base) + "_meta.json")
        p.write_text(json.dumps(meta, indent=2, ensure_ascii=False), "utf-8")
        paths.append(p)
        return paths

    # --------------------------------------------------------------- video
    def start_video(self, first_view_bgr: np.ndarray, fps: float, series: SeriesRecorder,
                    feed: bool) -> VideoSession:
        """series must be idle; it is started with <base>.csv and stopped with the video."""
        base = self.base()
        h, w = first_view_bgr.shape[:2]
        series.start(base.with_suffix(".csv"))
        try:
            self.video = VideoSession(base, (w, h), fps, series, feed)
        except Exception:
            series.stop()
            raise
        return self.video

    def stop_video(self) -> VideoSession | None:
        v, self.video = self.video, None
        if v is not None:
            v.close()
        return v
