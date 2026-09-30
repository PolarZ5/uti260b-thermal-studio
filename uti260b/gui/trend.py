"""Time-series graph with data recording controls and CSV export."""
from datetime import datetime
import time

import numpy as np
import pyqtgraph as pg
from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtWidgets import (QCheckBox, QComboBox, QFileDialog, QFrame, QHBoxLayout, QHeaderView, QLabel,
                             QMessageBox, QPushButton, QSplitter, QTableWidget, QTableWidgetItem,
                             QVBoxLayout, QWidget)

from ..series import CAM_KEYS, SPOT_KEYS, SeriesRecorder
from .capture import fmt_duration
from .icons import icon
from .theme import BORDER, CARD, COLORS, MUTED, PANEL, TEXT
from ..i18n import tr

NAMES = {"max": "Max", "min": "Min", "center": "Center", "mean": tr("เฉลี่ยทั้งภาพ"),
         "roi_max": "ROI max", "roi_min": "ROI min", "roi_mean": tr("ROI เฉลี่ย"),
         "cam1": tr("กล้อง P1"), "cam2": tr("กล้อง P2"), "cam3": tr("กล้อง P3")}
DEFAULT_ON = {"max", "min", "center", *SPOT_KEYS, *CAM_KEYS}
KEYS = ["max", "min", "center", "mean", "roi_max", "roi_min", "roi_mean", *SPOT_KEYS, *CAM_KEYS]
INTERVALS = [(tr("ทุกเฟรม"), 0.0), (tr("0.2 วิ"), 0.2), (tr("0.5 วิ"), 0.5), (tr("1 วิ"), 1.0), (tr("2 วิ"), 2.0),
             (tr("5 วิ"), 5.0), (tr("10 วิ"), 10.0), (tr("30 วิ"), 30.0), (tr("1 นาที"), 60.0)]
WINDOWS = [(tr("ทั้งหมด"), None), (tr("1 นาที"), 60), (tr("5 นาที"), 300), (tr("15 นาที"), 900), (tr("1 ชั่วโมง"), 3600)]


class Chip(QPushButton):
    """Checkable series toggle with the series colour."""

    def __init__(self, key, text):
        super().__init__()
        self.key = key
        self.label = text
        self.setCheckable(True)
        self.setChecked(key in DEFAULT_ON)
        col = COLORS[key]
        self.setStyleSheet(f"""
            QPushButton {{ background: transparent; border: 1px dashed {BORDER}; border-radius: 11px;
                           padding: 3px 10px; color: {MUTED}; font-size: 8.5pt; text-decoration: line-through; }}
            QPushButton:checked {{ background: {CARD}; border: 1px solid {col}; color: {TEXT};
                                   text-decoration: none; }}
        """)
        self.toggled.connect(self._update_text)
        self._update_text()

    def setText(self, text):                    # keep the on/off marker in front of the label
        self.label = text
        self._update_text()

    def _update_text(self, *_):
        on = self.isChecked()
        super().setText(("● " if on else "○ ") + self.label)
        self.setToolTip((tr("คลิกเพื่อซ่อนเส้น {name}", name=self.label) if on else tr("คลิกเพื่อแสดงเส้น {name}", name=self.label)))


