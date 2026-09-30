"""Main window of the UTi260B viewer (PyQt6)."""
import json
import os
from pathlib import Path
import time

from PyQt6.QtCore import QEvent, QObject, Qt, QTimer
from PyQt6.QtGui import QColor, QKeySequence, QShortcut
from PyQt6.QtWidgets import (QButtonGroup, QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QFrame,
                             QGridLayout, QHBoxLayout, QHeaderView, QLabel, QMainWindow, QMenu,
                             QMessageBox, QPushButton, QRadioButton, QScrollArea, QSplitter, QTableWidget,
                             QTableWidgetItem, QTabWidget, QToolButton, QVBoxLayout, QWidget)

from ..bmpfile import read_uti_bmp
from ..decoder import Decoder, ThermalFrame
from ..measure import MAX_SPOTS, Measurement, Spot, free_slot, measure
from ..palettes import display_palette, display_palette_names
from ..render import base_image, display_span, palette_for
from ..series import SeriesRecorder
from ..sources import BACKENDS, CameraSource, DemoSource, guess_uti_index, list_cameras
from .capture import CaptureManager, fmt_duration
from .icons import app_icon, icon, logo_pixmap
from .theme import ACCENT, COLORS, MUTED, TEXT
from .trend import TrendPanel
from .view import Overlay, ThermalView, bgr_to_qimage, fmt, render_to_array
from .widgets import Card, RecordButton, SegmentedTools, Toast, icon_button

from ..paths import DEFAULT_CAPTURES as DEFAULT_FOLDER, SAMPLES, SETTINGS


def hint(text):
    lb = QLabel(text)
    lb.setObjectName("Hint")
    lb.setWordWrap(True)
    return lb


def section(text):
    lb = QLabel(text)
    lb.setObjectName("Section")
    return lb


def spin(lo=-40.0, hi=1100.0, value=0.0, step=0.5, suffix=" °C"):
    s = QDoubleSpinBox()
    s.setRange(lo, hi)
    s.setDecimals(1)
    s.setSingleStep(step)
    s.setValue(value)
    s.setSuffix(suffix)
    return s


def row(*widgets, stretch=True):
    h = QHBoxLayout()
    h.setSpacing(6)
    for w in widgets:
        if isinstance(w, str):
            w = QLabel(w)
        h.addWidget(w)
    if stretch:
        h.addStretch(1)
    return h


