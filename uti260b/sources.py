"""Frame sources: the camera over USB (UVC), and a demo feed from sample files."""
from pathlib import Path
import threading
import time
from typing import Optional

import cv2
import numpy as np

from .bmpfile import read_uti_bmp

BACKENDS = {"DirectShow": cv2.CAP_DSHOW, "Media Foundation": cv2.CAP_MSMF, "Auto": cv2.CAP_ANY}
UTI_HINTS = ("uti", "thermal", "uni-t", "unit", "uvc camera", "infiray")


def list_cameras(max_probe: int = 6) -> list:
    """[(index, name)] of video capture devices, in DirectShow order."""
    try:
        from pygrabber.dshow_graph import FilterGraph
        names = FilterGraph().get_input_devices()
        return list(enumerate(names))
    except Exception:
        pass
    found = []
    for i in range(max_probe):
        cap = cv2.VideoCapture(i, cv2.CAP_DSHOW)
        if cap.isOpened():
            found.append((i, f"Camera {i}"))
        cap.release()
    return found


def guess_uti_index(cameras: list) -> Optional[int]:
    for i, name in cameras:
        if any(h in name.lower() for h in UTI_HINTS):
            return i
    return None


class FrameSource:
    name = "source"

    def start(self):
        pass

    def stop(self):
        pass

    def read(self):
        """Latest frame (BGR) and its sequence number, or (None, seq)."""
        raise NotImplementedError

    @property
    def fps(self) -> float:
        return 0.0

    @property
    def error(self) -> Optional[str]:
        return None


class CameraSource(FrameSource):
    """Reads the UVC stream on a background thread, keeping only the newest frame."""

    def __init__(self, index: int, backend: str = "DirectShow", size=None, name=None):
        self.index = index
        self.backend = backend
        self.size = size                # (w, h) to request, or None
        self.name = name or f"Camera {index}"
        self._cap = None
        self._lock = threading.Lock()
        self._frame = None
        self._seq = 0
        self._run = False
        self._thread = None
        self._fps = 0.0
        self._error = None
        self.actual_size = None
        self.fourcc = ""

    def start(self):
        cap = cv2.VideoCapture(self.index, BACKENDS.get(self.backend, cv2.CAP_ANY))
        if not cap.isOpened():
            raise RuntimeError(f"Cannot open camera #{self.index} ({self.backend})")
        if self.size:
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.size[0])
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.size[1])
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        self._cap = cap
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        cc = int(cap.get(cv2.CAP_PROP_FOURCC))
        self.actual_size = (w, h)
        self.fourcc = "".join(chr((cc >> 8 * i) & 0xFF) for i in range(4)) if cc > 0 else "?"
        self._run = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def _loop(self):
        t_last = time.time()
        n = 0
        fails = 0
        while self._run:
            ok, frame = self._cap.read()
            if not ok or frame is None:
                fails += 1
                if fails > 50:
                    self._error = "No frames from camera (unplugged, or USB Mode is not 'USB Camera'?)"
                time.sleep(0.02)
                continue
            fails = 0
            self._error = None
            with self._lock:
                self._frame = frame
                self._seq += 1
            n += 1
            now = time.time()
            if now - t_last >= 1.0:
                self._fps = n / (now - t_last)
                n, t_last = 0, now

    def read(self):
        with self._lock:
            return self._frame, self._seq

    def open_driver_settings(self):
        """Opens the Windows driver property page (DirectShow only)."""
        if self._cap is not None:
            self._cap.set(cv2.CAP_PROP_SETTINGS, 1)

    def stop(self):
        self._run = False
        if self._thread:
            self._thread.join(timeout=2)
        if self._cap is not None:
            self._cap.release()
            self._cap = None

    @property
    def fps(self):
        return self._fps

    @property
    def error(self):
        return self._error


class DemoSource(FrameSource):
    """Replays camera screens stored in UTi BMP files, with sensor-like noise."""

    name = "Demo (sample images)"

    def __init__(self, folder, seconds_per_image: float = 4.0, fps: float = 25.0):
        self.frames = []
        for p in sorted(Path(folder).glob("*.bmp")):
            try:
                self.frames.append(read_uti_bmp(p).screen_bgr)
            except Exception:
                pass
        if not self.frames:
            raise RuntimeError(f"No UTi BMP files in {folder}")
        self.seconds_per_image = seconds_per_image
        self._fps = fps
        self._t0 = time.time()
        self._rng = np.random.default_rng()
        self._last = (-1, None)

    def read(self):
        t = time.time() - self._t0
        seq = int(t * self._fps)
        if seq != self._last[0]:
            img = self.frames[int(t / self.seconds_per_image) % len(self.frames)]
            noise = self._rng.integers(-2, 3, img.shape, dtype=np.int16)
            frame = (img.astype(np.int16) + noise).clip(0, 255).astype(np.uint8)
            self._last = (seq, frame)
        return self._last[1], self._last[0]

    @property
    def fps(self):
        return self._fps
