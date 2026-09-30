"""Thermal image widget: draws the frame, markers, colour bar; handles spot/ROI/mask tools."""
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
from PyQt6.QtCore import QPointF, QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QBrush, QColor, QFont, QImage, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import QMenu, QWidget

from ..measure import Measurement
from .theme import BG, COLORS

BAR_W = 64          # room for the colour bar on the right


def fmt(v, unit="C", digits=1):
    return "--" if v is None else f"{v:.{digits}f}°{unit}"


def bgr_to_qimage(bgr: np.ndarray) -> QImage:
    rgb = np.ascontiguousarray(bgr[..., ::-1])
    h, w = rgb.shape[:2]
    return QImage(rgb.data, w, h, 3 * w, QImage.Format.Format_RGB888).copy()


@dataclass
class Overlay:
    m: Optional[Measurement] = None
    spots: list = field(default_factory=list)
    roi: Optional[tuple] = None
    masks: list = field(default_factory=list)
    show_hot: bool = True
    show_cold: bool = True
    show_center: bool = True
    unit: str = "C"
    lut: Optional[np.ndarray] = None        # 256x3 BGR of the displayed palette
    span: tuple = (None, None)              # temperatures at bottom/top of the colour bar
    alarm: bool = False
    note: str = ""
    drag: Optional[tuple] = None            # rect being dragged (image coords)
    drag_kind: str = "roi"
    highlight: Optional[int] = None         # spot slot being edited


def _label(p: QPainter, x, y, text, color, bounds: QRectF, bold=True):
    """Rounded dark pill with coloured text, kept inside bounds."""
    f = QFont(p.font())
    f.setPointSizeF(8.5)
    f.setBold(bold)
    p.setFont(f)
    fm = p.fontMetrics()
    w, h = fm.horizontalAdvance(text) + 10, fm.height() + 2
    x = min(max(bounds.left() + 2, x), bounds.right() - w - 2)
    y = min(max(bounds.top() + 2, y), bounds.bottom() - h - 2)
    r = QRectF(x, y, w, h)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(10, 12, 16, 190))
    p.drawRoundedRect(r, 5, 5)
    p.setPen(QColor(color))
    p.drawText(r, Qt.AlignmentFlag.AlignCenter, text)


def _cross(p: QPainter, c: QPointF, color, size=8, gap=3):
    for pen in (QPen(QColor(0, 0, 0, 200), 3.5), QPen(QColor(color), 1.6)):
        p.setPen(pen)
        p.drawLine(QPointF(c.x() - size, c.y()), QPointF(c.x() - gap, c.y()))
        p.drawLine(QPointF(c.x() + gap, c.y()), QPointF(c.x() + size, c.y()))
        p.drawLine(QPointF(c.x(), c.y() - size), QPointF(c.x(), c.y() - gap))
        p.drawLine(QPointF(c.x(), c.y() + gap), QPointF(c.x(), c.y() + size))


def _triangle(p: QPainter, c: QPointF, color, up=True, s=7):
    path = QPainterPath()
    d = -1 if up else 1
    path.moveTo(c.x(), c.y())
    path.lineTo(c.x() - s * 0.7, c.y() - d * s * 1.3)
    path.lineTo(c.x() + s * 0.7, c.y() - d * s * 1.3)
    path.closeSubpath()
    p.setPen(QPen(QColor(0, 0, 0, 220), 1.5))
    p.setBrush(QColor(color))
    p.drawPath(path)