class _Resize(QObject):
    """Keeps the toast positioned when the image area is resized."""

    def __init__(self, toast):
        super().__init__(toast)
        self.toast = toast

    def eventFilter(self, obj, e):
        if e.type() == QEvent.Type.Resize and self.toast.isVisible():
            self.toast.reposition()
        return False


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("UTi260B Thermal Studio")
        self.setWindowIcon(app_icon())
        self.resize(1480, 960)
        self.decoder = Decoder()
        self.source = None
        self.frame: ThermalFrame | None = None
        self.m: Measurement | None = None
        self._raw = None
        self.last_seq = -1
        self.frozen = False
        self.spots: list[Spot] = []
        self.roi = None
        self.alarm = False
        self._last_beep = 0.0
        self._blink = False
        self.capture = CaptureManager(DEFAULT_FOLDER)
        self.recorder = SeriesRecorder(interval=1.0)
        self.preview = SeriesRecorder(interval=0.25, max_age=120)
        self.preview.start()

        self._build_header()
        self._build_body()
        self._build_shortcuts()
        self._load_settings()
        self._apply_decoder()
        self._update_folder_button()
        self.refresh_devices(auto_connect=True)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(15)
        self.ui_timer = QTimer(self)
        self.ui_timer.timeout.connect(self._ui_tick)
        self.ui_timer.start(500)

    # ================================================================ header
    def _build_header(self):
        bar = QFrame()
        bar.setObjectName("Header")
        h = QHBoxLayout(bar)
        h.setContentsMargins(14, 8, 14, 8)
        h.setSpacing(10)
        logo = QLabel()
        logo.setPixmap(logo_pixmap(34))
        h.addWidget(logo)
        titles = QVBoxLayout()
        titles.setSpacing(0)
        t = QLabel("UTi260B Thermal Studio")
        t.setObjectName("AppTitle")
        self.lb_conn = QLabel("ยังไม่เชื่อมต่อ")
        self.lb_conn.setObjectName("AppSub")
        titles.addWidget(t)
        titles.addWidget(self.lb_conn)
        h.addLayout(titles)
        h.addSpacing(16)

        self.cb_device = QComboBox()
        self.cb_device.setMinimumWidth(210)
        self.cb_device.setToolTip("เลือกกล้อง")
        h.addWidget(self.cb_device)
        self.btn_connect = QPushButton()
        self.btn_connect.clicked.connect(self.toggle_connect)
        h.addWidget(self.btn_connect)
        h.addStretch(1)

        self.btn_snap = QPushButton("  ถ่ายภาพ")
        self.btn_snap.setObjectName("Capture")
        self.btn_snap.setIcon(icon("camera", TEXT, 18))
        self.btn_snap.setToolTip("บันทึกภาพ + ตารางอุณหภูมิทุกพิกเซล (Ctrl+S)")
        self.btn_snap.clicked.connect(self.snapshot)
        h.addWidget(self.btn_snap)
        self.btn_rec = RecordButton("บันทึกวิดีโอ")
        self.btn_rec.setToolTip("อัดวิดีโอ MP4 พร้อม CSV ชื่อเดียวกัน (Ctrl+R)")
        self.btn_rec.clicked.connect(lambda: self.toggle_video())
        h.addWidget(self.btn_rec)

        self.btn_folder = QPushButton()
        self.btn_folder.setObjectName("Folder")
        self.btn_folder.setIcon(icon("folder", MUTED, 16))
        menu = QMenu(self)
        menu.addAction(icon("folder", TEXT, 16), "เปิดโฟลเดอร์", self.open_folder)
        menu.addAction(icon("sliders", TEXT, 16), "เปลี่ยนโฟลเดอร์ปลายทาง…", self.choose_folder)
        self.btn_folder.setMenu(menu)
        h.addWidget(self.btn_folder)

        more = QToolButton()
        more.setIcon(icon("more", TEXT, 20))
        more.setToolTip("เมนูเพิ่มเติม")
        more.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        m = QMenu(self)
        m.addAction(icon("refresh", TEXT, 16), "ค้นหากล้องใหม่", self.refresh_devices)
        m.addAction(icon("sparkles", TEXT, 16), "โหมดสาธิต (ภาพตัวอย่าง)", self.start_demo)
        m.addAction(icon("image", TEXT, 16), "เปิดไฟล์ BMP จากกล้อง…", self.open_bmp)
        m.addSeparator()
        m.addAction(icon("cog", TEXT, 16), "ตั้งค่าไดรเวอร์ UVC", self.driver_settings)
        more.setMenu(m)
        h.addWidget(more)

        self.btn_adv = QToolButton()
        self.btn_adv.setIcon(icon("sliders", TEXT, 18))
        self.btn_adv.setText(" ขั้นสูง")
        self.btn_adv.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.btn_adv.setCheckable(True)
        self.btn_adv.setToolTip("แสดง/ซ่อนการตั้งค่าขั้นสูง")
        self.btn_adv.toggled.connect(self._toggle_advanced)
        h.addWidget(self.btn_adv)
        self.header = bar

    # ================================================================== body
    def _build_body(self):
        root = QWidget()
        rl = QVBoxLayout(root)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(0)
        rl.addWidget(self.header)

        vsplit = QSplitter(Qt.Orientation.Vertical)
        hsplit = QSplitter(Qt.Orientation.Horizontal)
        self.trend = TrendPanel(self.recorder, self.preview, lambda: self.capture.folder)
        self.trend.recordingChanged.connect(lambda s: self._ui_tick())

        # ---- image column
        imgcol = QWidget()
        il = QVBoxLayout(imgcol)
        il.setContentsMargins(10, 8, 4, 4)
        il.setSpacing(6)
        tools = QHBoxLayout()
        self.seg = SegmentedTools([
            ("spot", " จุดวัด", "spot", "คลิกบนภาพเพื่อเพิ่มจุดวัด (คลิกขวาที่จุดเพื่อลบ)"),
            ("roi", " ROI", "roi", "ลากกรอบพื้นที่ที่ต้องการวัด"),
            ("mask", " ไม่วัด", "mask", "ลากกรอบพื้นที่ที่ไม่ต้องการวัด เช่น ตัวหนังสือบนจอกล้อง"),
        ])
        self.seg.toolChanged.connect(self.set_tool)
        tools.addWidget(self.seg)
        clear = icon_button("eraser", "ล้าง")
        clear.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        cm = QMenu(self)
        cm.addAction("ล้างจุดวัดทั้งหมด", self.clear_spots)
        cm.addAction("ล้างกรอบ ROI", lambda: self.set_roi(None))
        cm.addAction("ล้างพื้นที่ไม่วัด", self.clear_masks)
        clear.setMenu(cm)
        tools.addWidget(clear)
        self.btn_freeze = icon_button("pause", "หยุดภาพชั่วคราว (Space)", checkable=True)
        self.btn_freeze.toggled.connect(self.set_frozen)
        tools.addWidget(self.btn_freeze)
        tools.addStretch(1)
        self.lb_hover = QLabel("")
        self.lb_hover.setObjectName("Hint")
        tools.addWidget(self.lb_hover)
        il.addLayout(tools)

        self.view = ThermalView()
        self.view.spotAdded.connect(self.add_spot)
        self.view.spotRemoved.connect(self.remove_spot)
        self.view.roiChanged.connect(self.set_roi)
        self.view.maskAdded.connect(self.add_mask)
        self.view.hovered.connect(self.on_hover)
        il.addWidget(self.view, 1)
        self._toast = Toast(imgcol)
        imgcol.installEventFilter(_Resize(self._toast))
        hsplit.addWidget(imgcol)

        # ---- side panel
        side = QWidget()
        sl = QVBoxLayout(side)
        sl.setContentsMargins(8, 10, 12, 10)
        sl.setSpacing(10)
        grid = QGridLayout()
        grid.setSpacing(8)
        self.c_max = Card("สูงสุด", COLORS["max"])
        self.c_min = Card("ต่ำสุด", COLORS["min"])
        self.c_center = Card("จุดกลาง", COLORS["center"])
        self.c_mean = Card("เฉลี่ยทั้งภาพ")
        for i, c in enumerate((self.c_max, self.c_min, self.c_center, self.c_mean)):
            grid.addWidget(c, i // 2, i % 2)
        sl.addLayout(grid)
        self.c_roi = Card("ROI", COLORS["roi_max"], big=False)
        sl.addWidget(self.c_roi)

        self.spot_table = QTableWidget(0, 4)
        self.spot_table.setHorizontalHeaderLabels(["จุด", "ตำแหน่ง", "อุณหภูมิ", ""])
        self.spot_table.verticalHeader().setVisible(False)
        self.spot_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.spot_table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        hh = self.spot_table.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        self.spot_table.setColumnWidth(3, 36)
        sl.addWidget(self.spot_table)
        self.lb_spot_hint = hint("คลิกบนภาพเพื่อเพิ่มจุดวัด (สูงสุด 6 จุด)")
        sl.addWidget(self.lb_spot_hint)
        self.lb_cam = hint("")
        self.lb_cam.setToolTip("ค่าจาก Point Temperature ของกล้อง (อ่านด้วย OCR) ใช้สอบเทียบภาพด้วย")
        sl.addWidget(self.lb_cam)

        quick = QFrame()
        quick.setObjectName("Card")
        ql = QVBoxLayout(quick)
        ql.setContentsMargins(12, 10, 12, 10)
        ql.setSpacing(8)
        self.cb_palette = QComboBox()
        self.cb_palette.addItems(["original"] + display_palette_names())
        self.cb_palette.currentTextChanged.connect(self._redraw)
        pal_ic = QLabel()
        pal_ic.setPixmap(icon("image", MUTED, 16).pixmap(16, 16))
        ql.addLayout(row(pal_ic, "Palette", self.cb_palette))
        self.chk_alarm = QCheckBox("แจ้งเตือนเมื่อสูงกว่า")
        self.sp_alarm_hi = spin(value=60, step=1)
        bell = QLabel()
        bell.setPixmap(icon("bell", MUTED, 16).pixmap(16, 16))
        ql.addLayout(row(bell, self.chk_alarm, self.sp_alarm_hi))
        sl.addWidget(quick)

        self.adv = self._build_advanced()
        self.adv.setVisible(False)
        sl.addWidget(self.adv)
        sl.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(side)
        scroll.setMinimumWidth(420)
        self.side_scroll = scroll
        hsplit.addWidget(scroll)
        hsplit.setStretchFactor(0, 3)
        hsplit.setStretchFactor(1, 1)

        vsplit.addWidget(hsplit)
        vsplit.addWidget(self.trend)
        vsplit.setStretchFactor(0, 3)
        vsplit.setStretchFactor(1, 2)
        vsplit.setSizes([600, 330])
        rl.addWidget(vsplit, 1)
        self.setCentralWidget(root)
        self.status = self.statusBar()
        self._rebuild_spot_table()

    def _build_advanced(self):
        box = QFrame()
        box.setObjectName("Advanced")
        bl = QVBoxLayout(box)
        bl.setContentsMargins(8, 8, 8, 8)
        head = QHBoxLayout()
        ic = QLabel()
        ic.setPixmap(icon("sliders", ACCENT, 16).pixmap(16, 16))
        head.addWidget(ic)
        head.addWidget(section("การตั้งค่าขั้นสูง"))
        head.addStretch(1)
        bl.addLayout(head)
        tabs = QTabWidget()
        tabs.addTab(self._adv_measure(), "การวัด")
        tabs.addTab(self._adv_display(), "แสดงผล")
        tabs.addTab(self._adv_alarm(), "แจ้งเตือน")
        tabs.addTab(self._adv_record(), "บันทึก")
        tabs.addTab(self._adv_camera(), "กล้อง")
        bl.addWidget(tabs)
        return box

    def _adv_measure(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(section("สเกลอุณหภูมิ"))
        self.rb_osd = QRadioButton("อ่านจากแถบสีของกล้อง (อัตโนมัติ)")
        self.rb_manual = QRadioButton("กำหนดเอง")
        self.rb_osd.setChecked(True)
        g = QButtonGroup(w)
        g.addButton(self.rb_osd)
        g.addButton(self.rb_manual)
        lay.addWidget(self.rb_osd)
        self.sp_man_min, self.sp_man_max = spin(value=20), spin(value=40)
        lay.addLayout(row(self.rb_manual, self.sp_man_min, "ถึง", self.sp_man_max))
        self.cb_unit = QComboBox()
        self.cb_unit.addItems(["C", "F"])
        lay.addLayout(row("หน่วย", self.cb_unit))
        for s in (self.rb_osd, self.rb_manual):
            s.toggled.connect(self._apply_decoder)
        for s in (self.sp_man_min, self.sp_man_max):
            s.valueChanged.connect(self._apply_decoder)
        self.cb_unit.currentTextChanged.connect(self._apply_decoder)
        lay.addWidget(section("อ่านค่าจากจอกล้อง"))
        self.chk_center_fix = QCheckBox("สอบเทียบด้วยค่าจุดกลาง + Point Temperature ของกล้อง")
        self.chk_center_fix.setChecked(True)
        self.chk_markers = QCheckBox("ใช้ตำแหน่ง/ค่าจุดร้อน-เย็นจากเป้าของกล้อง")
        self.chk_markers.setChecked(True)
        self.chk_overlay = QCheckBox("ตัดตัวหนังสือ/เป้าเล็งของกล้องออกจากการวัด")
        self.chk_overlay.setChecked(True)
        for c in (self.chk_center_fix, self.chk_markers, self.chk_overlay):
            c.toggled.connect(self._apply_decoder)
            lay.addWidget(c)
        lay.addWidget(section("เครื่องหมายบนภาพ"))
        self.chk_hot, self.chk_cold, self.chk_center = (QCheckBox("จุดร้อนสุด"), QCheckBox("จุดเย็นสุด"),
                                                         QCheckBox("จุดกลาง"))
        for c in (self.chk_hot, self.chk_cold, self.chk_center):
            c.setChecked(True)
            c.toggled.connect(self._redraw)
        lay.addLayout(row(self.chk_hot, self.chk_cold, self.chk_center))
        lay.addStretch(1)
        return w

    def _adv_display(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        self.chk_clean = QCheckBox("ลบตัวหนังสือ/สัญลักษณ์ของกล้องออกจากภาพ (clean)")
        self.chk_clean.toggled.connect(self._redraw)
        lay.addWidget(self.chk_clean)
        self.chk_span = QCheckBox("ล็อกช่วงสี")
        self.chk_span.toggled.connect(self._redraw)
        self.sp_span_min, self.sp_span_max = spin(value=20), spin(value=40)
        for s in (self.sp_span_min, self.sp_span_max):
            s.valueChanged.connect(self._redraw)
        lay.addLayout(row(self.chk_span, self.sp_span_min, "ถึง", self.sp_span_max))
        b = QPushButton("ใช้ช่วงของภาพปัจจุบัน")
        b.clicked.connect(self.lock_current_span)
        lay.addLayout(row(b))
        lay.addWidget(hint("ล็อกช่วงสีเพื่อเปรียบเทียบภาพต่อเนื่องได้ แม้กล้องจะปรับช่วงเอง "
                           "(ใช้กับ palette อื่นที่ไม่ใช่ original หรือเมื่อเปิด clean)"))
        lay.addStretch(1)
        return w

    def _adv_alarm(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        self.sp_alarm_lo = spin(value=-20, step=1)
        self.chk_alarm_lo = QCheckBox("แจ้งเตือนเมื่อต่ำกว่า")
        lay.addLayout(row(self.chk_alarm_lo, self.sp_alarm_lo))
        self.cb_alarm_target = QComboBox()
        self.cb_alarm_target.addItems(["ทั้งภาพ", "ROI", "จุดวัดทุกจุด", "จุดกลาง"])
        lay.addLayout(row("ตรวจที่", self.cb_alarm_target))
        self.chk_sound = QCheckBox("มีเสียงเตือน")
        self.chk_sound.setChecked(True)
        lay.addWidget(self.chk_sound)
        lay.addStretch(1)
        return w

    def _adv_record(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(self.trend.chk_autosave)
        self.cb_video_scale = QComboBox()
        for text, v in (("1× (240×320)", 1.0), ("2× (480×640)", 2.0), ("3× (720×960)", 3.0)):
            self.cb_video_scale.addItem(text, v)
        self.cb_video_scale.setCurrentIndex(1)
        lay.addLayout(row("ขนาดวิดีโอ/ภาพ", self.cb_video_scale))
        lay.addWidget(hint("ระหว่างอัดวิดีโอ ค่าที่วัดได้จะถูกบันทึกลง CSV ชื่อเดียวกับวิดีโอ "
                           "ตามความถี่ที่ตั้งในแผงกราฟ ไฟล์ทั้งหมดอยู่ในโฟลเดอร์ปลายทางที่เลือกไว้"))
        lay.addStretch(1)
        return w

    def _adv_camera(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        self.cb_backend = QComboBox()
        self.cb_backend.addItems(list(BACKENDS))
        lay.addLayout(row("Backend", self.cb_backend))
        self.cb_rotation = QComboBox()
        self.cb_rotation.addItems(["auto", "0", "90", "180", "270"])
        self.cb_rotation.currentTextChanged.connect(self._apply_decoder)
        lay.addLayout(row("หมุนภาพ", self.cb_rotation))
        lay.addWidget(hint(
            "ที่ตัวกล้อง: Settings → USB Mode → USB Camera\n"
            "ใช้ Image Mode = Thermal และเปิด Center Spot ไว้เพื่อให้สอบเทียบได้แม่น\n"
            "การตั้งค่าในตัวกล้อง (palette, emissivity, gain) ต้องกดที่ตัวกล้อง"))
        lay.addStretch(1)
        return w

    def _build_shortcuts(self):
        for seq, fn in (("Space", lambda: self.btn_freeze.toggle()), ("Ctrl+S", self.snapshot),
                        ("Ctrl+R", lambda: self.toggle_video()), ("Ctrl+L", self.trend.toggle_record),
                        ("Ctrl+1", lambda: self.set_tool("spot")), ("Ctrl+2", lambda: self.set_tool("roi")),
                        ("Ctrl+3", lambda: self.set_tool("mask"))):
            QShortcut(QKeySequence(seq), self, activated=fn)

    def _toggle_advanced(self, on):
        self.adv.setVisible(on)
        if on:
            QTimer.singleShot(50, lambda: self.side_scroll.ensureWidgetVisible(self.adv, 0, 0))

    # ============================================================ helpers
    def toast(self, text, kind="ok", action=None, callback=None):
        self._toast.show_message(text, kind, action, callback)

    def _update_folder_button(self):
        f = self.capture.folder
        name = f.name or str(f)
        self.btn_folder.setText(f"  {name if len(name) <= 22 else name[:20] + '…'}")
        self.btn_folder.setToolTip(f"โฟลเดอร์ปลายทาง:\n{f}")

    def choose_folder(self):
        d = QFileDialog.getExistingDirectory(self, "เลือกโฟลเดอร์ปลายทาง", str(self.capture.folder))
        if d:
            self.capture.set_folder(d)
            self._update_folder_button()
            self.toast(f"บันทึกไฟล์ไปที่ {d}", "info")

    def open_folder(self):
        self.capture.folder.mkdir(parents=True, exist_ok=True)
        os.startfile(self.capture.folder)

    # ============================================================= sources
    def refresh_devices(self, auto_connect=False):
        cams = list_cameras()
        self.cb_device.clear()
        for i, n in cams:
            self.cb_device.addItem(icon("camera", MUTED, 16), f"{n}  (#{i})", i)
        guess = guess_uti_index(cams)
        if guess is not None:
            self.cb_device.setCurrentIndex([i for i, _ in cams].index(guess))
        if not cams:
            self.cb_device.addItem("ไม่พบกล้อง — ตั้ง USB Mode = USB Camera", None)
        self._sync_connect()
        if auto_connect and guess is not None and self.source is None:
            self.connect_camera()

    def _sync_connect(self):
        on = self.source is not None
        self.btn_connect.setText("  ตัดการเชื่อมต่อ" if on else "  เชื่อมต่อ")
        self.btn_connect.setIcon(icon("unplug" if on else "plug", TEXT, 16))
        if not on:
            self.lb_conn.setText("ยังไม่เชื่อมต่อ")

    def _set_source(self, src):
        self.disconnect()
        try:
            src.start()
        except Exception as e:
            QMessageBox.critical(self, "เชื่อมต่อไม่ได้", str(e))
            return False
        self.source = src
        self.last_seq = -1
        self.btn_freeze.setChecked(False)
        self.decoder._auto_rot = None
        self.preview.clear()
        self._sync_connect()
        return True

    def toggle_connect(self):
        if self.source is not None:
            self.disconnect()
        else:
            self.connect_camera()

    def connect_camera(self):
        idx = self.cb_device.currentData()
        if idx is None:
            self.refresh_devices()
            idx = self.cb_device.currentData()
        if idx is None:
            self.toast("ไม่พบกล้อง — ตั้งกล้องเป็น USB Mode = USB Camera แล้วเสียบสายใหม่", "error")
            return
        if self._set_source(CameraSource(idx, self.cb_backend.currentText(), name=self.cb_device.currentText())):
            self.toast("เชื่อมต่อกล้องแล้ว", "ok")

    def start_demo(self):
        try:
            if self._set_source(DemoSource(SAMPLES)):
                self.toast("โหมดสาธิต: เล่นภาพตัวอย่าง", "info")
        except Exception as e:
            QMessageBox.critical(self, "Demo", str(e))

    def disconnect(self):
        if self.capture.video is not None:
            self.toggle_video(False)
        if self.source is not None:
            self.source.stop()
            self.source = None
        self._sync_connect()

    def open_bmp(self):
        path, _ = QFileDialog.getOpenFileName(self, "เปิดไฟล์ภาพจากกล้อง (USB Mode = USB Disk)", "",
                                              "UTi images (*.bmp *.BMP);;All (*.*)")
        if not path:
            return
        try:
            bmp = read_uti_bmp(path)
        except Exception as e:
            QMessageBox.critical(self, "อ่านไฟล์ไม่ได้", str(e))
            return
        self.disconnect()
        self.frame = Decoder.from_bmp(bmp)
        self._raw = bmp.screen_bgr
        self.cb_unit.setCurrentText(bmp.unit)
        self.frozen = True
        self._process(new=False)
        self.lb_conn.setText(f"ไฟล์ {Path(path).name} · emissivity {bmp.emissivity:.2f}")

    def driver_settings(self):
        if isinstance(self.source, CameraSource):
            self.source.open_driver_settings()
        else:
            self.toast("ต้องเชื่อมต่อกล้องด้วย Backend = DirectShow ก่อน", "info")

    def set_frozen(self, on):
        self.frozen = on
        self.btn_freeze.setIcon(icon("play" if on else "pause", ACCENT if on else TEXT, 18))
        self.btn_freeze.setToolTip("เล่นต่อ (Space)" if on else "หยุดภาพชั่วคราว (Space)")

    # =============================================================== tools
    def set_tool(self, key):
        self.view.tool = key
        self.seg.set_tool(key)

    def add_spot(self, x, y):
        slot = free_slot(self.spots)
        if slot is None:
            self.toast(f"มีจุดวัดครบ {MAX_SPOTS} จุดแล้ว — คลิกขวาที่จุดเพื่อลบ", "info")
            return
        self.spots.append(Spot(slot, x, y))
        self.spots.sort(key=lambda s: s.slot)
        self._spots_changed()

    def remove_spot(self, slot):
        self.spots = [s for s in self.spots if s.slot != slot]
        self._spots_changed()

    def clear_spots(self):
        self.spots.clear()
        self._spots_changed()

    def _spots_changed(self):
        self.trend.set_spot_labels(self.spots)
        self._rebuild_spot_table()
        self._process(new=False)

    def set_roi(self, r):
        self.roi = r
        self._process(new=False)

    def add_mask(self, r):
        self.decoder.exclude_rects.append(tuple(r))
        self._apply_decoder()

    def clear_masks(self):
        self.decoder.exclude_rects = []
        self._apply_decoder()

    def lock_current_span(self):
        if self.frame is not None and self.frame.has_scale:
            self.sp_span_min.setValue(self.frame.t_min)
            self.sp_span_max.setValue(self.frame.t_max)
            self.chk_span.setChecked(True)

    def on_hover(self, x, y):
        if x < 0 or self.frame is None:
            self.lb_hover.setText("")
            return
        h, w = self.frame.shape
        if 0 <= x < w and 0 <= y < h:
            t = self.frame.temp_at(x, y, 0)
            self.lb_hover.setText(f"({x}, {y})   {fmt(t, self.unit) if t is not None else 'วัดไม่ได้'}")

    # ============================================================ pipeline
    @property
    def unit(self):
        return self.frame.unit if self.frame is not None and self.frame.layout == "bmp" else self.cb_unit.currentText()

    def _apply_decoder(self, *a):
        d = self.decoder
        d.range_mode = "manual" if self.rb_manual.isChecked() else "osd"
        lo, hi = self.sp_man_min.value(), self.sp_man_max.value()
        d.manual_range = (min(lo, hi), max(lo, hi))
        d.detect_overlay = self.chk_overlay.isChecked()
        d.use_center_fix = self.chk_center_fix.isChecked()
        d.use_camera_markers = self.chk_markers.isChecked()
        d.unit = self.cb_unit.currentText()
        rot = self.cb_rotation.currentText()
        d.rotation = rot if rot == "auto" else int(rot)
        d._auto_rot = None
        if self._raw is not None and (self.frozen or self.source is None) and \
                (self.frame is None or self.frame.layout != "bmp"):
            self.frame = d.decode(self._raw)
        self.trend.unit = self.cb_unit.currentText()
        self._process(new=False)

    def _tick(self):
        if self.source is None or self.frozen:
            return
        raw, seq = self.source.read()
        if raw is not None and seq != self.last_seq:
            self.last_seq = seq
            self._raw = raw
            try:
                self.frame = self.decoder.decode(raw)
            except Exception as e:
                self.status.showMessage(f"decode error: {e}")
                return
            self._process(new=True)
        if self.source is not None and self.source.error:
            self.status.showMessage(self.source.error)

    def _process(self, new: bool):
        if self.frame is None:
            self.view.set_frame(None, Overlay())
            return
        self.m = measure(self.frame, self.spots, self.roi, self.unit)
        if new:
            self.m.t = time.time()
            self.recorder.offer(self.m)
            self.preview.offer(self.m)
            self._check_alarm()
        self._redraw()
        self._update_cards()
        if new and self.capture.video is not None:
            try:
                self.capture.video.write(self._render_file(), self.m)
            except Exception as e:
                self.toggle_video(False)
                self.toast(f"อัดวิดีโอไม่ได้: {e}", "error")

    def _render_file(self):
        return render_to_array(self.view.image, self.view.ov, float(self.cb_video_scale.currentData()))

    def _overlay(self) -> Overlay:
        f = self.frame
        span = (self.sp_span_min.value(), self.sp_span_max.value()) if self.chk_span.isChecked() else None
        pal = self.cb_palette.currentText()
        recolored = pal != "original" or self.chk_clean.isChecked()
        lo, hi = display_span(f, span if recolored else None)
        if f.menu_open:
            note = "เมนูของกล้องเปิดอยู่ — กด Back ที่กล้องเพื่อให้วัดได้ครบทั้งภาพ"
        elif not f.has_scale:
            note = "ยังไม่มีสเกลอุณหภูมิ — ตั้งช่วงเองใน ขั้นสูง › การวัด"
        elif f.range_source == "partial":
            note = "ค่า Min ของสเกลถูกบัง — ใช้ค่าล่าสุดที่อ่านได้"
        else:
            note = ""
        return Overlay(m=self.m, spots=list(self.spots), roi=self.roi, masks=list(self.decoder.exclude_rects),
                       show_hot=self.chk_hot.isChecked(), show_cold=self.chk_cold.isChecked(),
                       show_center=self.chk_center.isChecked(), unit=self.unit,
                       lut=display_palette(palette_for(f, pal)), span=(lo, hi), alarm=self.alarm, note=note)

    def _redraw(self, *a):
        if self.frame is None:
            return
        pal = self.cb_palette.currentText()
        span = (self.sp_span_min.value(), self.sp_span_max.value()) if self.chk_span.isChecked() else None
        img = base_image(self.frame, pal, self.chk_clean.isChecked(), span)
        self.view.set_frame(bgr_to_qimage(img), self._overlay())

    def _update_cards(self):
        m, u, f = self.m, self.unit, self.frame
        src = " · จากกล้อง" if m.from_camera else ""
        self.c_max.value.setText(fmt(m.max, u))
        self.c_max.sub.setText(f"{m.max_xy}{src}" if m.max_xy else "")
        self.c_min.value.setText(fmt(m.min, u))
        self.c_min.sub.setText(f"{m.min_xy}{src}" if m.min_xy else "")
        self.c_center.value.setText(fmt(m.center, u))
        self.c_center.sub.setText("ค่าจากกล้อง" if f.center_temp is not None else "")
        self.c_mean.value.setText(fmt(m.mean, u))
        n_cal = len(f.calibration)
        cal = f" · สอบเทียบ {n_cal} จุด" if n_cal > 2 and f.layout != "bmp" else ""
        self.c_mean.sub.setText(f"สเกล {fmt(f.t_min, u)}–{fmt(f.t_max, u)}{cal}")
        self.c_roi.setVisible(m.roi is not None)
        if m.roi:
            self.c_roi.value.setText(f"▲ {fmt(m.roi['max'], u)}   ▼ {fmt(m.roi['min'], u)}   Ø {fmt(m.roi['mean'], u)}")
            x0, y0, x1, y1 = self.roi
            self.c_roi.sub.setText(f"({x0},{y0}) – ({x1},{y1})")
        for r, sp in enumerate(self.spots):
            t = m.spots.get(sp.slot, (0, 0, None))[2]
            it = self.spot_table.item(r, 2)
            if it:
                it.setText(fmt(t, u) if t is not None else "วัดไม่ได้")
        if m.cam_points:
            self.lb_cam.setText("จุดวัดของกล้อง:  " + "   ".join(
                f"P{n} {fmt(t, u)} ({x},{y})" for n, (x, y, t) in sorted(m.cam_points.items())))
        else:
            self.lb_cam.setText("")

    def _rebuild_spot_table(self):
        tb = self.spot_table
        tb.setRowCount(len(self.spots))
        for r, sp in enumerate(self.spots):
            name = QTableWidgetItem(f"● P{sp.slot}")
            name.setForeground(QColor(COLORS[f"P{sp.slot}"]))
            tb.setItem(r, 0, name)
            tb.setItem(r, 1, QTableWidgetItem(f"({sp.x}, {sp.y})"))
            tb.setItem(r, 2, QTableWidgetItem("--"))
            b = QToolButton()
            b.setIcon(icon("trash", MUTED, 14))
            b.setToolTip(f"ลบจุด P{sp.slot}")
            b.clicked.connect(lambda _, s=sp.slot: self.remove_spot(s))
            tb.setCellWidget(r, 3, b)
        tb.setVisible(bool(self.spots))
        tb.resizeRowsToContents()
        h = tb.horizontalHeader().sizeHint().height() + sum(tb.rowHeight(r) for r in range(tb.rowCount()))
        tb.setFixedHeight(h + 6)
        self.lb_spot_hint.setVisible(not self.spots)

    def _check_alarm(self):
        m = self.m
        was = self.alarm
        self.alarm = False
        hi_on, lo_on = self.chk_alarm.isChecked(), self.chk_alarm_lo.isChecked()
        if hi_on or lo_on:
            target = self.cb_alarm_target.currentIndex()
            vals = []
            if target == 0:
                vals = [m.max, m.min]
            elif target == 1 and m.roi:
                vals = [m.roi["max"], m.roi["min"]]
            elif target == 2:
                vals = [t for (_, _, t) in m.spots.values()]
            elif target == 3:
                vals = [m.center]
            vals = [v for v in vals if v is not None]
            hi, lo = self.sp_alarm_hi.value(), self.sp_alarm_lo.value()
            self.alarm = any((hi_on and v > hi) or (lo_on and v < lo) for v in vals)
        now = time.time()
        if self.alarm and self.chk_sound.isChecked() and now - self._last_beep > 1.0:
            self._last_beep = now
            try:
                import winsound
                winsound.MessageBeep(winsound.MB_ICONHAND)
            except Exception:
                pass
        if self.alarm and not was:
            self.toast("อุณหภูมิเกินเกณฑ์ที่ตั้งไว้", "error")

    def _ui_tick(self):
        """Twice a second: blinking record indicators, timers, graph, connection line."""
        self._blink = not self._blink
        self.view.blink = self._blink
        badges = []
        v = self.capture.video
        if v is not None:
            t = fmt_duration(v.elapsed)
            self.btn_rec.set_recording(True, t)
            badges.append((f"REC  {t}", "#ff3b3b"))
        elif self.btn_rec.isChecked():
            self.btn_rec.set_recording(False)
        if self.recorder.state == "recording" and not self.trend.linked_video:
            badges.append((f"DATA  {fmt_duration(self.trend.elapsed())}", "#ffb020"))
        self.view.rec_badges = badges
        self.view.update()
        self.trend.refresh()
        if self.source is not None and self.frame is not None:
            f = self.frame
            self.lb_conn.setText(f"● {self.source.name.split('  (')[0]} · {self.source.fps:.1f} fps · "
                                 f"palette {f.palette} · สเกล {fmt(f.t_min, self.unit)}–{fmt(f.t_max, self.unit)}")

    # ============================================================ outputs
    def snapshot(self):
        if self.frame is None:
            self.toast("ยังไม่มีภาพให้บันทึก", "error")
            return
        try:
            paths = self.capture.snapshot(self.frame, self.m, self._render_file(), {"roi_rect": self.roi})
        except Exception as e:
            self.toast(f"บันทึกภาพไม่ได้: {e}", "error")
            return
        self.view.flash()
        self.toast(f"บันทึกภาพแล้ว  {paths[0].name}", "ok", "เปิดโฟลเดอร์", self.open_folder)

    def toggle_video(self, on=None):
        on = (self.capture.video is None) if on is None else on
        if not on:
            v = self.capture.stop_video()
            if self.trend.linked_video:
                self.trend.stop_recording()
            self.btn_rec.set_recording(False)
            self.view.rec_badges = []
            if v is not None:
                self.toast(f"บันทึกแล้ว  {v.video_path.name} + {v.csv_path.name}  ({fmt_duration(v.elapsed)})",
                           "ok", "เปิดโฟลเดอร์", self.open_folder)
            return
        if self.frame is None or self.view.image is None:
            self.toast("ยังไม่มีภาพ — เชื่อมต่อกล้องก่อน", "error")
            self.btn_rec.set_recording(False)
            return
        if self.recorder.state == "idle":
            if len(self.recorder) and QMessageBox.question(
                    self, "บันทึกวิดีโอ", "ข้อมูลในกราฟชุดก่อนหน้าจะถูกแทนที่ด้วยข้อมูลของวิดีโอนี้ ดำเนินการต่อ?") \
                    != QMessageBox.StandardButton.Yes:
                self.btn_rec.set_recording(False)
                return
            series, feed = self.recorder, False
            self.trend._interval_changed()
        else:
            series, feed = SeriesRecorder(interval=self.recorder.interval), True
        fps = self.source.fps if self.source is not None and self.source.fps > 1 else 10
        try:
            v = self.capture.start_video(self._render_file(), fps, series, feed)
        except Exception as e:
            self.toast(str(e), "error")
            self.btn_rec.set_recording(False)
            return
        if not feed:
            self.trend.linked_video = True
            self.trend._t_start, self.trend._paused_total, self.trend._pause_t = time.time(), 0.0, None
            self.trend._sync_buttons()
        self.btn_rec.set_recording(True, "00:00:00")
        self.toast(f"เริ่มบันทึกวิดีโอ  {v.video_path.name}", "rec")
        self._ui_tick()

    # =========================================================== settings
    def _widgets(self):
        return {
            "backend": self.cb_backend, "rotation": self.cb_rotation, "unit": self.cb_unit,
            "palette": self.cb_palette, "alarm_target": self.cb_alarm_target, "video_scale": self.cb_video_scale,
            "man_min": self.sp_man_min, "man_max": self.sp_man_max, "span_min": self.sp_span_min,
            "span_max": self.sp_span_max, "alarm_hi": self.sp_alarm_hi, "alarm_lo": self.sp_alarm_lo,
            "manual": self.rb_manual, "hot": self.chk_hot, "cold": self.chk_cold, "center": self.chk_center,
            "overlay": self.chk_overlay, "center_fix": self.chk_center_fix, "markers": self.chk_markers,
            "clean": self.chk_clean, "span": self.chk_span, "alarm": self.chk_alarm, "alarm_lo_on": self.chk_alarm_lo,
            "sound": self.chk_sound, "autosave": self.trend.chk_autosave,
            "interval": self.trend.cb_interval, "window": self.trend.cb_window, "advanced": self.btn_adv,
        }

    INDEX_COMBOS = ("alarm_target", "interval", "window", "video_scale")

    def _load_settings(self):
        try:
            data = json.loads(SETTINGS.read_text("utf-8"))
        except (OSError, ValueError):
            return
        for k, w in self._widgets().items():
            if k not in data:
                continue
            v = data[k]
            try:
                if isinstance(w, QComboBox):
                    if k in self.INDEX_COMBOS:
                        w.setCurrentIndex(int(v))
                    else:
                        w.setCurrentText(str(v))
                elif isinstance(w, QDoubleSpinBox):
                    w.setValue(float(v))
                else:
                    w.setChecked(bool(v))
            except (TypeError, ValueError):
                pass
        if data.get("folder"):
            self.capture.folder = Path(data["folder"])
        self.decoder.exclude_rects = [tuple(r) for r in data.get("masks", [])]
        self.spots = [Spot(*s) for s in data.get("spots", [])][:MAX_SPOTS]
        self.roi = tuple(data["roi"]) if data.get("roi") else None
        self._spots_changed()

    def _save_settings(self):
        data = {}
        for k, w in self._widgets().items():
            if isinstance(w, QComboBox):
                data[k] = w.currentIndex() if k in self.INDEX_COMBOS else w.currentText()
            elif isinstance(w, QDoubleSpinBox):
                data[k] = w.value()
            else:
                data[k] = w.isChecked()
        data.update(folder=str(self.capture.folder), masks=self.decoder.exclude_rects, roi=self.roi,
                    spots=[[s.slot, s.x, s.y] for s in self.spots])
        try:
            SETTINGS.parent.mkdir(parents=True, exist_ok=True)
            SETTINGS.write_text(json.dumps(data, indent=1, ensure_ascii=False), "utf-8")
        except OSError:
            pass

    def closeEvent(self, e):
        busy = self.capture.video is not None or self.recorder.state != "idle"
        if busy and QMessageBox.question(self, "กำลังบันทึก", "หยุดบันทึกและปิดโปรแกรม?") \
                != QMessageBox.StandardButton.Yes:
            e.ignore()
            return
        if self.capture.video is not None:
            self.toggle_video(False)
        self.recorder.stop()
        self._save_settings()
        self.disconnect()
        e.accept()

