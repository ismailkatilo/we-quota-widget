import time
import threading
import re
import json
import os
import sys
import ctypes
import base64
import io
import traceback
import webbrowser
from datetime import datetime, timedelta

from PySide6.QtWidgets import (
    QApplication, QWidget, QLabel, QHBoxLayout, QVBoxLayout,
    QDialog, QLineEdit, QPushButton, QComboBox, QSizePolicy,
    QSystemTrayIcon, QMenu, QGraphicsDropShadowEffect
)
from PySide6.QtCore import Qt, QTimer, Signal, QObject, QPoint, QSize
from PySide6.QtGui import (
    QFont, QColor, QPainter, QPainterPath, QIcon, QPixmap,
    QImage, QBrush, QPen, QAction, QActionGroup
)
from PIL import Image

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

try:
    from winotify import Notification, audio
    HAS_WINOTIFY = True
except ImportError:
    HAS_WINOTIFY = False

# ==========================================
# CONFIGURATION & PATHS
# ==========================================
APP_VERSION = "0.9.6-beta"
CONFIG_FILENAME  = "config.json"
COOKIES_FILENAME = "cookies.json"

SIZES = {
    "small":  {"w": 240, "h": 120, "f_main": 38, "f_tot": 13, "f_days": 11, "f_upd": 9},
    "medium": {"w": 300, "h": 148, "f_main": 48, "f_tot": 15, "f_days": 13, "f_upd": 11},
    "large":  {"w": 360, "h": 176, "f_main": 58, "f_tot": 17, "f_days": 15, "f_upd": 12},
}

if getattr(sys, "frozen", False):
    config_path = os.path.join(os.path.expanduser("~"), "Documents", "WE Widget")
    os.makedirs(config_path, exist_ok=True)
    assets_path = sys._MEIPASS
else:
    config_path = os.path.dirname(os.path.abspath(__file__))
    assets_path = config_path

CONFIG_FULL_PATH  = os.path.join(config_path, CONFIG_FILENAME)
COOKIES_FULL_PATH = os.path.join(config_path, COOKIES_FILENAME)

default_config = {
    "service_number": "",
    "password": "",
    "window_x": None,
    "window_y": None,
    "renewal_date": None,
    "total_quota": 0,
    "theme": "dark",
    "widget_size": "small",
    "alert_dismissed_cycle": "",
    "update_interval_minutes": 60,
}
config_data = default_config.copy()

def encode_pw(p): return base64.b64encode(p.encode()).decode()
def decode_pw(p):
    try: return base64.b64decode(p.encode()).decode()
    except: return p

def load_config():
    global config_data
    if not os.path.exists(CONFIG_FULL_PATH):
        try:
            with open(CONFIG_FULL_PATH, "w", encoding="utf-8") as f:
                json.dump(default_config, f, indent=4)
        except: pass
    else:
        try:
            with open(CONFIG_FULL_PATH, "r", encoding="utf-8") as f:
                config_data.update(json.load(f))
        except:
            config_data = default_config.copy()

def save_config():
    try:
        with open(CONFIG_FULL_PATH, "w", encoding="utf-8") as f:
            json.dump(config_data, f, indent=4)
    except: pass

def save_cookies(driver):
    try:
        cookies = driver.get_cookies()
        try: local_storage = driver.execute_script("return JSON.stringify(localStorage);")
        except: local_storage = None
        with open(COOKIES_FULL_PATH, "w", encoding="utf-8") as f:
            json.dump({"cookies": cookies, "localStorage": local_storage}, f, indent=2)
    except: pass

def load_cookies(driver):
    try:
        if not os.path.exists(COOKIES_FULL_PATH): return False
        with open(COOKIES_FULL_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not data: return False
        cookies = data if isinstance(data, list) else data.get("cookies", [])
        local_storage = None if isinstance(data, list) else data.get("localStorage")
        if not cookies: return False
        for c in cookies:
            c.pop("sameSite", None)
            try: driver.add_cookie(c)
            except:
                c.pop("expiry", None)
                try: driver.add_cookie(c)
                except: pass
        if local_storage:
            try:
                driver.execute_script(
                    "var d=arguments[0]; for(var k in d) localStorage.setItem(k,d[k]);",
                    json.loads(local_storage)
                )
            except: pass
        return True
    except: return False

def clear_cookies():
    try:
        if os.path.exists(COOKIES_FULL_PATH): os.remove(COOKIES_FULL_PATH)
    except: pass

load_config()

# ==========================================
# THEMES
# ==========================================
THEMES = {
    "dark": {
        "text_main":  "#FFFFFF",
        "text_total": "#B0B0B0",
        "text_days":  "#00E5FF",
        "text_warn":  "#FFEA00",
        "text_err":   "#FF3366",
        "bar_track":  "#1A1A1A",
        "bar_green":  "#00FF7F",
        "bar_yellow": "#FFEA00",
        "bar_red":    "#FF3366",
    },
    "light": {
        "text_main":  "#000000",
        "text_total": "#4A4A4A",
        "text_days":  "#0055CC",
        "text_warn":  "#D95A00",
        "text_err":   "#C00000",
        "bar_track":  "#E0E0E0",
        "bar_green":  "#008833",
        "bar_yellow": "#D95A00",
        "bar_red":    "#C00000",
    },
}

def T(): return THEMES[config_data.get("theme", "dark")]

# ==========================================
# CHROMEDRIVER
# ==========================================
def make_driver(images=False):
    opts = Options()
    opts.add_argument("--headless")
    opts.add_argument("--disable-web-security")
    opts.add_argument("--allow-running-insecure-content")
    opts.add_argument("--disable-features=IsolateOrigins,site-per-process")
    opts.add_argument("--no-first-run")
    opts.add_argument("--no-default-browser-check")
    opts.add_argument("--window-size=1280,800")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_experimental_option("excludeSwitches", ["enable-logging"])
    if not images:
        opts.add_argument("--blink-settings=imagesEnabled=false")
    opts.add_argument("--log-level=3")
    opts.add_argument("--silent")
    opts.page_load_strategy = "eager"
    try:
        driver = webdriver.Chrome(options=opts)
    except Exception as e1:
        try:
            import logging; logging.getLogger("WDM").setLevel(logging.ERROR)
            driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=opts)
        except Exception as e2:
            raise Exception(f"ChromeDriver Init Failed.\nNative: {e1}\nWDM: {e2}")
    try:
        driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument",
            {"source": "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});"})
    except: pass
    return driver