def paint_scene(p: QPainter, W: float, H: float, image: Optional[QImage], ov: Overlay) -> Optional[QRectF]:
    """Paints image + overlays into a W x H area. Returns the image rectangle."""
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    p.fillRect(QRectF(0, 0, W, H), QColor(BG))
    if image is None:
        p.setPen(QColor("#8b93a5"))
        p.drawText(QRectF(0, 0, W, H), Qt.AlignmentFlag.AlignCenter,
                   "ยังไม่มีภาพ\nเชื่อมต่อกล้อง, เปิดโหมดสาธิต หรือเปิดไฟล์ BMP")
        return None
    iw, ih = image.width(), image.height()
    avail_w = max(10.0, W - BAR_W)
    s = min(avail_w / iw, H / ih)
    rect = QRectF((avail_w - iw * s) / 2, (H - ih * s) / 2, iw * s, ih * s)
    p.drawImage(rect, image)
    if ov.alarm:
        p.setPen(QPen(QColor("#ff3b3b"), 4))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(rect.adjusted(2, 2, -2, -2))

    def P(xy):
        return QPointF(rect.left() + (xy[0] + 0.5) * s, rect.top() + (xy[1] + 0.5) * s)

    def R(r):
        x0, y0, x1, y1 = r
        return QRectF(P((min(x0, x1) - 0.5, min(y0, y1) - 0.5)), P((max(x0, x1) - 0.5, max(y0, y1) - 0.5)))

    u = ov.unit
    for mr in ov.masks:
        q = R(mr)
        p.setPen(QPen(QColor(200, 200, 200, 160), 1, Qt.PenStyle.DashLine))
        p.setBrush(QBrush(QColor(120, 120, 120, 90), Qt.BrushStyle.BDiagPattern))
        p.drawRect(q)
    m = ov.m
    if ov.roi:
        q = R(ov.roi)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(0, 0, 0, 180), 3))
        p.drawRect(q)
        p.setPen(QPen(QColor(COLORS["roi_max"]), 1.5, Qt.PenStyle.DashLine))
        p.drawRect(q)
        if m and m.roi:
            _triangle(p, P(m.roi["max_xy"]), COLORS["max"], True, 5)
            _triangle(p, P(m.roi["min_xy"]), COLORS["min"], False, 5)
            _label(p, q.left(), q.top() - 20,
                   f"ROI  ▲{fmt(m.roi['max'], u)}  ▼{fmt(m.roi['min'], u)}  Ø{fmt(m.roi['mean'], u)}",
                   COLORS["roi_max"], rect)
    if m:
        if ov.show_hot and m.max_xy:
            c = P(m.max_xy)
            _triangle(p, c, COLORS["max"], True)
            _label(p, c.x() + 8, c.y() - 22, fmt(m.max, u), COLORS["max"], rect)
        if ov.show_cold and m.min_xy:
            c = P(m.min_xy)
            _triangle(p, c, COLORS["min"], False)
            _label(p, c.x() + 8, c.y() + 6, fmt(m.min, u), COLORS["min"], rect)
        if ov.show_center:
            c = QPointF(rect.center())
            _cross(p, c, COLORS["center"], 11, 4)
            _label(p, c.x() + 10, c.y() + 8, fmt(m.center, u), COLORS["center"], rect)
        for n, (x, y, t) in sorted(m.cam_points.items()):
            c = P((x, y))
            col = COLORS.get(f"cam{n}", "#ffffff")
            d = 6
            diamond = QPainterPath()
            diamond.moveTo(c.x(), c.y() - d)
            diamond.lineTo(c.x() + d, c.y())
            diamond.lineTo(c.x(), c.y() + d)
            diamond.lineTo(c.x() - d, c.y())
            diamond.closeSubpath()
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(QColor(0, 0, 0, 200), 3.5))
            p.drawPath(diamond)
            p.setPen(QPen(QColor(col), 1.6))
            p.drawPath(diamond)
            _label(p, c.x() + 9, c.y() + 4, f"กล้อง P{n}  {fmt(t, u)}", col, rect)
        for sp in ov.spots:
            c = P((sp.x, sp.y))
            col = COLORS[f"P{sp.slot}"]
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(QColor(0, 0, 0, 200), 3.5))
            p.drawEllipse(c, 5, 5)
            p.setPen(QPen(QColor(col), 1.8))
            p.drawEllipse(c, 5, 5)
            if sp.slot == ov.highlight:
                p.setPen(QPen(QColor(col), 1.4, Qt.PenStyle.DashLine))
                p.drawEllipse(c, 11, 11)
            t = m.spots.get(sp.slot, (0, 0, None))[2]
            _label(p, c.x() + 8, c.y() - 9, f"P{sp.slot}  {fmt(t, u)}", col, rect)
    if ov.drag:
        q = R(ov.drag)
        col = "#bbbbbb" if ov.drag_kind == "mask" else COLORS["roi_max"]
        p.setBrush(QColor(255, 255, 255, 25))
        p.setPen(QPen(QColor(col), 1.2, Qt.PenStyle.DashLine))
        p.drawRect(q)
    if ov.note:
        _label(p, rect.left() + 6, rect.bottom() - 26, ov.note, "#ffb020", rect, bold=False)
    _paint_colorbar(p, QRectF(rect.right() + 14, rect.top() + 22, 16, rect.height() - 44), ov)
    return rect


