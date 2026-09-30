# PyInstaller spec: single-file Windows app.
# Build (in a clean venv with requirements.txt + pyinstaller installed):
#   pyinstaller UTi260B-Thermal-Studio.spec
# Output: dist/UTi260B-Thermal-Studio.exe
from pathlib import Path

root = Path(SPECPATH)
samples = [(str(p), "samples") for p in (root / "samples").iterdir() if p.suffix.lower() in (".bmp", ".png", ".txt")]

a = Analysis(
    [str(root / "launcher.py")],
    pathex=[str(root)],
    datas=[
        (str(root / "uti260b" / "assets.npz"), "uti260b"),
        (str(root / "uti260b" / "gui" / "thermometer.ico"), "uti260b/gui"),
        *samples,
    ],
    hiddenimports=["pygrabber.dshow_graph", "comtypes.stream"],
    excludes=["tkinter", "matplotlib", "scipy", "pandas", "IPython", "torch", "PIL",
              "PyQt6.QtWebEngineCore", "PyQt6.QtWebEngineWidgets", "PyQt6.QtQml", "PyQt6.QtQuick",
              "PyQt6.Qt3DCore", "PyQt6.QtMultimedia", "PyQt6.QtBluetooth", "PyQt6.QtPdf"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="UTi260B-Thermal-Studio",
    icon=str(root / "uti260b" / "gui" / "thermometer.ico"),
    console=False,
    upx=False,
    version=str(root / "tools" / "version_info.txt"),
)