def get_captcha_image(driver):
    try:
        src = driver.find_element(By.XPATH, "//img[@alt='Captcha Image']").get_attribute("src")
        if src and "base64," in src:
            return Image.open(io.BytesIO(base64.b64decode(src.split("base64,", 1)[1])))
    except: pass
    return None

# ==========================================
# HELPERS
# ==========================================
def _shadow(parent, blur=6, dx=1, dy=1, alpha=180):
    fx = QGraphicsDropShadowEffect(parent)
    fx.setBlurRadius(blur)
    fx.setXOffset(dx)
    fx.setYOffset(dy)
    fx.setColor(QColor(0, 0, 0, alpha))
    return fx

def _pil_to_pixmap(pil_img):
    pil_img = pil_img.convert("RGBA")
    data    = pil_img.tobytes("raw", "RGBA")
    qimg    = QImage(data, pil_img.width, pil_img.height, QImage.Format_RGBA8888)
    return QPixmap.fromImage(qimg)

def _styled_label(text, color_hex, pt, bold=False, parent=None):
    lbl = QLabel(text, parent)
    f   = QFont("Segoe UI", pt, QFont.Bold if bold else QFont.Normal)
    lbl.setFont(f)
    lbl.setStyleSheet(f"color: {color_hex}; background: transparent;")
    lbl.setAttribute(Qt.WA_TranslucentBackground)
    return lbl

# ==========================================
# DIALOGS
# ==========================================
_DLG_STYLE = """
    QDialog { background: #1C1C1E; }
    QLabel  { color: #DDDDDD; background: transparent; }
    QLineEdit {
        background: #2C2C2E; color: #FFFFFF; border: 1px solid #3A3A3C;
        border-radius: 8px; padding: 6px 10px;
    }
    QLineEdit:focus { border: 1px solid #3498DB; }
    QPushButton {
        background: #3498DB; color: #FFFFFF; border: none;
        border-radius: 8px; padding: 8px 18px; font-weight: bold;
    }
    QPushButton:hover  { background: #2980B9; }
    QPushButton:pressed { background: #1F6FA5; }
    QComboBox {
        background: #2C2C2E; color: #FFFFFF; border: 1px solid #3A3A3C;
        border-radius: 8px; padding: 6px 10px;
    }
"""

class HelpDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("How it works")
        self.setStyleSheet(_DLG_STYLE)
        self.setFixedSize(360, 360)
        self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)

        lay = QVBoxLayout(self)
        lay.setSpacing(8)
        lay.setContentsMargins(20, 18, 20, 18)

        title = QLabel("How WE Widget Works")
        title.setFont(QFont("Segoe UI", 15, QFont.Bold))
        title.setStyleSheet("color: #3498DB; background: transparent;")
        lay.addWidget(title)

        ver = QLabel(f"Version: {APP_VERSION}")
        ver.setStyleSheet("color: #888888; background: transparent; font-size: 10pt;")
        lay.addWidget(ver)
        lay.addSpacing(6)

        for line in [
            "1. The widget runs silently in the background.",
            "2. It automatically updates based on your interval.",
            "3. If WE portal requires a CAPTCHA, you'll be notified.",
            "4. Right-click the system tray icon to solve CAPTCHA.",
            "5. Drag the widget anywhere to reposition it.",
        ]:
            lbl = QLabel(line)
            lbl.setWordWrap(True)
            lbl.setStyleSheet("color: #CCCCCC; background: transparent; font-size: 11pt;")
            lay.addWidget(lbl)

        lay.addSpacing(8)
        gh_lbl = QLabel("Check for updates or report issues on GitHub:")
        gh_lbl.setStyleSheet("color: #F1C40F; background: transparent; font-weight: bold;")
        lay.addWidget(gh_lbl)

        gh_btn = QPushButton("Open GitHub")
        gh_btn.setStyleSheet("background: #2C2C2E; color: #FFFFFF; border-radius: 8px; padding: 7px;")
        gh_btn.clicked.connect(
            lambda: webbrowser.open("https://github.com/ismailkatilo/we-quota-widget"))
        lay.addWidget(gh_btn)
        lay.addSpacing(4)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        lay.addWidget(close_btn, 0, Qt.AlignCenter)


