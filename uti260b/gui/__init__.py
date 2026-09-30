"""PyQt6 desktop GUI."""
import sys


def main():
    import json

    from PyQt6.QtWidgets import QApplication

    from ..i18n import set_language, system_language
    from ..paths import SETTINGS

    try:
        lang = json.loads(SETTINGS.read_text("utf-8")).get("language")
    except (OSError, ValueError):
        lang = None
    set_language(lang or system_language())       # before the UI modules build their text

    from . import theme
    from .icons import app_icon
    from .window import MainWindow

    if sys.platform == "win32":
        try:                                    # own taskbar button/icon instead of python.exe's
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("UNI-T.UTi260B.ThermalStudio")
        except Exception:
            pass
    app = QApplication(sys.argv)
    app.setApplicationName("UTi260B Thermal Studio")
    app.setWindowIcon(app_icon())
    theme.apply(app)
    w = MainWindow()
    w.show()
    return app.exec()
