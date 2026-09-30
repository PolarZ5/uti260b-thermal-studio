"""Reader for the radiometric .bmp files the UTi260B saves on its SD card.

File layout (firmware 1.1.x, documented by github.com/Santi-hr/UNI-T-Thermal-Utilities):
  standard 24-bit BMP (screen capture with overlay)
  W*H bytes   clean thermal image, 1 byte/pixel, 0..254 = min..max temperature
  512 bytes   palette, 256 x RGB565 little-endian
  26 bytes    embedded data (unit, max, min, centre, emissivity, positions)
"""
from dataclasses import dataclass
from pathlib import Path
import struct

import numpy as np


def rgb565_to_rgb(values: np.ndarray) -> np.ndarray:
    v = values.astype(np.int32)
    r = ((v >> 11) & 0x1F) * 255 / 0x1F
    g = ((v >> 5) & 0x3F) * 255 / 0x3F
    b = (v & 0x1F) * 255 / 0x1F
    return np.round(np.stack([r, g, b], -1)).astype(np.uint8)


@dataclass
class UtiBmp:
    path: Path
    screen_bgr: np.ndarray      # HxWx3 screen capture incl. overlay
    raw: np.ndarray             # HxW uint8 thermal index 0..254
    palette_rgb: np.ndarray     # 256x3
    unit: str                   # 'C' or 'F'
    t_max: float
    t_min: float
    t_center: float
    emissivity: float
    min_pos: tuple
    max_pos: tuple
    center_pos: tuple

    def temperatures(self, use_fix: bool = True) -> np.ndarray:
        """Per-pixel temperature. use_fix interpolates through the centre
        reading as well, which reduces the error caused by the camera's
        contrast enhancement (the stored image is not linear in temperature)."""
        raw = self.raw.astype(np.float32)
        lin = self.t_min + (self.t_max - self.t_min) * raw / 254.0
        if not use_fix:
            return lin
        cx, cy = self.center_pos
        if not (0 <= cy < raw.shape[0] and 0 <= cx < raw.shape[1]):
            return lin
        c = raw[cy, cx]
        if c <= 0 or c >= 254:
            return lin
        out = np.where(
            raw >= c,
            self.t_center + (self.t_max - self.t_center) * (raw - c) / (254.0 - c),
            self.t_min + (self.t_center - self.t_min) * raw / c,
        )
        return out.astype(np.float32)


def read_uti_bmp(path) -> UtiBmp:
    path = Path(path)
    data = path.read_bytes()
    if data[:2] != b"BM":
        raise ValueError(f"{path.name}: not a BMP file")
    file_size = struct.unpack_from("<I", data, 2)[0]
    w, h = struct.unpack_from("<ii", data, 18)
    h_abs = abs(h)
    n = w * h_abs
    if len(data) < file_size + n + 512 + 26:
        raise ValueError(f"{path.name}: no embedded thermal data (not a UTi camera image?)")

    import cv2
    screen = cv2.imdecode(np.frombuffer(data[:file_size], np.uint8), cv2.IMREAD_COLOR)

    raw = np.frombuffer(data, np.uint8, n, file_size).reshape(h_abs, w).copy()
    off = file_size + n
    palette = rgb565_to_rgb(np.frombuffer(data, "<u2", 256, off))
    off += 512
    e = data[off:off + 26]
    t_max, t_min, _unk, t_center = struct.unpack_from("<hhhh", e, 1)
    pos = struct.unpack_from("<6H", e, 14)
    return UtiBmp(
        path=path,
        screen_bgr=screen,
        raw=raw,
        palette_rgb=palette,
        unit="C" if e[0] == 0 else "F",
        t_max=t_max / 10.0,
        t_min=t_min / 10.0,
        t_center=t_center / 10.0,
        emissivity=e[9] / 100.0,
        min_pos=(pos[0], pos[1]),
        max_pos=(pos[2], pos[3]),
        center_pos=(pos[4], pos[5]),
    )