class SetupDialog(QDialog):
    saved = Signal()

    def __init__(self, parent=None, first_setup=False):
        super().__init__(parent)
        self.first_setup = first_setup
        self.setWindowTitle("WE Widget – Settings")
        self.setStyleSheet(_DLG_STYLE)
        self.setFixedSize(340, 320)
        self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)

        icon_path = os.path.join(assets_path, "app_icon.ico")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        lay = QVBoxLayout(self)
        lay.setSpacing(10)
        lay.setContentsMargins(24, 20, 24, 20)

        title = QLabel("WE Quota Widget")
        title.setFont(QFont("Segoe UI", 16, QFont.Bold))
        title.setStyleSheet("color: #3498DB; background: transparent;")
        title.setAlignment(Qt.AlignCenter)
        lay.addWidget(title)

        self.e_num = QLineEdit()
        self.e_num.setPlaceholderText("Service Number")
        self.e_num.setFixedHeight(38)
        if config_data["service_number"]:
            self.e_num.setText(config_data["service_number"])
        lay.addWidget(self.e_num)

        self.e_pwd = QLineEdit()
        self.e_pwd.setPlaceholderText("Password")
        self.e_pwd.setEchoMode(QLineEdit.Password)
        self.e_pwd.setFixedHeight(38)
        if config_data["password"]:
            self.e_pwd.setText(decode_pw(config_data["password"]))
        lay.addWidget(self.e_pwd)

        interval_lbl = QLabel("Update Interval")
        interval_lbl.setFont(QFont("Segoe UI", 12, QFont.Bold))
        lay.addWidget(interval_lbl)

        self._interval_options = [
            ("Every 10 minutes", 10), ("Every 30 minutes", 30),
            ("Every 1 hour", 60),     ("Every 2 hours", 120),
            ("Every 4 hours", 240),   ("Every 6 hours", 360),
        ]
        self.combo = QComboBox()
        self.combo.setFixedHeight(38)
        current_min = config_data.get("update_interval_minutes", 60)
        for label, mins in self._interval_options:
            self.combo.addItem(label, mins)
        idx = next((i for i, (_, m) in enumerate(self._interval_options) if m == current_min), 2)
        self.combo.setCurrentIndex(idx)
        lay.addWidget(self.combo)

        self.err_lbl = QLabel("")
        self.err_lbl.setStyleSheet("color: #E74C3C; background: transparent; font-size: 10pt;")
        self.err_lbl.setAlignment(Qt.AlignCenter)
        lay.addWidget(self.err_lbl)

        save_btn = QPushButton("Save && Start")
        save_btn.setFixedHeight(40)
        save_btn.clicked.connect(self._save)
        lay.addWidget(save_btn)

    def show_error(self, msg):
        self.err_lbl.setText(msg)
        self.e_pwd.clear()

    def _save(self):
        num = self.e_num.text().strip()
        pwd = self.e_pwd.text().strip()
        if not num or not pwd:
            return
        config_data["service_number"] = num
        config_data["password"] = encode_pw(pwd)
        config_data["update_interval_minutes"] = self.combo.currentData()
        clear_cookies()
        save_config()
        self.saved.emit()
        self.accept()


class CaptchaDialog(QDialog):
    submitted = Signal(str)

    def __init__(self, captcha_image, parent=None, on_refresh=None):
        super().__init__(parent)
        self.on_refresh = on_refresh
        self.setWindowTitle("Verification Required")
        self.setStyleSheet(_DLG_STYLE)
        self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)

        has_img = captcha_image is not None
        self.setFixedSize(400, 295 if has_img else 210)

        icon_path = os.path.join(assets_path, "app_icon.ico")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        lay = QVBoxLayout(self)
        lay.setSpacing(10)
        lay.setContentsMargins(16, 16, 16, 16)

        title = QLabel("CAPTCHA Required")
        title.setFont(QFont("Segoe UI", 13, QFont.Bold))
        title.setStyleSheet("color: #F39C12; background: transparent;")
        lay.addWidget(title)

        img_row = QHBoxLayout()
        if has_img:
            pix = _pil_to_pixmap(captcha_image.resize((280, 80), Image.LANCZOS))
            img_lbl = QLabel()
            img_lbl.setPixmap(pix)
            img_row.addWidget(img_lbl)

        if on_refresh:
            ref_btn = QPushButton("Refresh")
            ref_btn.setFixedSize(80, 80)
            ref_btn.clicked.connect(self._do_refresh)
            img_row.addWidget(ref_btn)

        lay.addLayout(img_row)

        self.entry = QLineEdit()
        self.entry.setPlaceholderText("e.g. k6i WN")
        self.entry.setFixedHeight(42)
        self.entry.returnPressed.connect(self._submit)
        lay.addWidget(self.entry)

        submit_btn = QPushButton("Submit")
        submit_btn.setFixedHeight(40)
        submit_btn.clicked.connect(self._submit)
        lay.addWidget(submit_btn)

    def _submit(self):
        code = self.entry.text().strip()
        if code:
            self.submitted.emit(code)
            self.accept()

    def _do_refresh(self):
        self.reject()
        if self.on_refresh:
            self.on_refresh()


