"""Diagnostics for a connected UTi260B (USB Mode = USB Camera).

Lists the USB/video devices, tries every capture backend and a few frame
sizes, saves sample frames and checks whether the decoder recognises the
stream. Writes everything to probe_report/.

Usage:  python probe.py            (all video devices)
        python probe.py 1          (only device index 1)
"""
from pathlib import Path
import subprocess
import sys
import time

import cv2
import numpy as np

from uti260b.decoder import Decoder
from uti260b.sources import list_cameras, guess_uti_index

OUT = Path(__file__).resolve().parent / "probe_report"
SIZES = [None, (240, 320), (320, 240), (256, 192), (256, 384), (480, 640), (640, 480)]
BACKENDS = {"DSHOW": cv2.CAP_DSHOW, "MSMF": cv2.CAP_MSMF}

lines = []


def log(*a):
    s = " ".join(str(x) for x in a)
    print(s)
    lines.append(s)


def pnp_devices():
    ps = ("Get-PnpDevice -PresentOnly | Where-Object { $_.Class -in 'Camera','Image','USB','WPD','DiskDrive',"
          "'USBDevice' -or $_.InstanceId -like 'USB*' } | ForEach-Object { \"$($_.Status)`t$($_.Class)`t"
          "$($_.FriendlyName)`t$($_.InstanceId)\" }")
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True, timeout=30)
        return r.stdout.strip().splitlines()
    except Exception as e:
        return [f"(PnP query failed: {e})"]


def dshow_formats(index):
    try:
        from pygrabber.dshow_graph import FilterGraph
        g = FilterGraph()
        g.add_video_input_device(index)
        return g.get_input_device().get_formats()
    except Exception as e:
        return [f"(format list unavailable: {e})"]


def fourcc_str(cap):
    cc = int(cap.get(cv2.CAP_PROP_FOURCC))
    return "".join(chr((cc >> 8 * i) & 0xFF) for i in range(4)) if cc > 0 else "?"


def try_open(index, bname, backend, size):
    tag = f"{bname} size={size or 'default'}"
    cap = cv2.VideoCapture(index, backend)
    if not cap.isOpened():
        log(f"  [{tag}] cannot open")
        return None
    if size:
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, size[0])
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, size[1])
    frame = None
    t0 = time.time()
    n = 0
    while time.time() - t0 < 2.0:
        ok, f = cap.read()
        if ok and f is not None:
            frame = f
            n += 1
    fps = n / 2.0
    w, h = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    info = f"  [{tag}] reported {w}x{h} fourcc={fourcc_str(cap)} fps~{fps:.1f}"
    if frame is None:
        log(info + " NO FRAMES")
        cap.release()
        return None
    log(info + f" frame={frame.shape} mean={frame.mean():.1f}")
    # raw buffer: look for bytes beyond the image (embedded telemetry?)
    try:
        cap.set(cv2.CAP_PROP_CONVERT_RGB, 0)
        ok, raw = cap.read()
        if ok and raw is not None:
            expect = w * h * 2
            log(f"      raw buffer: shape={raw.shape} bytes={raw.size} (YUYV image would be {expect})")
            if raw.size > expect:
                tail = raw.reshape(-1)[expect:expect + 64]
                log(f"      EXTRA {raw.size - expect} bytes after image, first 64: {tail.tobytes().hex()}")
            np.save(OUT / f"cam{index}_{bname}_{w}x{h}_raw.npy", raw)
    except Exception as e:
        log(f"      raw read failed: {e}")
    cap.release()
    return frame


def main():
    OUT.mkdir(exist_ok=True)
    only = int(sys.argv[1]) if len(sys.argv) > 1 else None
    log("== PnP devices (USB / camera / storage) ==")
    for line in pnp_devices():
        log("  " + line)
    cams = list_cameras()
    log("\n== Video capture devices ==")
    for i, n in cams:
        log(f"  #{i}: {n}")
    guess = guess_uti_index(cams)
    log(f"  likely UTi260B: {guess}")
    if not cams:
        log("\nNo video devices. On the camera: Settings -> USB Mode -> USB Camera, then reconnect the cable.")
    for i, name in cams:
        if only is not None and i != only:
            continue
        log(f"\n== Device #{i}: {name} ==")
        for fmt in dshow_formats(i):
            log(f"  format: {fmt}")
        for bname, backend in BACKENDS.items():
            for size in SIZES:
                frame = try_open(i, bname, backend, size)
                if frame is None:
                    continue
                h, w = frame.shape[:2]
                cv2.imwrite(str(OUT / f"cam{i}_{bname}_{w}x{h}.png"), frame)
                d = Decoder()
                tf = d.decode(frame)
                log(f"      decoder: layout={tf.layout} rotation={d._auto_rot} palette={tf.palette} "
                    f"range=({tf.t_min}, {tf.t_max}) source={tf.range_source} "
                    f"measurable={np.mean(~np.isnan(tf.index)):.2f}")
                if tf.layout == "screen":
                    cv2.imwrite(str(OUT / f"cam{i}_{bname}_{w}x{h}_screen.png"), tf.screen)
    (OUT / "report.txt").write_text("\n".join(lines), encoding="utf-8")
    print(f"\nReport written to {OUT}")


if __name__ == "__main__":
    main()
