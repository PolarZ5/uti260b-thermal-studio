"""PyQt6 desktop GUI."""
import sys


def main():
    from PyQt6.QtWidgets import QApplication

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