class AlertDialog(QDialog):
    def __init__(self, parent=None, on_ok=None):
        super().__init__(parent)
        self.on_ok = on_ok
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Dialog)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(300, 185)

        card = QWidget(self)
        card.setGeometry(5, 5, 290, 175)
        card.setStyleSheet("""
            QWidget { background: #2C2C2E; border-radius: 15px; }
            QLabel  { background: transparent; }
        """)

        lay = QVBoxLayout(card)
        lay.setContentsMargins(20, 20, 20, 20)
        lay.setSpacing(8)

        t = QLabel("Low Balance Warning")
        t.setFont(QFont("Segoe UI", 13, QFont.Bold))
        t.setStyleSheet("color: #F1C40F;")
        lay.addWidget(t, 0, Qt.AlignCenter)

        msg = QLabel("Less than 20% remaining.\nRecharge your WE account.")
        msg.setStyleSheet("color: #AAAAAA; font-size: 11pt;")
        msg.setAlignment(Qt.AlignCenter)
        lay.addWidget(msg)

        btn = QPushButton("OK, Got it")
        btn.setFixedSize(130, 36)
        btn.setStyleSheet("""
            QPushButton { background: #3498DB; color: white; border-radius: 8px; font-weight: bold; }
            QPushButton:hover { background: #2980B9; }
        """)
        btn.clicked.connect(self._ok)
        lay.addWidget(btn, 0, Qt.AlignCenter)

    def _ok(self):
        if self.on_ok: self.on_ok()
        self.accept()