def _paint_colorbar(p: QPainter, r: QRectF, ov: Overlay):
    if ov.lut is None or r.height() < 20:
        return
    grad = ov.lut[::-1][:, None, :].repeat(2, 1)             # hot at the top
    img = bgr_to_qimage(np.ascontiguousarray(grad))
    p.drawImage(r, img)
    p.setPen(QPen(QColor("#323743"), 1))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRect(r)
    lo, hi = ov.span
    f = QFont(p.font())
    f.setPointSizeF(8)
    f.setBold(False)
    p.setFont(f)
    p.setPen(QColor("#e6e8ee"))
    top = QRectF(r.center().x() - 40, r.top() - 20, 80, 16)
    bot = QRectF(r.center().x() - 40, r.bottom() + 4, 80, 16)
    p.drawText(top, Qt.AlignmentFlag.AlignCenter, fmt(hi, ov.unit))
    p.drawText(bot, Qt.AlignmentFlag.AlignCenter, fmt(lo, ov.unit))
    if lo is not None and hi is not None and hi > lo:
        p.setPen(QColor("#8b93a5"))
        for k in range(1, 4):
            y = r.top() + r.height() * k / 4
            p.drawLine(QPointF(r.right(), y), QPointF(r.right() + 4, y))
            p.drawText(QRectF(r.right() + 6, y - 8, 40, 16), Qt.AlignmentFlag.AlignVCenter,
                       f"{hi - (hi - lo) * k / 4:.1f}")


def render_to_array(image: QImage, ov: Overlay, scale: float = 2.0) -> np.ndarray:
    """Offscreen render (for snapshots / video). Returns BGR uint8."""
    W, H = int(image.width() * scale + BAR_W), int(image.height() * scale)
    W += W % 2
    H += H % 2
    out = QImage(W, H, QImage.Format.Format_RGB888)
    p = QPainter(out)
    paint_scene(p, W, H, image, ov)
    p.end()
    ptr = out.constBits()
    ptr.setsize(out.sizeInBytes())
    arr = np.frombuffer(ptr, np.uint8).reshape(H, out.bytesPerLine())[:, :W * 3].reshape(H, W, 3)
    return arr[..., ::-1].copy()


