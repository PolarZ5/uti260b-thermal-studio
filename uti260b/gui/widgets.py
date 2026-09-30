"""Small reusable widgets: toast, record button, segmented tool bar, cards."""
from PyQt6.QtCore import QEasingCurve, QPropertyAnimation, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (QButtonGroup, QFrame, QGraphicsOpacityEffect, QHBoxLayout, QLabel,
                             QPushButton, QToolButton, QVBoxLayout, QWidget)

from .icons import icon
from .theme import ACCENT, BORDER, CARD, MUTED, TEXT


class Toast(QFrame):
    """Transient message at the bottom of its parent, with an optional action."""

    def __init__(self, parent):
        super().__init__(parent)
        self.setObjectName("Toast")
        self.setStyleSheet(f"""
            QFrame#Toast {{ background: rgba(29,32,39,235); border: 1px solid {BORDER}; border-radius: 10px; }}
            QLabel {{ background: transparent; }}
            QPushButton {{ background: transparent; border: none; color: {ACCENT}; font-weight: 600; padding: 2px 6px; }}
            QPushButton:hover {{ text-decoration: underline; }}
        """)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 8, 10, 8)
        lay.setSpacing(10)
        self.ic = QLabel()
        self.text = QLabel()
        self.action = QPushButton()
        lay.addWidget(self.ic)
        lay.addWidget(self.text)
        lay.addWidget(self.action)
        self._cb = None
        self.action.clicked.connect(self._run)
        self.fx = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.fx)
        self.anim = QPropertyAnimation(self.fx, b"opacity", self)
        self.anim.setDuration(350)
        self.anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.anim.finished.connect(self._after_anim)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self._fade_out)
        self.hide()

    def show_message(self, text, kind="ok", action=None, callback=None, ms=3500):
        name, color = {"ok": ("check", "#52d273"), "rec": ("record", "#ff4d4f"),
                       "info": ("bell", ACCENT), "error": ("mask", "#ff4d4f")}[kind]
        self.ic.setPixmap(icon(name, color, 18).pixmap(18, 18))
        self.text.setText(text)
        self.action.setVisible(bool(action))
        self.action.setText(action or "")
        self._cb = callback
        self.adjustSize()
        self.reposition()
        self.show()
        self.raise_()
        self.anim.stop()
        self.anim.setStartValue(self.fx.opacity() if self.isVisible() else 0.0)
        self.anim.setEndValue(1.0)
        self.anim.start()
        self.timer.start(ms)

    def reposition(self):
        p = self.parentWidget()
        if p is not None:
            self.move((p.width() - self.width()) // 2, p.height() - self.height() - 18)

    def _run(self):
        if self._cb:
            self._cb()
        self._fade_out()

    def _fade_out(self):
        self.anim.stop()
        self.anim.setStartValue(self.fx.opacity())
        self.anim.setEndValue(0.0)
        self.anim.start()

    def _after_anim(self):
        if self.fx.opacity() <= 0.01:
            self.hide()


class RecordButton(QPushButton):
    """Idle: '● บันทึกวิดีโอ'. Recording: red pill with a pulsing dot and the elapsed time."""

    def __init__(self, idle_text="บันทึกวิดีโอ", parent=None):
        super().__init__(parent)
        self.idle_text = idle_text
        self.setCheckable(True)
        self.setIconSize(QSize(16, 16))
        self._on = False
        self._blink = False
        self.set_recording(False)

    def set_recording(self, on: bool, elapsed: str = ""):
        self._on = on
        self.setChecked(on)
        if on:
            self._blink = not self._blink
            self.setIcon(icon("record", "#ffffff" if self._blink else "#ffb3b3", 16))
            self.setText(f"  REC  {elapsed}")
            self.setToolTip("หยุดบันทึก")
            self.setObjectName("RecOn")
        else:
            self.setIcon(icon("record", "#ff4d4f", 16))
            self.setText(f"  {self.idle_text}")
            self.setToolTip(self.idle_text)
            self.setObjectName("RecOff")
        self.style().unpolish(self)
        self.style().polish(self)


class SegmentedTools(QFrame):
    """Mutually exclusive tool buttons in one rounded group."""
    toolChanged = pyqtSignal(str)

    def __init__(self, tools, parent=None):
        super().__init__(parent)
        self.setObjectName("Segmented")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(3, 3, 3, 3)
        lay.setSpacing(2)
        self.group = QButtonGroup(self)
        self.buttons = {}
        for key, text, ic, tip in tools:
            b = QToolButton()
            b.setText(text)
            b.setIcon(icon(ic, TEXT, 18))
            b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            b.setCheckable(True)
            b.setToolTip(tip)
            b.clicked.connect(lambda _, k=key: self.toolChanged.emit(k))
            self.group.addButton(b)
            lay.addWidget(b)
            self.buttons[key] = b
        next(iter(self.buttons.values())).setChecked(True)

    def set_tool(self, key):
        self.buttons[key].setChecked(True)


def icon_button(name, tip, text="", color=TEXT, checkable=False, object_name=None):
    b = QToolButton()
    b.setIcon(icon(name, color, 18))
    b.setToolTip(tip)
    if text:
        b.setText(text)
        b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
    b.setCheckable(checkable)
    b.setAutoRaise(True)
    if object_name:
        b.setObjectName(object_name)
    return b


class Card(QFrame):
    def __init__(self, title, color=None, big=True):
        super().__init__()
        self.setObjectName("Card")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 9, 12, 9)
        lay.setSpacing(1)
        t = QLabel(title)
        t.setObjectName("CardTitle")
        self.value = QLabel("--")
        self.value.setObjectName("CardValue" if big else "CardValueSmall")
        if color:
            self.value.setStyleSheet(f"color: {color};")
        self.sub = QLabel("")
        self.sub.setObjectName("CardSub")
        for w in (t, self.value, self.sub):
            lay.addWidget(w)


class Section(QWidget):
    """Titled block used in the side panel."""

    def __init__(self, title, parent=None):
        super().__init__(parent)
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(0, 4, 0, 4)
        self.lay.setSpacing(6)
        lb = QLabel(title)
        lb.setObjectName("Section")
        self.lay.addWidget(lb)


def dot(color: str, size=8) -> QLabel:
    lb = QLabel()
    lb.setFixedSize(size, size)
    lb.setStyleSheet(f"background: {color}; border-radius: {size // 2}px;")
    return lb


__all__ = ["Toast", "RecordButton", "SegmentedTools", "icon_button", "Card", "Section", "dot",
           "QColor", "MUTED", "CARD"]
