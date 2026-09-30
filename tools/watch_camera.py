"""Logs connect/disconnect of the UTi260B (USB VID 1D6B PID 0102) and grabs
test frames whenever it is present. Prints one line per event.

Usage:  python tools/watch_camera.py [minutes]
"""
from pathlib import Path
import subprocess
import sys
import time

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from uti260b.decoder import Decoder            # noqa: E402
from uti260b.sources import list_cameras       # noqa: E402

OUT = ROOT / "probe_report"
PS = ("(Get-PnpDevice -PresentOnly -ErrorAction SilentlyContinue | "
      "Where-Object { $_.InstanceId -match 'VID_1D6B&PID_0102' }).Count")


def present() -> bool:
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-Command", PS], capture_output=True, text=True, timeout=15)
        return int((r.stdout.strip() or "0").splitlines()[-1]) > 0
    except Exception:
        return False


def log(msg):
    print(time.strftime("%H:%M:%S"), msg, flush=True)


def try_capture():
    cams = list_cameras()
    idx = next((i for i, n in cams if "uvc" in n.lower() or "thermal" in n.lower()), None)
    if idx is None:
        log(f"present on USB but not in DirectShow list yet: {cams}")
        return False
    for name, be in (("DSHOW", cv2.CAP_DSHOW), ("MSMF", cv2.CAP_MSMF)):
        cap = cv2.VideoCapture(idx, be)
        if not cap.isOpened():
            log(f"{name}: cannot open #{idx}")
            continue
        frames, t0, frame = 0, time.time(), None
        while time.time() - t0 < 3:
            ok, f = cap.read()
            if ok and f is not None:
                frames += 1
                frame = f
        w, h = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        cc = int(cap.get(cv2.CAP_PROP_FOURCC))
        fourcc = "".join(chr((cc >> 8 * i) & 0xFF) for i in range(4)) if cc > 0 else "?"
        cap.release()
        if frame is None:
            log(f"{name}: opened {w}x{h} {fourcc} but NO frames in 3 s")
            continue
        OUT.mkdir(exist_ok=True)
        p = OUT / f"live_{name}_{frame.shape[1]}x{frame.shape[0]}.png"
        cv2.imwrite(str(p), frame)
        d = Decoder()
        tf = d.decode(frame)
        log(f"{name}: OK {w}x{h} {fourcc} {frames / 3:.1f} fps frame={frame.shape} -> {p.name} | "
            f"decoder layout={tf.layout} rot={d._auto_rot} palette={tf.palette} "
            f"range=({tf.t_min}, {tf.t_max}) {tf.range_source} measurable={np.mean(~np.isnan(tf.index)):.2f}")
        return True
    return False


def main():
    minutes = float(sys.argv[1]) if len(sys.argv) > 1 else 25
    end = time.time() + minutes * 60
    state = None
    captured = False
    log("watching for UTi260B (1D6B:0102)")
    while time.time() < end:
        p = present()
        if p != state:
            log("CONNECTED" if p else "DISCONNECTED")
            state = p
            captured = False
            if p:
                time.sleep(2.5)
        if p and not captured:
            captured = try_capture()
            if captured:
                log("DONE: capture succeeded")
                return
        time.sleep(1)
    log("TIMEOUT")


if __name__ == "__main__":
    main()
