"""Line icons (inline SVG, 24x24, stroke = currentColor) and the thermometer app icon."""
from functools import lru_cache

from PyQt6.QtCore import QByteArray, QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QIcon, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap
from PyQt6.QtSvg import QSvgRenderer

_SVG = {
    "thermometer": '<path d="M14 14.8V5a2 2 0 0 0-4 0v9.8a4 4 0 1 0 4 0Z"/><path d="M12 9v7"/>',
    "camera": '<path d="M4 8h3l2-3h6l2 3h3a1 1 0 0 1 1 1v9a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V9a1 1 0 0 1 1-1Z"/>'
              '<circle cx="12" cy="13" r="3.5"/>',
    "record": '<circle cx="12" cy="12" r="7" fill="currentColor" stroke="none"/>',
    "stop": '<rect x="6" y="6" width="12" height="12" rx="2" fill="currentColor" stroke="none"/>',
    "pause": '<rect x="7" y="5" width="3.5" height="14" rx="1" fill="currentColor" stroke="none"/>'
             '<rect x="13.5" y="5" width="3.5" height="14" rx="1" fill="currentColor" stroke="none"/>',
    "play": '<path d="M8 5.5v13l10.5-6.5Z" fill="currentColor"/>',
    "folder": '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2Z"/>',
    "sliders": '<path d="M4 6h10M18 6h2M4 12h4M12 12h8M4 18h12M20 18h0"/>'
               '<circle cx="16" cy="6" r="2"/><circle cx="10" cy="12" r="2"/><circle cx="18" cy="18" r="2"/>',
    "more": '<circle cx="5" cy="12" r="1.4" fill="currentColor"/><circle cx="12" cy="12" r="1.4" fill="currentColor"/>'
            '<circle cx="19" cy="12" r="1.4" fill="currentColor"/>',
    "plug": '<path d="M9 3v5M15 3v5M6 8h12v3a6 6 0 0 1-12 0Z"/><path d="M12 17v4"/>',
    "unplug": '<path d="M9 3v5M15 3v5M6 8h12v3a6 6 0 0 1-12 0Z"/><path d="M12 17v4M3 3l18 18"/>',
    "refresh": '<path d="M20 11a8 8 0 1 0-2.3 5.7"/><path d="M20 5v6h-6"/>',
    "spot": '<circle cx="12" cy="12" r="4"/><path d="M12 2v5M12 17v5M2 12h5M17 12h5"/>',
    "roi": '<rect x="4" y="5" width="16" height="14" rx="1.5" stroke-dasharray="3 2.2"/>',
    "mask": '<circle cx="12" cy="12" r="8"/><path d="M6.5 6.5l11 11"/>',
    "trash": '<path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13"/>',
    "download": '<path d="M12 4v11M7 10l5 5 5-5M5 20h14"/>',
    "check": '<path d="M5 12.5l4.5 4.5L19 7.5"/>',
    "image": '<rect x="3" y="4" width="18" height="16" rx="2"/><circle cx="9" cy="10" r="2"/>'
             '<path d="M21 16l-5-5-9 9"/>',
    "sparkles": '<path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8Z"/><path d="M19 16v4M17 18h4"/>',
    "bell": '<path d="M6 16V11a6 6 0 0 1 12 0v5l2 2H4Z"/><path d="M10 20a2 2 0 0 0 4 0"/>',
    "chart": '<path d="M4 4v16h16"/><path d="M7 15l4-5 3 3 5-7"/>',
    "eraser": '<path d="M4 16l9-9 6 6-7 7H7Z"/><path d="M11 20h9"/>',
    "cog": '<circle cx="12" cy="12" r="3"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9l2.1 2.1M17 17l2.1 2.1'
           'M4.9 19.1L7 17M17 7l2.1-2.1"/>',
    "video": '<rect x="3" y="6" width="13" height="12" rx="2"/><path d="M16 10l5-3v10l-5-3Z"/>',
}


@lru_cache(maxsize=None)
def icon(name: str, color: str = "#e6e8ee", size: int = 20) -> QIcon:
    body = _SVG[name].replace("currentColor", color)
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" '
           f'stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round">{body}</svg>')
    renderer = QSvgRenderer(QByteArray(svg.encode()))
    ic = QIcon()
    for s in (size, size * 2):
        pm = QPixmap(s, s)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        renderer.render(p)
        p.end()
        ic.addPixmap(pm)
    return ic


def _thermometer_pixmap(s: int) -> QPixmap:
    pm = QPixmap(s, s)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    # rounded tile with a warm gradient
    tile = QRectF(s * 0.04, s * 0.04, s * 0.92, s * 0.92)
    g = QLinearGradient(tile.topLeft(), tile.bottomRight())
    g.setColorAt(0.0, QColor("#ffb020"))
    g.setColorAt(0.55, QColor("#ff5a1f"))
    g.setColorAt(1.0, QColor("#c2185b"))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(g)
    p.drawRoundedRect(tile, s * 0.22, s * 0.22)
    # thermometer: white tube + bulb, red mercury
    cx = s * 0.5
    tube_w, bulb_r = s * 0.17, s * 0.15
    top, bulb_c = s * 0.16, s * 0.70
    path = QPainterPath()
    path.addRoundedRect(QRectF(cx - tube_w / 2, top, tube_w, bulb_c - top), tube_w / 2, tube_w / 2)
    path.addEllipse(QPointF(cx, bulb_c), bulb_r, bulb_r)
    p.setBrush(QColor("#ffffff"))
    p.drawPath(path.simplified())
    merc_w = tube_w * 0.42
    p.setBrush(QColor("#e5202e"))
    p.drawRoundedRect(QRectF(cx - merc_w / 2, s * 0.36, merc_w, bulb_c - s * 0.36), merc_w / 2, merc_w / 2)
    p.drawEllipse(QPointF(cx, bulb_c), bulb_r * 0.62, bulb_r * 0.62)
    # scale ticks
    p.setPen(QPen(QColor(255, 255, 255, 230), max(1.0, s * 0.022), cap=Qt.PenCapStyle.RoundCap))
    for k in range(4):
        y = top + s * 0.07 + k * s * 0.085
        p.drawLine(QPointF(cx + tube_w * 0.8, y), QPointF(cx + tube_w * (1.35 if k % 2 == 0 else 1.1), y))
    p.end()
    return pm


@lru_cache(maxsize=1)
def app_icon() -> QIcon:
    ic = QIcon()
    for s in (16, 24, 32, 48, 64, 128, 256):
        ic.addPixmap(_thermometer_pixmap(s))
    return ic


def logo_pixmap(size: int = 28) -> QPixmap:
    return _thermometer_pixmap(size)


def save_ico(path) -> None:
    """Writes a multi-size .ico (for shortcuts)."""
    app_icon().pixmap(256, 256).save(str(path), "ICO")