class TrendPanel(QWidget):
    recordingChanged = pyqtSignal(str)

    def __init__(self, recorder: SeriesRecorder, preview: SeriesRecorder, folder_fn, parent=None):
        super().__init__(parent)
        self.rec = recorder
        self.preview = preview
        self.folder_fn = folder_fn          # -> Path of the output folder
        self.spot_labels = {}
        self.unit = "C"
        self.linked_video = False           # recording started by the video recorder
        self._t_start = None
        self._paused_total = 0.0
        self._pause_t = None
        self._build()

    # ----------------------------------------------------------------- ui
    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(6)

        bar = QFrame()
        bar.setObjectName("TrendBar")
        h = QHBoxLayout(bar)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(8)
        title = QLabel()
        title.setPixmap(icon("chart", "#ff7a18", 18).pixmap(18, 18))
        h.addWidget(title)
        t = QLabel(tr("กราฟอุณหภูมิตามเวลา"))
        t.setStyleSheet("font-weight: 600;")
        h.addWidget(t)
        h.addSpacing(10)

        self.btn_rec = QPushButton()
        self.btn_rec.setIconSize(QSize(14, 14))
        self.btn_rec.clicked.connect(self.toggle_record)
        self.btn_rec.setToolTip(tr("บันทึกค่า Max / Min / จุดกลาง / จุดวัด ตามเวลา (Ctrl+L)"))
        self.btn_pause = QPushButton()
        self.btn_pause.setIconSize(QSize(14, 14))
        self.btn_pause.clicked.connect(self.toggle_pause)
        self.cb_interval = QComboBox()
        for text, v in INTERVALS:
            self.cb_interval.addItem(text, v)
        self.cb_interval.setCurrentIndex(3)
        self.cb_interval.setToolTip(tr("ความถี่ในการบันทึกค่า"))
        self.cb_interval.currentIndexChanged.connect(self._interval_changed)
        self.pill = QLabel("")
        self.pill.setObjectName("Pill")
        for w in (self.btn_rec, self.btn_pause, QLabel(tr("ทุก")), self.cb_interval, self.pill):
            h.addWidget(w)
        h.addStretch(1)
        h.addWidget(QLabel(tr("แสดง")))
        self.cb_window = QComboBox()
        for text, v in WINDOWS:
            self.cb_window.addItem(text, v)
        self.cb_window.currentIndexChanged.connect(self.refresh)
        h.addWidget(self.cb_window)
        self.btn_clear = QPushButton(tr(" ล้าง"))
        self.btn_clear.setIcon(icon("trash", TEXT, 16))
        self.btn_clear.setToolTip(tr("ล้างข้อมูลในกราฟ"))
        self.btn_clear.clicked.connect(self.clear)
        self.btn_export = QPushButton(" Export CSV")
        self.btn_export.setIcon(icon("download", TEXT, 16))
        self.btn_export.clicked.connect(self.export_csv)
        h.addWidget(self.btn_clear)
        h.addWidget(self.btn_export)
        lay.addWidget(bar)

        # auto-save option lives in the Advanced panel of the main window
        self.chk_autosave = QCheckBox(tr("เขียน CSV ลงโฟลเดอร์ทันทีระหว่างบันทึกข้อมูล"))
        self.chk_autosave.setChecked(True)

        chips = QHBoxLayout()
        chips.setSpacing(4)
        self.chips = {}
        for key in KEYS:
            c = Chip(key, NAMES.get(key, key))
            c.toggled.connect(self.refresh)
            self.chips[key] = c
            chips.addWidget(c)
        chips.addStretch(1)
        lay.addLayout(chips)

        split = QSplitter(Qt.Orientation.Horizontal)
        pg.setConfigOptions(antialias=True, background=PANEL, foreground=MUTED)
        self.plot = pg.PlotWidget(axisItems={"bottom": pg.DateAxisItem(orientation="bottom")})
        self.plot.showGrid(x=True, y=True, alpha=0.15)
        self.plot.setLabel("left", "°C")
        self.plot.setClipToView(True)
        self.plot.setDownsampling(auto=True, mode="peak")
        self.curves = {k: self.plot.plot([], [], pen=pg.mkPen(COLORS[k], width=2), connect="finite") for k in KEYS}
        self.vline = pg.InfiniteLine(angle=90, movable=False,
                                     pen=pg.mkPen("#8b93a5", width=1, style=Qt.PenStyle.DashLine))
        self.plot.addItem(self.vline, ignoreBounds=True)
        self.hover_text = pg.TextItem(anchor=(0, 0), color=TEXT, fill=pg.mkBrush(21, 23, 28, 220))
        self.plot.addItem(self.hover_text, ignoreBounds=True)
        self.vline.hide()
        self.hover_text.hide()
        self.plot.scene().sigMouseMoved.connect(self._on_mouse)
        split.addWidget(self.plot)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels([tr("ค่า"), tr("ล่าสุด"), tr("ต่ำสุด"), tr("สูงสุด"), tr("เฉลี่ย")])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setMinimumWidth(340)
        split.addWidget(self.table)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 1)
        lay.addWidget(split, 1)
        self._sync_buttons()

    # ------------------------------------------------------------ control
    def _interval_changed(self):
        self.rec.interval = float(self.cb_interval.currentData())

    def active(self) -> SeriesRecorder:
        return self.rec if (self.rec.state != "idle" or len(self.rec)) else self.preview

    def elapsed(self) -> float:
        if self._t_start is None:
            return 0.0
        now = self._pause_t or time.time()
        return now - self._t_start - self._paused_total

    def start_recording(self, stream_path=None, linked_video=False):
        self._interval_changed()
        self.rec.start(stream_path)
        self.linked_video = linked_video
        self._t_start, self._paused_total, self._pause_t = time.time(), 0.0, None
        self._sync_buttons()
        self.recordingChanged.emit(self.rec.state)

    def stop_recording(self):
        self.rec.stop()
        self.linked_video = False
        if self._pause_t:
            self._paused_total += time.time() - self._pause_t
        self._pause_t = time.time()           # freeze the timer
        self._sync_buttons()
        self.recordingChanged.emit(self.rec.state)
        self.refresh()

    def toggle_record(self):
        if self.rec.state != "idle":
            if self.linked_video:
                QMessageBox.information(self, tr("กำลังอัดวิดีโอ"),
                                        tr("ข้อมูลชุดนี้บันทึกคู่กับวิดีโอ — หยุดที่ปุ่มบันทึกวิดีโอด้านบน"))
                return
            self.stop_recording()
            return
        if len(self.rec) and QMessageBox.question(
                self, tr("เริ่มบันทึกใหม่"), tr("ข้อมูลชุดก่อนหน้าในกราฟจะถูกล้าง ต้องการเริ่มใหม่หรือไม่?")) \
                != QMessageBox.StandardButton.Yes:
            return
        path = None
        if self.chk_autosave.isChecked():
            folder = self.folder_fn()
            folder.mkdir(parents=True, exist_ok=True)
            path = folder / f"uti_{time.strftime('%Y%m%d_%H%M%S')}_data.csv"
        self.start_recording(path)

    def toggle_pause(self):
        if self.rec.state == "recording":
            self.rec.pause()
            self._pause_t = time.time()
        elif self.rec.state == "paused":
            self.rec.start()
            if self._pause_t:
                self._paused_total += time.time() - self._pause_t
            self._pause_t = None
        self._sync_buttons()
        self.recordingChanged.emit(self.rec.state)

    def _sync_buttons(self):
        st = self.rec.state
        if st == "idle":
            self.btn_rec.setText(tr(" เริ่มบันทึกข้อมูล"))
            self.btn_rec.setIcon(icon("record", "#ff4d4f", 14))
            self.btn_rec.setObjectName("")
        else:
            self.btn_rec.setText(tr(" หยุด"))
            self.btn_rec.setIcon(icon("stop", "#ffffff", 14))
            self.btn_rec.setObjectName("Danger")
        self.btn_rec.style().unpolish(self.btn_rec)
        self.btn_rec.style().polish(self.btn_rec)
        self.btn_pause.setVisible(st != "idle")
        self.btn_pause.setText(tr(" ต่อ") if st == "paused" else tr(" พัก"))
        self.btn_pause.setIcon(icon("play" if st == "paused" else "pause", TEXT, 14))
        self.cb_interval.setEnabled(st == "idle")
        self.btn_clear.setEnabled(st == "idle")

    def clear(self):
        if self.rec.state != "idle":
            return
        if len(self.rec) and QMessageBox.question(
                self, tr("ล้างกราฟ"), tr("ล้างข้อมูลที่บันทึกไว้ในกราฟ? (ไฟล์ CSV ที่เขียนไว้แล้วจะไม่ถูกลบ)")) \
                != QMessageBox.StandardButton.Yes:
            return
        self.rec.clear()
        self.preview.clear()
        self._t_start = None
        self.refresh()

    def export_csv(self):
        src = self.active()
        if not len(src):
            QMessageBox.information(self, "Export CSV", tr("ยังไม่มีข้อมูล กด 'เริ่มบันทึกข้อมูล' ก่อน"))
            return
        folder = self.folder_fn()
        folder.mkdir(parents=True, exist_ok=True)
        default = folder / f"uti_{time.strftime('%Y%m%d_%H%M%S')}_export.csv"
        path, _ = QFileDialog.getSaveFileName(self, "Export CSV", str(default), "CSV (*.csv)")
        if not path:
            return
        n = src.export_csv(path)
        w = self.window()
        if hasattr(w, "toast"):
            w.toast(tr("Export {n} แถว → {path}", n=f"{n:,}", path=path), "ok")

    def set_spot_labels(self, spots):
        self.spot_labels = {f"P{s.slot}": f"P{s.slot} ({s.x},{s.y})" for s in spots}
        for k in SPOT_KEYS:
            self.chips[k].setText(self.spot_labels.get(k, k))

    # ---------------------------------------------------------------- draw
    def refresh(self):
        src = self.active()
        t = src.times()
        win = self.cb_window.currentData()
        st = self.rec.state
        if st in ("recording", "paused"):
            what = tr("วิดีโอ + ข้อมูล") if self.linked_video else tr("บันทึกข้อมูล")
            mark = "●" if st == "recording" else "⏸"
            self.pill.setText(f"{mark} {what}  {fmt_duration(self.elapsed())}  ·  " + tr("{n} แถว", n=f"{len(self.rec):,}"))
            self.pill.setObjectName("PillRec")
            path = self.rec.stream_path
            self.pill.setToolTip(str(path) if path else tr("ยังไม่ได้เขียนไฟล์ — กด Export CSV เมื่อหยุด"))
        elif src is self.rec:
            self.pill.setText(tr("บันทึกแล้ว  {dur}  ·  {n} แถว", dur=fmt_duration(self.elapsed()), n=f"{len(self.rec):,}"))
            self.pill.setObjectName("Pill")
        else:
            self.pill.setText(tr("Live preview · 2 นาทีล่าสุด"))
            self.pill.setObjectName("Pill")
        self.pill.style().unpolish(self.pill)
        self.pill.style().polish(self.pill)
        rows = []
        for key, curve in self.curves.items():
            has = src.has_data(key)
            self.chips[key].setVisible(has or key in ("max", "min", "center"))
            if not (self.chips[key].isChecked() and len(t) and has):
                curve.setData([], [])
                continue
            curve.setData(t, src.series(key))
            s = src.stats(key)
            if s:
                rows.append((key, s))
        if len(t):
            x1 = t[-1]
            x0 = t[0] if win is None else max(t[0], x1 - win)
            self.plot.setXRange(x0, max(x1, x0 + 1), padding=0.02)
            self.plot.enableAutoRange(axis="y")
        self.plot.setLabel("left", f"°{self.unit}")
        self._fill_table(rows)

    def _fill_table(self, rows):
        self.table.setRowCount(len(rows))
        u = self.unit
        for i, (key, s) in enumerate(rows):
            name = QTableWidgetItem("● " + self.spot_labels.get(key, NAMES.get(key, key)))
            name.setForeground(pg.mkColor(COLORS[key]))
            self.table.setItem(i, 0, name)
            for j, k in enumerate(("last", "min", "max", "mean"), 1):
                it = QTableWidgetItem(f"{s[k]:.1f}°{u}")
                it.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.table.setItem(i, j, it)

    def _on_mouse(self, pos):
        vb = self.plot.getPlotItem().vb
        src = self.active()
        t = src.times()
        if not self.plot.sceneBoundingRect().contains(pos) or len(t) == 0:
            self.vline.hide()
            self.hover_text.hide()
            return
        x = vb.mapSceneToView(pos).x()
        i = int(np.clip(np.searchsorted(t, x), 0, len(t) - 1))
        if i > 0 and abs(t[i - 1] - x) < abs(t[i] - x):
            i -= 1
        lines = [datetime.fromtimestamp(t[i]).strftime("%H:%M:%S.%f")[:-4]]
        for key in self.curves:
            if self.chips[key].isChecked() and src.has_data(key):
                v = src.series(key)[i]
                if not np.isnan(v):
                    lines.append(f"{self.spot_labels.get(key, NAMES.get(key, key))}: {v:.1f}°{self.unit}")
        self.vline.setPos(t[i])
        self.vline.show()
        self.hover_text.setText("\n".join(lines))
        (x0, x1), (y0, y1) = vb.viewRange()
        self.hover_text.setPos(t[i] if t[i] < (x0 + x1) / 2 else t[i] - (x1 - x0) * 0.22, y1)
        self.hover_text.show()
