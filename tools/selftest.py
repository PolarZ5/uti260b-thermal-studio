"""Offline self-test: decodes the sample screens as if they came over USB.

Simulates YUYV 4:2:2 chroma subsampling and a landscape stream, then compares
the decoded temperatures with the radiometric data stored in each BMP.
Usage:  python tools/selftest.py
"""
from pathlib import Path
import sys

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from uti260b.bmpfile import read_uti_bmp   # noqa: E402
from uti260b.decoder import Decoder        # noqa: E402


def yuyv_roundtrip(bgr):
    yuv = cv2.cvtColor(bgr, cv2.COLOR_BGR2YUV).astype(np.float32)
    avg = (yuv[:, 0::2, 1:] + yuv[:, 1::2, 1:]) / 2
    yuv[:, 0::2, 1:] = avg
    yuv[:, 1::2, 1:] = avg
    return cv2.cvtColor(yuv.round().clip(0, 255).astype(np.uint8), cv2.COLOR_YUV2BGR)


def main():
    failures = 0
    for path in sorted((ROOT / "samples").glob("*.bmp")):
        bmp = read_uti_bmp(path)
        truth = bmp.temperatures(use_fix=False)
        cases = {
            "exact": bmp.screen_bgr,
            "yuyv": yuyv_roundtrip(bmp.screen_bgr),
            "yuyv+rot": cv2.rotate(yuyv_roundtrip(bmp.screen_bgr), cv2.ROTATE_90_COUNTERCLOCKWISE),
        }
        for name, frame in cases.items():
            tf = Decoder().decode(frame)
            ok_range = tf.t_min == bmp.t_min and tf.t_max == bmp.t_max
            valid = ~np.isnan(tf.temps)
            err = np.abs(tf.temps[valid] - truth[valid]) if valid.any() else np.array([np.nan])
            failures += not ok_range
            print(f"{path.name:22s} {name:9s} {'OK  ' if ok_range else 'FAIL'} layout={tf.layout} "
                  f"palette={tf.palette:9s} range=({tf.t_min}, {tf.t_max}) valid={valid.mean():.2f} "
                  f"err median={np.median(err):.2f} p95={np.percentile(err, 95):.2f}")
    print("range read failures:", failures)
    return failures


if __name__ == "__main__":
    sys.exit(1 if main() else 0)