class ThermalView(QWidget):
    spotAdded = pyqtSignal(int, int)
    spotRemoved = pyqtSignal(int)              # slot
    roiChanged = pyqtSignal(object)            # tuple or None
    maskAdded = pyqtSignal(object)
    hovered = pyqtSignal(int, int)             # -1, -1 when leaving

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(320, 360)
        self.setMouseTracking(True)
        self.image: Optional[QImage] = None
        self.img_size = (0, 0)
        self.ov = Overlay()
        self.tool = "spot"
        self._rect: Optional[QRectF] = None
        self._press = None
        self.rec_badges = []                   # [(text, color)] drawn on screen only, not in saved files
        self.blink = False
        self._flash = 0
        self._flash_timer = QTimer(self)
        self._flash_timer.timeout.connect(self._fade_flash)

    def flash(self):
        """Camera-shutter flash after a snapshot."""
        self._flash = 170
        self._flash_timer.start(16)
        self.update()

    def _fade_flash(self):
        self._flash = max(0, self._flash - 18)
        if self._flash == 0:
            self._flash_timer.stop()
        self.update()

    def set_frame(self, image: Optional[QImage], ov: Overlay):
        self.image = image
        if image is not None:
            self.img_size = (image.width(), image.height())
        drag, kind = self.ov.drag, self.ov.drag_kind
        self.ov = ov
        self.ov.drag, self.ov.drag_kind = drag, kind
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        self._rect = paint_scene(p, self.width(), self.height(), self.image, self.ov)
        if self._rect is not None and self._flash:
            p.fillRect(self._rect, QColor(255, 255, 255, self._flash))
        if self._rect is not None and self.rec_badges:
            y = self._rect.top() + 8
            for text, color in self.rec_badges:
                f = QFont(self.font())
                f.setPointSizeF(9)
                f.setBold(True)
                p.setFont(f)
                w = p.fontMetrics().horizontalAdvance(text) + 34
                r = QRectF(self._rect.right() - w - 8, y, w, 24)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(10, 12, 16, 200))
                p.drawRoundedRect(r, 12, 12)
                p.setBrush(QColor(color) if self.blink else QColor(color).darker(170))
                p.drawEllipse(QPointF(r.left() + 14, r.center().y()), 5, 5)
                p.setPen(QColor("#ffffff"))
                p.drawText(r.adjusted(24, 0, -8, 0), Qt.AlignmentFlag.AlignVCenter, text)
                y += 30
        p.end()

    # ------------------------------------------------------------ mouse
    def _img_xy(self, pos):
        if self._rect is None or not self.img_size[0]:
            return None
        s = self._rect.width() / self.img_size[0]
        x = int((pos.x() - self._rect.left()) / s)
        y = int((pos.y() - self._rect.top()) / s)
        return x, y

    def _inside(self, xy):
        return xy is not None and 0 <= xy[0] < self.img_size[0] and 0 <= xy[1] < self.img_size[1]

    def _clamp(self, xy):
        return (min(max(0, xy[0]), self.img_size[0] - 1), min(max(0, xy[1]), self.img_size[1] - 1))

    def mousePressEvent(self, e):
        xy = self._img_xy(e.position())
        if not self._inside(xy):
            return
        if e.button() == Qt.MouseButton.RightButton:
            self._context(e, xy)
            return
        if e.button() != Qt.MouseButton.LeftButton:
            return
        if self.tool == "spot":
            self.spotAdded.emit(*xy)
        else:
            self._press = xy
            self.ov.drag, self.ov.drag_kind = (*xy, *xy), self.tool
            self.update()

    def mouseMoveEvent(self, e):
        xy = self._img_xy(e.position())
        if self._press is not None and xy is not None:
            self.ov.drag = (*self._press, *self._clamp(xy))
            self.update()
        if self._inside(xy):
            self.hovered.emit(*xy)
        else:
            self.hovered.emit(-1, -1)

    def mouseReleaseEvent(self, e):
        if self._press is None:
            return
        r = self.ov.drag
        self._press = None
        self.ov.drag = None
        if r and abs(r[2] - r[0]) >= 3 and abs(r[3] - r[1]) >= 3:
            r = (min(r[0], r[2]), min(r[1], r[3]), max(r[0], r[2]) + 1, max(r[1], r[3]) + 1)
            (self.maskAdded if self.tool == "mask" else self.roiChanged).emit(r)
        self.update()

    def leaveEvent(self, e):
        self.hovered.emit(-1, -1)

    def _context(self, e, xy):
        menu = QMenu(self)
        near = None
        if self.ov.spots and self._rect is not None:
            s = self._rect.width() / self.img_size[0]
            d = [((sp.x - xy[0]) ** 2 + (sp.y - xy[1]) ** 2) ** 0.5 * s for sp in self.ov.spots]
            k = int(np.argmin(d))
            if d[k] < 20:
                near = self.ov.spots[k]
        if near:
            menu.addAction(f"ลบจุด P{near.slot}", lambda: self.spotRemoved.emit(near.slot))
        if self.ov.roi:
            menu.addAction("ลบกรอบ ROI", lambda: self.roiChanged.emit(None))
        if not menu.actions():
            return
        menu.exec(e.globalPosition().toPoint())