# ==========================================
# PROGRESS BAR WIDGET
# ==========================================
class ProgressBar(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._value      = 0.0
        self._bar_color  = QColor("#00FF7F")
        self._track_color = QColor("#1A1A1A")
        self.setFixedHeight(8)
        self.setAttribute(Qt.WA_TranslucentBackground)

    def set_value(self, value, color_hex):
        self._value     = max(0.0, min(1.0, value))
        self._bar_color = QColor(color_hex)
        self.update()

    def paintEvent(self, event):
        p   = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r   = self.rect().adjusted(0, 0, -1, -1)
        rad = r.height() / 2.0
        p.setPen(Qt.NoPen)
        p.setBrush(self._track_color)
        p.drawRoundedRect(r, rad, rad)
        if self._value > 0.001:
            from PySide6.QtCore import QRectF
            pr = QRectF(r.x(), r.y(), r.width() * self._value, r.height())
            p.setBrush(self._bar_color)
            p.drawRoundedRect(pr, rad, rad)
        p.end()

# ==========================================
# SCRAPER SIGNALS  (cross-thread safe)
# ==========================================
class ScraperSignals(QObject):
    data_ready     = Signal(float, float, str)   # current, total, days
    status_update  = Signal(str, str)            # text, color_hex
    captcha_show   = Signal()
    captcha_hide   = Signal()
    wrong_password = Signal()
    rate_limited   = Signal()
    error_msg      = Signal(str)

# ==========================================
# MAIN WIDGET
# ==========================================
class QuotaWidget(QWidget):
    def __init__(self):
        super().__init__()

        # --- window flags ---
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_NoSystemBackground)

        self._is_ready    = False
        self._is_updating = False
        self._last_data   = None
        self._drag_pos    = None

        sz = SIZES[config_data.get("widget_size", "small")]
        self.resize(sz["w"], sz["h"])

        screen = QApplication.primaryScreen().availableGeometry()
        x = config_data.get("window_x")
        y = config_data.get("window_y")
        if x is None or y is None or x < 0 or y < 0 or x > screen.width()-50 or y > screen.height()-50:
            x = (screen.width()  - sz["w"]) // 2
            y = (screen.height() - sz["h"]) // 2
            config_data["window_x"] = x
            config_data["window_y"] = y
            save_config()
        self.move(x, y)

        # captcha state
        self._captcha_visible = False
        self._captcha_event   = None
        self._captcha_code    = None
        self._captcha_driver  = None

        # scraper signals
        self._signals = ScraperSignals()
        self._signals.data_ready.connect(self.update_ui_safe)
        self._signals.status_update.connect(self._on_status_update)
        self._signals.captcha_show.connect(self._show_captcha_btn)
        self._signals.captcha_hide.connect(self._hide_captcha_btn)
        self._signals.wrong_password.connect(self._prompt_wrong_password)
        self._signals.rate_limited.connect(
            lambda: self._on_status_update("Blocked: Retry in 1h", T()["text_err"]))
        self._signals.error_msg.connect(
            lambda msg: self._on_status_update(msg, T()["text_err"]))

        # update timer
        self._update_timer = QTimer(self)
        self._update_timer.setSingleShot(True)
        self._update_timer.timeout.connect(self.trigger_update)

        self._build_ui()
        self._setup_tray()

        # desktop watchdog
        self._watchdog = QTimer(self)
        self._watchdog.timeout.connect(self._desktop_watchdog)
        self._watchdog.start(300)

        self.show()
        QTimer.singleShot(150, self._apply_desktop_style)

        if not config_data["service_number"] or not config_data["password"]:
            QTimer.singleShot(300, lambda: self._open_setup(first=True))
        else:
            QTimer.singleShot(500, lambda: setattr(self, "_is_ready", True))
            QTimer.singleShot(600, self.trigger_update)

    # ------------------------------------------------------------------
    # UI BUILD
    # ------------------------------------------------------------------
    def _build_ui(self):
        t  = T()
        sz = SIZES[config_data.get("widget_size", "small")]

        # clear existing layout
        if self.layout():
            while self.layout().count():
                item = self.layout().takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
            QApplication.processEvents()

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 8, 10, 6)
        root.setSpacing(5)

        # top row: big number + GB/total
        top = QHBoxLayout()
        top.setSpacing(4)
        top.setContentsMargins(0, 0, 0, 0)

        self.lbl_current = _styled_label("...", t["text_main"], sz["f_main"], bold=True)
        self.lbl_current.setGraphicsEffect(_shadow(self))

        self.lbl_total = _styled_label("GB / --", t["text_total"], sz["f_tot"], bold=True)
        self.lbl_total.setAlignment(Qt.AlignBottom | Qt.AlignLeft)
        self.lbl_total.setGraphicsEffect(_shadow(self, blur=4, alpha=140))

        top.addWidget(self.lbl_current, 0, Qt.AlignBottom)
        top.addWidget(self.lbl_total,   0, Qt.AlignBottom)
        top.addStretch()
        root.addLayout(top)

        # progress bar
        self.progress = ProgressBar(self)
        root.addWidget(self.progress)

        # bottom row: days + last update
        bot = QHBoxLayout()
        bot.setSpacing(0)
        bot.setContentsMargins(0, 2, 0, 0)

        self.lbl_days = _styled_label("-- Days Remaining", t["text_days"], sz["f_days"], bold=True)
        self.lbl_days.setGraphicsEffect(_shadow(self, blur=5, alpha=170))

        self.lbl_update = _styled_label("", t["text_total"], sz["f_upd"])
        self.lbl_update.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.lbl_update.setGraphicsEffect(_shadow(self, blur=4, alpha=130))

        bot.addWidget(self.lbl_days)
        bot.addStretch()
        bot.addSpacing(8)
        bot.addWidget(self.lbl_update)
        root.addLayout(bot)

    def _rebuild_ui(self):
        t  = T()
        sz = SIZES[config_data.get("widget_size", "small")]

        # Update fonts and colors on existing labels
        self.lbl_current.setFont(QFont("Segoe UI", sz["f_main"], QFont.Bold))
        self.lbl_total.setFont(QFont("Segoe UI", sz["f_tot"],  QFont.Bold))
        self.lbl_days.setFont(QFont("Segoe UI",   sz["f_days"], QFont.Bold))
        self.lbl_update.setFont(QFont("Segoe UI", sz["f_upd"]))

        self.lbl_current.setStyleSheet(f"color: {t['text_main']}; background: transparent;")
        self.lbl_total.setStyleSheet(f"color: {t['text_total']}; background: transparent;")
        self.lbl_update.setStyleSheet(f"color: {t['text_total']}; background: transparent;")
        self.progress._track_color = QColor(t["bar_track"])
        self.progress.update()

        # Tell every label its size hint changed, then invalidate and
        # activate the layout before resizing — this ensures Qt uses the
        # new font metrics when it recalculates positions after the resize.
        for w in (self.lbl_current, self.lbl_total, self.lbl_days, self.lbl_update):
            w.updateGeometry()
        self.layout().invalidate()
        self.layout().activate()

        self.resize(sz["w"], sz["h"])

        if self._last_data:
            d = self._last_data
            self.update_ui_safe(d["current"], d["total"], d["days"])
        else:
            self.lbl_days.setStyleSheet(f"color: {t['text_days']}; background: transparent;")

    # ------------------------------------------------------------------
    # SYSTEM TRAY
    # ------------------------------------------------------------------
    def _setup_tray(self):
        icon_path = os.path.join(assets_path, "tray_icon.ico")
        icon = QIcon(icon_path) if os.path.exists(icon_path) else QIcon()

        self.tray = QSystemTrayIcon(icon, self)
        self.tray.setToolTip("WE Quota Widget")

        menu = QMenu()

        act_update = QAction("Update Now", self)
        act_update.triggered.connect(self.trigger_update)
        menu.addAction(act_update)
        menu.addSeparator()

        act_settings = QAction("Settings", self)
        act_settings.triggered.connect(lambda: self._open_setup())
        menu.addAction(act_settings)

        # Size submenu
        size_menu = menu.addMenu("Change Size")
        size_grp  = QActionGroup(size_menu)
        size_grp.setExclusive(True)
        for label, key in [("Small (Default)", "small"), ("Medium", "medium"), ("Large", "large")]:
            a = QAction(label, size_grp)
            a.setCheckable(True)
            a.setChecked(config_data.get("widget_size", "small") == key)
            a.triggered.connect(lambda _, k=key: self._set_size(k))
            size_menu.addAction(a)

        # Theme submenu
        theme_menu = menu.addMenu("Switch Theme")
        theme_grp  = QActionGroup(theme_menu)
        theme_grp.setExclusive(True)
        for label, key in [("Dark Mode", "dark"), ("Light Mode", "light")]:
            a = QAction(label, theme_grp)
            a.setCheckable(True)
            a.setChecked(config_data.get("theme", "dark") == key)
            a.triggered.connect(lambda _, k=key: self._set_theme(k))
            theme_menu.addAction(a)

        menu.addSeparator()

        self.act_captcha = QAction("Solve CAPTCHA", self)
        self.act_captcha.setEnabled(False)
        self.act_captcha.triggered.connect(self._open_captcha_window)
        menu.addAction(self.act_captcha)
        menu.addSeparator()

        act_clear = QAction("Clear Cache && Cookies", self)
        act_clear.triggered.connect(self._clear_cookies_action)
        menu.addAction(act_clear)

        act_help = QAction("Help / How it works", self)
        act_help.triggered.connect(lambda: HelpDialog(self).exec())
        menu.addAction(act_help)
        menu.addSeparator()

        act_exit = QAction("Exit", self)
        act_exit.triggered.connect(self._quit)
        menu.addAction(act_exit)

        self.tray.setContextMenu(menu)
        self.tray.show()

    # ------------------------------------------------------------------
    # WINDOWS DESKTOP EMBEDDING
    # ------------------------------------------------------------------
    def _apply_desktop_style(self):
        try:
            hwnd = int(self.winId())
            # Hide from taskbar / Alt+Tab
            ex = ctypes.windll.user32.GetWindowLongW(hwnd, -20)
            ctypes.windll.user32.SetWindowLongW(hwnd, -20, ex | 0x00000080)
            # Find WorkerW / Progman desktop host
            desktop = ctypes.windll.user32.FindWindowW("Progman", None)
            workerw = [0]
            WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_size_t, ctypes.c_size_t)
            def _cb(w, _):
                if ctypes.windll.user32.FindWindowExW(w, 0, "SHELLDLL_DefView", None):
                    workerw[0] = w
                return True
            ctypes.windll.user32.EnumWindows(WNDENUMPROC(_cb), 0)
            if workerw[0]:
                desktop = workerw[0]
            if desktop:
                fn = getattr(ctypes.windll.user32, "SetWindowLongPtrW",
                             ctypes.windll.user32.SetWindowLongW)
                fn(hwnd, -8, desktop)
        except Exception:
            pass

    def _desktop_watchdog(self):
        if self._is_ready and not self.isVisible():
            self.show()
            self.lower()

    def changeEvent(self, event):
        from PySide6.QtCore import QEvent
        if event.type() == QEvent.Type.WindowStateChange and self._is_ready:
            if self.isMinimized():
                self.showNormal()
                self.lower()
        super().changeEvent(event)

    # ------------------------------------------------------------------
    # DRAG
    # ------------------------------------------------------------------
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton and self._drag_pos is not None:
            self.move(event.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, event):
        self._drag_pos = None
        config_data["window_x"] = self.x()
        config_data["window_y"] = self.y()
        threading.Thread(target=save_config, daemon=True).start()

    # ------------------------------------------------------------------
    # TRAY ACTIONS
    # ------------------------------------------------------------------
    def _set_size(self, key):
        if config_data.get("widget_size") == key: return
        config_data["widget_size"] = key
        save_config()
        self._rebuild_ui()

    def _set_theme(self, key):
        if config_data.get("theme") == key: return
        config_data["theme"] = key
        save_config()
        self._rebuild_ui()

    def _open_setup(self, first=False):
        dlg = SetupDialog(self, first_setup=first)
        dlg.saved.connect(self._on_setup_done)
        dlg.exec()

    def _clear_cookies_action(self):
        clear_cookies()
        self._on_status_update("Cookies cleared!", T()["text_warn"])
        QTimer.singleShot(2000, lambda: self.trigger_update() if not self._is_updating else None)

    def _quit(self):
        self.tray.hide()
        QApplication.quit()

    # ------------------------------------------------------------------
    # CAPTCHA
    # ------------------------------------------------------------------
    def _show_captcha_btn(self):
        self._captcha_visible = True
        self.act_captcha.setEnabled(True)
        self._on_status_update("Click Tray Icon -> Solve CAPTCHA", T()["text_warn"])

    def _hide_captcha_btn(self):
        self._captcha_visible = False
        self.act_captcha.setEnabled(False)

    def _open_captcha_window(self):
        driver = self._captcha_driver
        if not driver or not self._captcha_event: return

        def _fetch():
            try: img = get_captcha_image(driver)
            except: img = None
            QTimer.singleShot(0, lambda: self._show_captcha_dialog(img, driver))

        threading.Thread(target=_fetch, daemon=True).start()

    def _show_captcha_dialog(self, img, driver):
        if not self._captcha_event: return

        def _on_refresh():
            def _do():
                try:
                    r = driver.find_element(
                        By.XPATH,
                        "//img[@src and contains(@style,'cursor: pointer') and not(@alt='Captcha Image')]")
                    driver.execute_script("arguments[0].click();", r)
                    time.sleep(1.5)
                except: pass
            threading.Thread(target=_do, daemon=True).start()
            QTimer.singleShot(1800, self._open_captcha_window)

        dlg = CaptchaDialog(img, parent=None, on_refresh=_on_refresh)
        dlg.setWindowFlags(dlg.windowFlags() | Qt.WindowStaysOnTopHint)
        screen = QApplication.primaryScreen().availableGeometry()
        dlg.move((screen.width() - dlg.width()) // 2, (screen.height() - dlg.height()) // 2)
        dlg.submitted.connect(self._on_captcha_submitted)
        dlg.exec()

    def _on_captcha_submitted(self, code):
        self._captcha_code = code
        if self._captcha_event:
            self._captcha_event.set()

    def _notify_and_solve_captcha(self, driver):
        if HAS_WINOTIFY:
            try:
                def _toast():
                    n = Notification(
                        app_id="WE Quota Widget",
                        title="WE Widget – CAPTCHA Required",
                        msg="Right-click the tray icon and choose 'Solve CAPTCHA'.",
                        duration="long")
                    n.set_audio(audio.Default, loop=False)
                    n.show()
                threading.Thread(target=_toast, daemon=True).start()
            except: pass

        for _ in range(5):
            done = threading.Event()
            self._captcha_driver = driver
            self._captcha_event  = done
            self._captcha_code   = None
            self._signals.captcha_show.emit()

            waited = 0
            while not done.wait(timeout=5):
                waited += 5
                if waited >= 1800:
                    self._signals.captcha_hide.emit()
                    return False
                try: driver.execute_script("return 1;")
                except:
                    self._signals.captcha_hide.emit()
                    return False

            self._signals.captcha_hide.emit()
            code = self._captcha_code
            if not code: return False

            try:
                inp = driver.find_element(
                    By.XPATH, "//img[@alt='Captcha Image']/following::input[1]")
                driver.execute_script("""
                    var el=arguments[0], v=arguments[1];
                    Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,'value')
                        .set.call(el,v);
                    el.dispatchEvent(new FocusEvent('focus',{bubbles:true}));
                    el.dispatchEvent(new InputEvent('input',{bubbles:true,data:v}));
                    el.dispatchEvent(new Event('change',{bubbles:true}));
                """, inp, code)
                time.sleep(0.5)
                btn = driver.find_element(By.XPATH, "//button[.//span[text()='Ok']]")
                for _ in range(20):
                    if not btn.get_attribute("disabled"): break
                    time.sleep(0.25)
                driver.execute_script("arguments[0].click();", btn)
                time.sleep(3)
                try:
                    driver.find_element(By.XPATH, "//img[@alt='Captcha Image']")
                    continue   # still showing captcha → retry
                except: return True
            except: return False
        return False

    # ------------------------------------------------------------------
    # UPDATE CYCLE
    # ------------------------------------------------------------------
    def _on_setup_done(self):
        screen = QApplication.primaryScreen().availableGeometry()
        sz = SIZES[config_data.get("widget_size", "small")]
        x  = (screen.width()  - sz["w"]) // 2
        y  = (screen.height() - sz["h"]) // 2
        self.move(x, y)
        config_data["window_x"] = x
        config_data["window_y"] = y
        save_config()
        self.show()
        self.raise_()
        QTimer.singleShot(200, self._apply_desktop_style)
        QTimer.singleShot(1200, lambda: setattr(self, "_is_ready", True))
        self.trigger_update()

    def _prompt_wrong_password(self):
        dlg = SetupDialog(self)
        dlg.saved.connect(self._on_setup_done)
        dlg.show_error("Invalid Password or Service Number.")
        dlg.exec()

    def trigger_update(self):
        if self._is_updating: return
        self._is_updating = True
        self._update_timer.stop()
        self._on_status_update("Updating...", T()["text_warn"])
        threading.Thread(target=self._run_scraper, daemon=True).start()

    def _run_scraper(self):
        driver  = None
        success = False
        try:
            driver = make_driver(images=True)
            wait   = WebDriverWait(driver, 15)
            driver.get("https://my.te.eg/echannel/#/login")

            cookies_loaded = load_cookies(driver)
            if cookies_loaded:
                driver.refresh()
                time.sleep(2)

            try:
                driver.find_element(By.XPATH, "//span[contains(@style,'font-size: 2.1875rem')]")
                already_in = True
            except: already_in = False

            if not already_in:
                driver.get("https://my.te.eg/echannel/#/login")
                try:
                    svc = wait.until(EC.visibility_of_element_located((By.ID, "login_loginid_input_01")))
                    svc.send_keys(config_data["service_number"] + Keys.TAB)
                    time.sleep(0.2)
                    driver.switch_to.active_element.send_keys("Internet" + Keys.ENTER)
                    driver.find_element(By.ID, "login_password_input_01").send_keys(
                        decode_pw(config_data["password"]) + Keys.ENTER)
                    time.sleep(2)

                    try:
                        body = driver.find_element(By.TAG_NAME, "body").text
                        if "maximum number of attempts" in body or "try again after" in body:
                            self._signals.rate_limited.emit()
                            raise Exception("RATE_LIMITED")
                        if any(w in body.lower() for w in ("invalid", "incorrect", "wrong")):
                            self._signals.wrong_password.emit()
                            raise Exception("WRONG_PASSWORD")
                    except Exception as chk:
                        if "RATE_LIMITED" in str(chk) or "WRONG_PASSWORD" in str(chk): raise
                except Exception: pass

                try:
                    driver.find_element(By.XPATH, "//img[@alt='Captcha Image']")
                    captcha_present = True
                except: captcha_present = False

                if captcha_present:
                    self._captcha_driver = driver
                    solved = self._notify_and_solve_captcha(driver)
                    driver = self._captcha_driver or driver
                    wait   = WebDriverWait(driver, 20)
                    if not solved:
                        clear_cookies()
                        raise Exception("CAPTCHA not solved")
                    time.sleep(3)
                    try:
                        wait.until(EC.visibility_of_element_located(
                            (By.XPATH, "//span[contains(@style,'font-size: 2.1875rem')]")))
                    except:
                        driver.get("https://my.te.eg/echannel/#/login")
                        wait.until(EC.visibility_of_element_located(
                            (By.ID, "login_loginid_input_01"))).send_keys(
                            config_data["service_number"] + Keys.TAB)
                        time.sleep(0.2)
                        driver.switch_to.active_element.send_keys("Internet" + Keys.ENTER)
                        driver.find_element(By.ID, "login_password_input_01").send_keys(
                            decode_pw(config_data["password"]) + Keys.ENTER)
                        time.sleep(3)
                save_cookies(driver)

            usage = wait.until(EC.visibility_of_element_located(
                (By.XPATH, "//span[contains(@style,'font-size: 2.1875rem')]")))
            current_quota = float(usage.text)

            total = 0.0
            try:
                elm = driver.find_element(By.XPATH, "//*[contains(text(),'GB)') or contains(text(),'GB )')]")
                m   = re.search(r"\((\d+)\s*GB\)", elm.text, re.IGNORECASE)
                if m: total = float(m.group(1))
            except: pass
            if total == 0 and config_data.get("total_quota"):
                total = float(config_data["total_quota"])

            days_val = "??"
            try:
                wait_slow = WebDriverWait(driver, 30)
                btn = wait_slow.until(EC.element_to_be_clickable(
                    (By.XPATH, "//span[contains(text(),'More Details')]")))
                driver.execute_script("arguments[0].click();", btn)
                time.sleep(2)
                d_elm = wait_slow.until(EC.visibility_of_element_located(
                    (By.XPATH, "//span[contains(@style,'0.8rem') and contains(text(),'Remaining Days')]")))
                m = re.search(r"(\d+)\s*Remaining Days", d_elm.text, re.IGNORECASE)
                if m:
                    days = int(m.group(1))
                    if days > 0:
                        days_val = str(days)
                    config_data["renewal_date"] = (
                        datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d")
            except:
                if config_data.get("renewal_date"):
                    try:
                        r    = datetime.strptime(config_data["renewal_date"], "%Y-%m-%d").date()
                        diff = (r - datetime.now().date()).days
                        if diff > 0: days_val = str(diff)
                    except: pass

            if total > 0: config_data["total_quota"] = total
            save_config()

            self._signals.data_ready.emit(current_quota, total, days_val)
            success = True

        except Exception as e:
            err = str(e)
            with open(os.path.join(config_path, "error_log.txt"), "a", encoding="utf-8") as f:
                f.write(f"\n--- {datetime.now()} ---\n{traceback.format_exc()}\n")
            if not any(k in err for k in ("RATE_LIMITED", "WRONG_PASSWORD", "CAPTCHA not solved")):
                self._signals.error_msg.emit("Err: check error_log.txt")
        finally:
            drv = self._captcha_driver or driver
            if drv:
                try: drv.quit()
                except: pass
            self._captcha_driver = None
            self._is_updating    = False
            mins = config_data.get("update_interval_minutes", 60)
            self._update_timer.start((mins * 60 * 1000) if success else 300_000)

    # ------------------------------------------------------------------
    # UI UPDATE
    # ------------------------------------------------------------------
    def _on_status_update(self, text, color_hex):
        try:
            self.lbl_days.setText(text)
            self.lbl_days.setStyleSheet(f"color: {color_hex}; background: transparent;")
        except: pass

    def update_ui_safe(self, current, total, days):
        self._last_data = {"current": current, "total": total, "days": days}
        t = T()
        try:
            self.lbl_current.setText(str(current))
            self.lbl_current.setStyleSheet(f"color: {t['text_main']}; background: transparent;")

            self.lbl_total.setText(f"GB / {int(total)}" if total else "GB / --")
            self.lbl_total.setStyleSheet(f"color: {t['text_total']}; background: transparent;")

            days_s = str(days)
            if days_s.lstrip("-").isdigit():
                self.lbl_days.setText(f"{days_s} Days Remaining")
                self.lbl_days.setStyleSheet(f"color: {t['text_days']}; background: transparent;")
            else:
                self.lbl_days.setText(days_s)
                self.lbl_days.setStyleSheet(f"color: {t['text_warn']}; background: transparent;")

            pct   = (current / total) if total > 0 else 0
            color = t["bar_green"] if pct > 0.5 else (t["bar_yellow"] if pct > 0.2 else t["bar_red"])
            self.progress.set_value(min(pct, 1.0), color)

            self.lbl_update.setText(f"Last update: {datetime.now().strftime('%I:%M %p')}")
            self.lbl_update.setStyleSheet(f"color: {t['text_total']}; background: transparent;")
        except: pass

        try:
            if total > 0 and (current / total) < 0.20 and current > 0:
                cycle     = config_data.get("renewal_date", "")
                dismissed = config_data.get("alert_dismissed_cycle", "")
                if cycle != dismissed:
                    def _mark_ok():
                        config_data["alert_dismissed_cycle"] = cycle
                        save_config()
                    AlertDialog(self, on_ok=_mark_ok).exec()
        except: pass


if __name__ == "__main__":
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    widget = QuotaWidget()
    sys.exit(app.exec())
