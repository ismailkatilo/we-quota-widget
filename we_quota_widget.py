import time
import threading
import re
import json
import os
import sys
import ctypes
import subprocess
import base64
import io
import customtkinter as ctk
from PIL import Image
from datetime import datetime, timedelta
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from webdriver_manager.chrome import ChromeDriverManager
try:
    from winotify import Notification, audio
    HAS_WINOTIFY = True
except ImportError:
    HAS_WINOTIFY = False

IS_WINDOWS = sys.platform.startswith("win")
IS_MAC = sys.platform == "darwin"

# ==========================================
# CONFIGURATION
# ==========================================
CONFIG_FILENAME  = "config.json"
COOKIES_FILENAME = "cookies.json"
UPDATE_INTERVAL  = 3600000

if getattr(sys, 'frozen', False):
    # EXE: save config in Documents/WE Widget — always writable
    docs = os.path.join(os.path.expanduser("~"), "Documents", "WE Widget")
    os.makedirs(docs, exist_ok=True)
    application_path = docs
else:
    application_path = os.path.dirname(os.path.abspath(__file__))

CONFIG_FULL_PATH  = os.path.join(application_path, CONFIG_FILENAME)
COOKIES_FULL_PATH = os.path.join(application_path, COOKIES_FILENAME)

default_config = {
    "service_number": "",
    "password": "",
    "window_x": None,
    "window_y": None,
    "renewal_date": None,
    "total_quota": 0,
    "theme": "dark",
    "alert_dismissed_cycle": ""
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
                data = json.load(f)
                config_data.update(data)
        except:
            config_data = default_config.copy()
            try:
                with open(CONFIG_FULL_PATH, "w", encoding="utf-8") as f:
                    json.dump(config_data, f, indent=4)
            except: pass

def save_config():
    try:
        with open(CONFIG_FULL_PATH, "w", encoding="utf-8") as f:
            json.dump(config_data, f, indent=4)
    except: pass

def save_cookies(driver):
    try:
        cookies = driver.get_cookies()
        with open(COOKIES_FULL_PATH, "w", encoding="utf-8") as f:
            json.dump(cookies, f, indent=2)
    except: pass

def load_cookies(driver):
    """Load saved cookies into driver. Returns True if cookies were loaded."""
    try:
        if not os.path.exists(COOKIES_FULL_PATH):
            return False
        with open(COOKIES_FULL_PATH, "r", encoding="utf-8") as f:
            cookies = json.load(f)
        if not cookies:
            return False
        for cookie in cookies:
            # Only remove sameSite — keep expiry so session lasts longer
            cookie.pop("sameSite", None)
            try:
                driver.add_cookie(cookie)
            except:
                # If fails with expiry, try without it
                cookie.pop("expiry", None)
                try: driver.add_cookie(cookie)
                except: pass
        return True
    except: return False

def clear_cookies():
    try:
        if os.path.exists(COOKIES_FULL_PATH):
            os.remove(COOKIES_FULL_PATH)
    except: pass

load_config()

# ==========================================
# THEMES
# ==========================================
THEMES = {
    "dark": {
        "text_main":   "#FFFFFF",
        "text_total":  "#777777",
        "text_days":   "#3498DB",
        "text_warn":   "#F39C12",
        "text_err":    "#E74C3C",
        "bar_track":   "#2D2D2D",
        "bar_green":   "#2CC985",
        "bar_yellow":  "#F1C40F",
        "bar_red":     "#E74C3C",
        "menu_bg":     "#1C1C1E",
        "menu_text":   "#FFFFFF",
        "menu_hover":  "#2C2C2E",
        "menu_sep":    "#3A3A3C",
        "menu_danger": "#E74C3C",
    },
    "light": {
        "text_main":   "#1A1A2E",
        "text_total":  "#6B7280",
        "text_days":   "#2563EB",
        "text_warn":   "#D97706",
        "text_err":    "#DC2626",
        "bar_track":   "#E5E7EB",
        "bar_green":   "#059669",
        "bar_yellow":  "#D97706",
        "bar_red":     "#DC2626",
        "menu_bg":     "#FFFFFF",
        "menu_text":   "#111111",
        "menu_hover":  "#F3F4F6",
        "menu_sep":    "#E5E7EB",
        "menu_danger": "#DC2626",
        "stroke_main": False,
        "stroke_days": False,
        "stroke_total": False,
    }
}

def T(): return THEMES[config_data.get("theme", "dark")]

def notify_user(title, message):
    if HAS_WINOTIFY:
        try:
            toast = Notification(
                app_id="WE Quota Widget",
                title=title,
                msg=message,
                duration="long",
            )
            toast.set_audio(audio.Default, loop=False)
            toast.show()
            return
        except Exception:
            pass
    if IS_MAC:
        try:
            def esc(text):
                return text.replace("\\", "\\\\").replace('"', '\\"')

            script = f'display notification "{esc(message)}" with title "{esc(title)}"'
            subprocess.Popen(["osascript", "-e", script])
        except Exception:
            pass

# ==========================================
# CHROMEDRIVER
# ==========================================
_driver_path = None

def get_chrome_service(force_fresh=False):
    global _driver_path
    if force_fresh or not _driver_path or not os.path.exists(_driver_path):
        _driver_path = ChromeDriverManager().install()
    svc = Service(_driver_path)
    return svc

def get_chrome_service_fresh():
    """Always download/verify latest compatible driver."""
    global _driver_path
    _driver_path = ChromeDriverManager().install()
    return Service(_driver_path)

def make_driver(images=False, _retry=False):
    opts = Options()
    opts.add_argument("--headless=old")
    opts.add_argument("--window-size=1280,800")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--disable-dev-shm-usage")
    if not images:
        opts.add_argument("--blink-settings=imagesEnabled=false")
    opts.add_argument("--log-level=3")
    opts.add_argument("--silent")
    opts.page_load_strategy = 'eager'
    try:
        driver = webdriver.Chrome(service=get_chrome_service(), options=opts)
    except Exception:
        if _retry:
            raise
        # Driver incompatible — force fresh download and retry once
        global _driver_path
        _driver_path = None
        return make_driver(images=images, _retry=True)
    try:
        driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {"source": """
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
        """})
    except: pass
    return driver

def get_captcha_image(driver):
    """Extract CAPTCHA image from base64 src — no network load."""
    try:
        img_elem = driver.find_element(By.XPATH, "//img[@alt='Captcha Image']")
        src = img_elem.get_attribute("src")
        if src and "base64," in src:
            b64_data = src.split("base64,", 1)[1]
            return Image.open(io.BytesIO(base64.b64decode(b64_data)))
    except Exception as ex:
        print(f"CAPTCHA image extraction failed: {ex}")
    return None

# ==========================================
# SETUP WINDOW
# ==========================================
class SetupWindow(ctk.CTkToplevel):
    def __init__(self, parent, on_save):
        super().__init__(parent)
        self.on_save = on_save
        self.title("WE Widget - Setup")
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry(f"340x300+{sw//2-170}+{sh//2-150}")
        self.resizable(False, False)
        self.attributes('-topmost', True)
        self.grab_set()
        self.configure(fg_color="#1C1C1E")

        ctk.CTkLabel(self, text="WE Quota Widget",
                     font=("Segoe UI", 17, "bold"),
                     text_color="#3498DB").pack(pady=(24, 4))
        ctk.CTkLabel(self, text="Enter your MyWE login credentials",
                     font=("Segoe UI", 11), text_color="#888888").pack(pady=(0, 18))

        self.e_num = ctk.CTkEntry(self, placeholder_text="Service Number",
                                   width=270, height=38, corner_radius=8,
                                   border_color="#3498DB", fg_color="#2C2C2E",
                                   text_color="#FFFFFF")
        self.e_num.pack(pady=5)
        if config_data["service_number"]:
            self.e_num.insert(0, config_data["service_number"])

        self.e_pwd = ctk.CTkEntry(self, placeholder_text="Password",
                                   width=270, height=38, corner_radius=8,
                                   show="*", border_color="#3498DB",
                                   fg_color="#2C2C2E", text_color="#FFFFFF")
        self.e_pwd.pack(pady=(5, 0))
        if config_data["password"]:
            self.e_pwd.insert(0, decode_pw(config_data["password"]))

        # Eye toggle button
        self._pwd_visible = False
        self.btn_eye = ctk.CTkButton(
            self, text="👁  Show Password", width=270, height=26,
            corner_radius=6, fg_color="transparent",
            hover_color="#2C2C2E", text_color="#666666",
            border_width=0, anchor="w",
            font=("Segoe UI", 10),
            command=self._toggle_pwd
        )
        self.btn_eye.pack(pady=(0, 4))

        self.lbl_err = ctk.CTkLabel(self, text="", font=("Segoe UI", 10),
                                     text_color="#E74C3C")
        self.lbl_err.pack(pady=(2, 0))

        ctk.CTkButton(self, text="Save & Start", width=270, height=40,
                      corner_radius=8, fg_color="#3498DB", hover_color="#2980B9",
                      font=("Segoe UI", 13, "bold"),
                      command=self._save).pack(pady=10)

    def _toggle_pwd(self):
        self._pwd_visible = not self._pwd_visible
        self.e_pwd.configure(show="" if self._pwd_visible else "*")
        self.btn_eye.configure(
            text="🙈  Hide Password" if self._pwd_visible else "👁  Show Password",
            text_color="#3498DB"   if self._pwd_visible else "#666666"
        )

    def _save(self):
        num = self.e_num.get().strip()
        pwd = self.e_pwd.get().strip()
        if not num or not pwd:
            self.lbl_err.configure(text="⚠  Both fields are required.")
            return
        config_data["service_number"] = num
        config_data["password"] = encode_pw(pwd)
        clear_cookies()
        save_config()
        self.destroy()
        self.on_save()

    def show_wrong_password(self):
        self.lbl_err.configure(text="⚠  Wrong password. Please try again.")
        self.e_pwd.delete(0, "end")
        self.e_pwd.focus()

# ==========================================
# CAPTCHA WINDOW
# ==========================================
class CaptchaWindow(ctk.CTkToplevel):
    def __init__(self, parent, captcha_image, on_submit, on_refresh=None):
        super().__init__(parent)
        self.on_submit  = on_submit
        self.on_refresh = on_refresh
        self.title("Verification Required")
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        has_img = captcha_image is not None
        win_h   = 310 if has_img else 220
        self.geometry(f"400x{win_h}+{sw//2-200}+{sh//2-(win_h//2)}")
        self.resizable(False, False)
        self.attributes('-topmost', True)
        # No grab_set — allow user to keep using other apps
        self.configure(fg_color="#1C1C1E")

        ctk.CTkLabel(self, text="CAPTCHA Required",
                     font=("Segoe UI", 14, "bold"),
                     text_color="#F39C12").pack(pady=(16, 10))

        # Image row: captcha image + refresh square button
        img_row = ctk.CTkFrame(self, fg_color="transparent")
        img_row.pack(padx=16, fill="x")

        IMG_H = 80  # fixed height for both image and refresh button

        if has_img:
            try:
                target_w, target_h = 280, IMG_H
                img_resized = captcha_image.resize((target_w, target_h), Image.LANCZOS)
                self._ctk_img = ctk.CTkImage(
                    light_image=img_resized,
                    dark_image=img_resized,
                    size=(target_w, target_h)
                )
                img_card = ctk.CTkFrame(img_row, fg_color="#2C2C2E", corner_radius=8,
                                         width=target_w, height=IMG_H)
                img_card.pack_propagate(False)
                img_card.pack(side="left")
                ctk.CTkLabel(img_card, image=self._ctk_img, text="").pack(
                    expand=True, fill="both")
            except Exception as ex:
                print(f"Image display error: {ex}")
                ctk.CTkLabel(img_row, text="(Image error)",
                             font=("Segoe UI", 10), text_color="#888").pack(side="left")
        else:
            ctk.CTkLabel(img_row, text="Could not load CAPTCHA image.",
                         font=("Segoe UI", 11), text_color="#AAAAAA").pack(side="left")

        # Refresh button — square, same height as image
        if on_refresh:
            refresh_btn = ctk.CTkButton(
                img_row, text="↻", width=IMG_H, height=IMG_H,
                fg_color="#2C2C2E", hover_color="#1A6FA8",
                corner_radius=8, font=("Segoe UI", 32, "bold"),
                text_color="#3498DB",
                command=self._do_refresh
            )
            refresh_btn.pack(side="left", padx=(10, 0))

        ctk.CTkLabel(self, text="Type the code shown above:",
                     font=("Segoe UI", 11), text_color="#AAAAAA").pack(pady=(14, 4))

        self.entry = ctk.CTkEntry(
            self, width=240, height=40, corner_radius=8,
            fg_color="#2C2C2E", text_color="white",
            border_color="#F39C12",
            font=("Segoe UI", 15),
            placeholder_text="e.g.  k6i WN"
        )
        self.entry.pack()
        # Don't force focus — user may be in another app
        self.entry.bind("<Return>", lambda e: self._submit())

        ctk.CTkButton(self, text="Submit", width=180, height=38,
                      fg_color="#2980B9", hover_color="#3498DB",
                      corner_radius=8, font=("Segoe UI", 13, "bold"),
                      command=self._submit).pack(pady=14)

    def _submit(self):
        code = self.entry.get().strip()
        if code:
            self.destroy()
            self.on_submit(code)

    def _do_refresh(self):
        self.destroy()
        if self.on_refresh:
            self.on_refresh()

# ==========================================
# ALERT WINDOW
# ==========================================
class AlertWindow(ctk.CTkToplevel):
    def __init__(self, parent, on_ok):
        super().__init__(parent)
        self.on_ok = on_ok
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry(f"300x185+{sw//2-150}+{sh//2-92}")
        self.overrideredirect(True)
        self.attributes('-topmost', True)
        self.configure(fg_color="#1C1C1E")
        card = ctk.CTkFrame(self, fg_color="#2C2C2E", corner_radius=15)
        card.pack(fill="both", expand=True, padx=5, pady=5)
        ctk.CTkLabel(card, text="Low Balance Warning",
                     font=("Segoe UI", 14, "bold"),
                     text_color="#F1C40F").pack(pady=(20, 6))
        ctk.CTkLabel(card, text="Less than 20 GB remaining.\nRecharge your WE account.",
                     font=("Segoe UI", 11), text_color="#AAAAAA",
                     justify="center").pack(pady=(0, 14))
        ctk.CTkButton(card, text="OK, Got it", width=120, height=34,
                      fg_color="#C0392B", hover_color="#E74C3C",
                      corner_radius=8, font=("Segoe UI", 12, "bold"),
                      command=self._ok).pack(pady=(0, 14))

    def _ok(self):
        self.on_ok()
        self.destroy()

# ==========================================
# CONTEXT MENU
# ==========================================
class ContextMenu(ctk.CTkToplevel):
    def __init__(self, parent, x, y, on_theme, on_settings, on_close, on_captcha=None):
        super().__init__(parent)
        self.overrideredirect(True)
        self.attributes('-topmost', True)
        t = T()
        self.configure(fg_color=t["menu_bg"])
        frame = ctk.CTkFrame(self, fg_color=t["menu_bg"], corner_radius=10,
                              border_width=1, border_color=t["menu_sep"])
        frame.pack(fill="both", expand=True)
        theme_label = "Light Mode" if config_data.get("theme","dark") == "dark" else "Dark Mode"

        def item(text, cmd, danger=False):
            ctk.CTkButton(
                frame, text=text, anchor="w",
                width=175, height=30, corner_radius=6,
                fg_color="transparent", hover_color=t["menu_hover"],
                text_color=t["menu_danger"] if danger else t["menu_text"],
                font=("Segoe UI", 12),
                command=lambda: (self.destroy(), cmd())
            ).pack(fill="x", padx=3, pady=1)

        def sep():
            ctk.CTkFrame(frame, height=1,
                         fg_color=t["menu_sep"]).pack(fill="x", padx=8, pady=2)

        item(theme_label, on_theme)
        item("Settings",  on_settings)
        if on_captcha:
            sep()
            item("🔒  Solve CAPTCHA", on_captcha, danger=False)
        sep()
        item("✕  Close",  on_close, danger=True)
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        h = 148 if on_captcha else 108
        self.geometry(f"182x{h}+{min(x, sw-188)}+{min(y, sh-h-5)}")
        self.after(100, self.focus_set)
        self.bind("<FocusOut>", lambda e: self.destroy())

# ==========================================
# MAIN WIDGET
# ==========================================
class QuotaWidget(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.is_updating   = False
        self._ctx_menu     = None
        self._update_job   = None
        self._last_data    = None
        self._drag_x       = None
        self._drag_y       = None
        self._has_dragged  = False

        w, h = 240, 130
        x = config_data.get("window_x") or (self.winfo_screenwidth() - w - 20)
        y = config_data.get("window_y") or 20
        self.geometry(f"{w}x{h}+{x}+{y}")
        self.overrideredirect(True)
        self._window_bg = "#000001" if IS_WINDOWS else T()["menu_bg"]
        self.configure(fg_color=self._window_bg)
        if IS_WINDOWS:
            try:
                self.attributes('-transparentcolor', "#000001", '-alpha', 1.0)
            except Exception:
                self.attributes('-alpha', 1.0)
        else:
            self.attributes('-alpha', 1.0)
        ctk.set_appearance_mode("Dark" if config_data.get("theme","dark") == "dark" else "Light")

        self._build_ui()
        self.after(100, self._apply_window_style)

        if not config_data["service_number"] or not config_data["password"]:
            self.after(300, lambda: SetupWindow(self, self._on_setup_done))
        else:
            self.start_auto_update()

    # ---- UI ----
    def _build_ui(self):
        for w in self.winfo_children():
            w.destroy()
        t = T()
        self.main_frame = ctk.CTkFrame(self, fg_color="transparent", corner_radius=0)
        self.main_frame.pack(fill="both", expand=True, padx=15, pady=10)
        self.data_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent", corner_radius=0)
        self.data_frame.pack(fill="x", pady=(0, 5))
        self.lbl_current = ctk.CTkLabel(
            self.data_frame, text="...",
            font=("Segoe UI", 36, "bold"),
            text_color=t["text_main"], height=35)
        self.lbl_current.pack(side="left", anchor="s")
        self.lbl_total = ctk.CTkLabel(
            self.data_frame, text="GB / --",
            font=("Segoe UI", 12, "bold"),
            text_color=t["text_total"], height=25)
        self.lbl_total.pack(side="left", anchor="s", padx=(5,0), pady=(0,4))
        self.progress = ctk.CTkProgressBar(
            self.main_frame, height=6, corner_radius=3,
            fg_color=t["bar_track"], progress_color=t["bar_green"])
        self.progress.set(0)
        self.progress.pack(fill="x")
        # Days + Last update on same row
        days_row = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        days_row.pack(fill="x", pady=(3,0))

        self.lbl_days = ctk.CTkLabel(
            days_row, text="-- Days Left",
            font=("Segoe UI", 10, "bold"),
            text_color=t["text_days"])
        self.lbl_days.pack(side="left", anchor="w")

        self.lbl_update = ctk.CTkLabel(
            days_row, text="",
            font=("Segoe UI", 8),
            text_color=t["text_total"])
        self.lbl_update.pack(side="right", anchor="e")

        self._captcha_btn_visible    = False
        self._pending_captcha_driver = None
        self._pending_captcha_done   = None
        self._pending_captcha_code   = None

        # Invisible overlay — covers entire widget area for reliable click/rclick
        # Overlay sits below labels but above window background
        # _bind_all will add right-click to it
        self._overlay = ctk.CTkFrame(
            self, fg_color="transparent", corner_radius=0
        )
        self._overlay.place(x=0, y=0, relwidth=1.0, relheight=1.0)
        self._overlay.lower()

        self._apply_stroke_shadows()
        self._bind_all()

    def _rebuild_ui(self):
        ctk.set_appearance_mode("Dark" if config_data.get("theme","dark") == "dark" else "Light")
        self._window_bg = "#000001" if IS_WINDOWS else T()["menu_bg"]
        self.configure(fg_color=self._window_bg)
        self._build_ui()   # _build_ui already creates lbl_hover + schedules midnight
        if self._last_data:
            d = self._last_data
            self.update_ui_safe(d["current"], d["total"], d["days"])

    def _prompt_wrong_password(self):
        """Show settings window with wrong password message."""
        win = SetupWindow(self, self._on_setup_done)
        self.after(300, lambda: (
            win.lbl_err.configure(
                text="⚠  Wrong password. Please try again.",
                text_color="#E74C3C"
            ),
            win.e_pwd.delete(0, "end")
        ))

    def _show_captcha_btn(self):
        """Update label to show CAPTCHA is needed."""
        self._captcha_btn_visible = True
        try:
            self.lbl_days.configure(
                text="⚠ Right-click → Solve CAPTCHA",
                text_color=T()["text_warn"]
            )
            self.lbl_update.configure(text="")
        except: pass

    def _hide_captcha_btn(self):
        """Restore normal label."""
        self._captcha_btn_visible = False

    def _open_captcha_window(self):
        """Must run in main thread — called via button click."""
        driver = self._pending_captcha_driver
        done   = self._pending_captcha_done

        if not done:
            return

        if not driver:
            # Show window without image
            self._show_captcha_dialog(None, None, done)
            return

        # Get image in background then show dialog
        def fetch_and_show():
            try:
                img = get_captcha_image(driver)
            except Exception as ex:
                img = None
            self.after(0, lambda: self._show_captcha_dialog(img, driver, done))

        threading.Thread(target=fetch_and_show, daemon=True).start()

    def _show_captcha_dialog(self, img, driver, done):
        """Show the CAPTCHA dialog in main thread."""
        if done is None:
            return

        def on_submit(code):
            self._pending_captcha_code = code
            done.set()

        def on_refresh():
            def do_refresh():
                try:
                    r = driver.find_element(By.XPATH,
                        "//img[@src and contains(@style,'cursor: pointer') "
                        "and not(@alt='Captcha Image')]")
                    driver.execute_script("arguments[0].click();", r)
                    time.sleep(1.5)
                except: pass
            threading.Thread(target=do_refresh, daemon=True).start()
            self.after(1800, self._open_captcha_window)

        CaptchaWindow(self, captcha_image=img,
                      on_submit=on_submit, on_refresh=on_refresh)

    def _schedule_days_retry(self, current_quota, total):
        """Retry fetching days only — without full scrape."""
        def retry():
            if not self.is_updating:
                self.trigger_update()
        self.after(120000, retry)   # retry in 2 minutes

    def _apply_stroke_shadows(self):
        """White shadow 1px behind for stroke effect — only for flagged labels."""
        import tkinter as _tk
        t  = T()
        bg = "#000001"

        for attr in ("_stroke_current","_stroke_days"):
            try: getattr(self, attr).destroy()
            except: pass

        if not t.get("stroke_main") and not t.get("stroke_days"):
            return

        def sh(parent, font, text, target):
            s = _tk.Label(parent, text=text, font=font,
                          fg="#FFFFFF", bg=bg, bd=0, highlightthickness=0)
            s.place(in_=target, x=1, y=1, anchor="nw")
            return s

        try:
            if t.get("stroke_main"):
                self._stroke_current = sh(
                    self.data_frame, ("Segoe UI",36,"bold"), "...", self.lbl_current)
            if t.get("stroke_days"):
                self._stroke_days = sh(
                    self.main_frame, ("Segoe UI",10,"bold"), "-- Days Left", self.lbl_days)
        except: pass

    def _bind_all(self):
        def collect(w, lst):
            lst.append(w)
            for c in w.winfo_children(): collect(c, lst)
        all_w = []
        collect(self, all_w)
        for w in all_w:

            try:
                w.bind("<ButtonPress-1>",  self._on_press)
                w.bind("<B1-Motion>",       self._on_drag)
                w.bind("<ButtonRelease-1>", self._on_release)
                w.bind("<Button-3>",        self._on_rclick)
            except: pass

    def _on_press(self, e):
        self._drag_x        = e.x_root - self.winfo_x()
        self._drag_y        = e.y_root - self.winfo_y()
        self._has_dragged   = False
        self._click_handled = False

    def _on_drag(self, e):
        self._has_dragged = True
        self.geometry(f"+{e.x_root-self._drag_x}+{e.y_root-self._drag_y}")

    def _on_release(self, e):
        if getattr(self, "_click_handled", True):
            return
        self._click_handled = True
        if self._has_dragged:
            config_data["window_x"] = self.winfo_x()
            config_data["window_y"] = self.winfo_y()
            threading.Thread(target=save_config, daemon=True).start()
        else:
            if not self.is_updating:
                self.trigger_update()

    def _on_rclick(self, e):
        if self._ctx_menu:
            try: self._ctx_menu.destroy()
            except: pass
        captcha_cb = self._open_captcha_window if self._captcha_btn_visible else None
        self._ctx_menu = ContextMenu(
            self, e.x_root, e.y_root,
            on_theme=self._toggle_theme,
            on_settings=lambda: SetupWindow(self, self._on_setup_done),
            on_close=self.destroy,
            on_captcha=captcha_cb)

    def _toggle_theme(self):
        config_data["theme"] = "light" if config_data.get("theme","dark") == "dark" else "dark"
        save_config()
        self._rebuild_ui()

    def _on_setup_done(self):
        self.start_auto_update()

    def _apply_window_style(self):
        if not IS_WINDOWS:
            return
        try:
            hwnd = ctypes.windll.user32.GetParent(self.winfo_id()) or self.winfo_id()
            s = ctypes.windll.user32.GetWindowLongW(hwnd, -20)
            ctypes.windll.user32.SetWindowLongW(hwnd, -20, (s & ~0x00040000) | 0x00000080)
            self.withdraw(); self.deiconify()
        except: pass

    # ---- Scraper ----
    def start_auto_update(self):
        self.trigger_update()

    def trigger_update(self):
        if self.is_updating: return
        self.is_updating = True
        self.lbl_days.configure(text="Updating...", text_color=T()["text_warn"])
        threading.Thread(target=self.run_scraper, daemon=True).start()

    def _notify_and_solve_captcha(self, driver):
        """Toast + red button. Keep driver alive. User solves when ready."""
        threading.Thread(
            target=lambda: notify_user(
                "WE Widget — Verification Needed",
                "Right-click on the widget and choose 'Solve CAPTCHA'."
            ),
            daemon=True,
        ).start()

        for attempt in range(5):
            done = threading.Event()

            # Store in instance — button reads from here
            self._pending_captcha_driver = driver
            self._pending_captcha_done   = done
            self._pending_captcha_code   = None

            self.after(0, self._show_captcha_btn)
            self.after(0, lambda: self.lbl_days.configure(
                text="⚠ CAPTCHA needed",
                text_color=T()["text_warn"]
            ))

            # Ping driver every 5s to keep alive — wait until done
            while not done.wait(timeout=5):
                try:
                    driver.execute_script("return 1;")
                except:
                    self.after(0, self._hide_captcha_btn)
                    self._pending_captcha_driver = None
                    self._pending_captcha_done   = None
                    return False
            self.after(0, self._hide_captcha_btn)
            code = self._pending_captcha_code
            self._pending_captcha_driver = None
            self._pending_captcha_done   = None

            if not code:
                return False

            # Submit
            try:
                inp = driver.find_element(By.XPATH,
                    "//img[@alt=\'Captcha Image\']/following::input[1]")
                driver.execute_script("""
                    var el=arguments[0], val=arguments[1];
                    var s=Object.getOwnPropertyDescriptor(
                        window.HTMLInputElement.prototype,'value').set;
                    s.call(el,val);
                    el.dispatchEvent(new FocusEvent('focus',{bubbles:true}));
                    el.dispatchEvent(new InputEvent('input',{bubbles:true,data:val}));
                    el.dispatchEvent(new Event('change',{bubbles:true}));
                """, inp, code)
                time.sleep(0.5)
                btn = driver.find_element(By.XPATH,
                    "//button[.//span[text()=\'Ok\']]")
                for _ in range(20):
                    if not btn.get_attribute("disabled"): break
                    time.sleep(0.25)
                driver.execute_script("arguments[0].click();", btn)
                time.sleep(3)
                try:
                    driver.find_element(By.XPATH, "//img[@alt=\'Captcha Image\']")
                    # Show button again
                    self._pending_captcha_driver = driver
                    continue
                except:
                    return True
            except Exception as ex:
                return False

        return False

    def _do_captcha_flow(self, driver):
        """
        1. Grab CAPTCHA image from live driver
        2. Show window to user — keep driver alive with pings
        3. User submits code → type it into the page and click Ok
        4. If driver dies during wait → mark for restart
        Returns True on success, False on failure.
        """
        for attempt in range(5):
            # Grab image while driver is alive
            img = get_captcha_image(driver)

            done       = threading.Event()
            code       = [None]
            do_refresh = [False]

            def on_code(c, _done=done, _code=code):
                _code[0] = c
                _done.set()

            def on_refresh(_done=done, _ref=do_refresh):
                _ref[0] = True
                _done.set()

            self.after(0, lambda i=img: CaptchaWindow(
                self, captcha_image=i,
                on_submit=on_code, on_refresh=on_refresh
            ))

            # Keep driver alive while user reads the CAPTCHA
            driver_alive = True
            while not done.wait(timeout=3):
                try:
                    driver.execute_script("return 1;")
                except:
                    driver_alive = False
                    break

            # Refresh requested
            if do_refresh[0]:
                if driver_alive:
                    try:
                        refresh_img = driver.find_element(By.XPATH,
                            "//img[@src and contains(@style,'cursor: pointer') "
                            "and not(@alt='Captcha Image')]"
                        )
                        driver.execute_script("arguments[0].click();", refresh_img)
                        time.sleep(1.5)
                    except Exception as ex:
                        print(f"Refresh error: {ex}")
                continue

            if not code[0]:
                return False

            # Submit — if driver died, we can't submit on this session
            if not driver_alive:
                return False

            try:
                inp = driver.find_element(By.XPATH,
                    "//img[@alt='Captcha Image']/following::input[1]"
                )
                driver.execute_script("""
                    var el=arguments[0], val=arguments[1];
                    var s=Object.getOwnPropertyDescriptor(
                        window.HTMLInputElement.prototype,'value').set;
                    s.call(el,val);
                    el.dispatchEvent(new FocusEvent('focus',{bubbles:true}));
                    el.dispatchEvent(new InputEvent('input',{bubbles:true,data:val}));
                    el.dispatchEvent(new Event('change',{bubbles:true}));
                """, inp, code[0])
                time.sleep(0.5)

                btn = driver.find_element(By.XPATH,
                    "//button[.//span[text()='Ok']]"
                )
                for _ in range(20):
                    if not btn.get_attribute("disabled"):
                        break
                    time.sleep(0.25)

                driver.execute_script("arguments[0].click();", btn)
                time.sleep(3)

                # Check result
                try:
                    driver.find_element(By.XPATH, "//img[@alt='Captcha Image']")
                    print("Wrong CAPTCHA code — retrying...")
                    continue
                except:
                    self._captcha_driver = driver
                    return True

            except Exception as ex:
                print(f"CAPTCHA submit error: {ex}")
                return False

        return False

    def run_scraper(self):
        driver  = None
        success = False

        try:
            # images=True needed for CAPTCHA — minor perf cost is acceptable
            driver = make_driver(images=True)
            wait   = WebDriverWait(driver, 15)
            driver.get("https://my.te.eg/echannel/#/login")
            cookies_loaded = load_cookies(driver)
            if cookies_loaded:
                driver.refresh()
                time.sleep(2)
            try:
                driver.find_element(By.XPATH,
                    "//span[contains(@style,'font-size: 2.1875rem')]")
                already_in = True
            except:
                already_in = False

            if not already_in:
                driver.get("https://my.te.eg/echannel/#/login")

                try:
                    svc_input = wait.until(EC.visibility_of_element_located(
                        (By.ID, "login_loginid_input_01")
                    ))
                    svc_input.send_keys(config_data["service_number"] + Keys.TAB)
                    time.sleep(0.2)
                    driver.switch_to.active_element.send_keys("Internet" + Keys.ENTER)
                    driver.find_element(By.ID, "login_password_input_01").send_keys(
                        decode_pw(config_data["password"]) + Keys.ENTER
                    )
                    time.sleep(2)

                    # Detect rate-limit or wrong password
                    try:
                        body = driver.find_element(By.TAG_NAME, "body").text
                        if "maximum number of attempts" in body or "try again after" in body:
                            self.after(0, lambda: self.lbl_days.configure(
                                text="Blocked — retry in 1h",
                                text_color=T()["text_err"]
                            ))
                            raise Exception("RATE_LIMITED")
                        # Wrong password = error message visible on page
                        if ("Invalid" in body or "incorrect" in body.lower()
                                or "wrong" in body.lower()
                                or "invalid password" in body.lower()
                                or "كلمة المرور" in body):
                            self.after(0, self._prompt_wrong_password)
                            raise Exception("WRONG_PASSWORD")
                    except Exception as _chk:
                        if "RATE_LIMITED" in str(_chk) or "WRONG_PASSWORD" in str(_chk):
                            raise

                except Exception as _login_ex:
                    raise

                # CAPTCHA check — restart with images=True if needed
                try:
                    driver.find_element(By.XPATH, "//img[@alt='Captcha Image']")
                    captcha_present = True
                except:
                    captcha_present = False

                if captcha_present:
                    print("CAPTCHA detected — notifying user...")
                    self._captcha_driver = driver
                    solved = self._notify_and_solve_captcha(driver)
                    driver = getattr(self, "_captcha_driver", driver)
                    wait   = WebDriverWait(driver, 20)
                    if not solved:
                        clear_cookies()
                        raise Exception("CAPTCHA not solved")
                    time.sleep(3)
                    try:
                        wait.until(EC.visibility_of_element_located(
                            (By.XPATH, "//span[contains(@style,'font-size: 2.1875rem')]")
                        ))
                    except:
                        driver.get("https://my.te.eg/echannel/#/login")
                        wait.until(EC.visibility_of_element_located(
                            (By.ID, "login_loginid_input_01")
                        )).send_keys(config_data["service_number"] + Keys.TAB)
                        time.sleep(0.2)
                        driver.switch_to.active_element.send_keys("Internet" + Keys.ENTER)
                        driver.find_element(By.ID, "login_password_input_01").send_keys(
                            decode_pw(config_data["password"]) + Keys.ENTER
                        )
                        time.sleep(3)

                save_cookies(driver)

            # ── Remaining quota ───────────────────────────────────────────────
            usage_elem = wait.until(EC.visibility_of_element_located(
                (By.XPATH, "//span[contains(@style, 'font-size: 2.1875rem')]")
            ))
            current_quota = float(usage_elem.text)

            # ── Total from plan name — always fresh ───────────────────────────
            total = 0.0
            try:
                plan_elm = driver.find_element(By.XPATH,
                    "//*[contains(text(),'GB)') or contains(text(),'GB )')]")
                m = re.search(r"\((\d+)\s*GB\)", plan_elm.text, re.IGNORECASE)
                if m: total = float(m.group(1))
            except: pass
            if total == 0 and config_data.get("total_quota"):
                total = float(config_data["total_quota"])

            # ── More Details → Remaining Days ─────────────────────────────────
            days_val = "??"
            try:
                # Wait longer for slow connections
                wait_slow = WebDriverWait(driver, 30)
                more_btn = wait_slow.until(EC.element_to_be_clickable(
                    (By.XPATH, "//span[contains(text(),'More Details')]")))
                driver.execute_script("arguments[0].click();", more_btn)
                time.sleep(2)  # extra wait for page to load on slow connections
                d_elm = wait_slow.until(EC.visibility_of_element_located(
                    (By.XPATH,
                     "//span[contains(@style,'0.8rem') and contains(text(),'Remaining Days')]")))
                d_match = re.search(r"(\d+)\s*Remaining Days", d_elm.text, re.IGNORECASE)
                if d_match:
                    days     = int(d_match.group(1))
                    if days > 0:
                        days_val = str(days)
                    config_data["renewal_date"] = (
                        datetime.now() + timedelta(days=days)
                    ).strftime("%Y-%m-%d")
            except Exception as ex:
                print(f"More Details error: {ex}")
                # Only use cached date if it's in the future AND not today (avoid 0)
                if config_data.get("renewal_date"):
                    try:
                        r    = datetime.strptime(config_data["renewal_date"], "%Y-%m-%d").date()
                        diff = (r - datetime.now().date()).days
                        if diff > 0:   # strictly greater — never show 0
                            days_val = str(diff)
                        # if diff == 0 or negative, keep days_val = "??" 
                        # and retry will fix it next update
                    except: pass

            if total > 0: config_data["total_quota"] = total
            save_config()

            self.after(0, lambda: self.update_ui_safe(current_quota, total, days_val))
            success = True
            # always schedule next hourly update regardless of days_val
            pass

        except Exception as e:
            print(f"Update failed: {e}")
        finally:
            # Always quit the driver that was active at the end
            active_driver = getattr(self, "_captcha_driver", None) or driver
            if active_driver:
                try: active_driver.quit()
                except: pass
            self._captcha_driver = None
            self.is_updating = False
            # Cancel any stale job before scheduling new one
            # Always cancel ALL pending jobs before scheduling next
            if self._update_job:
                try: self.after_cancel(self._update_job)
                except: pass
                self._update_job = None
            if success:
                # Success: wait exactly 1 hour
                self._update_job = self.after(UPDATE_INTERVAL, self.start_auto_update)
            else:
                # Failure: reset driver cache then retry in 5 minutes
                global _driver_path
                _driver_path = None
                self._update_job = self.after(300000, self.trigger_update)

    # ---- UI Update ----
    def update_ui_safe(self, current, total, days):
        self._last_data = {"current": current, "total": total, "days": days}
        t = T()
        try:
            txt = str(current)
            self.lbl_current.configure(text=txt)
            if hasattr(self, "_stroke_current"):
                self._stroke_current.configure(text=txt)
        except: pass
        try:
            total_txt = f"GB / {int(total)}" if total else "GB / --"
            self.lbl_total.configure(text=total_txt)
            if hasattr(self, "_stroke_total"):
                self._stroke_total.configure(text=total_txt)
        except: pass
        try:
            days_s = str(days)
            if days_s.lstrip('-').isdigit():
                days_txt = f"{days_s} Days Left"
                self.lbl_days.configure(text=days_txt, text_color=t["text_days"])
            else:
                days_txt = days_s
                self.lbl_days.configure(text=days_txt, text_color=t["text_warn"])
            if hasattr(self, "_stroke_days"):
                self._stroke_days.configure(text=days_txt)
        except: pass
        try:
            pct = (current / total) if total > 0 else 0
            self.progress.set(min(pct, 1.0))
            color = t["bar_green"] if pct > 0.5 else (t["bar_yellow"] if pct > 0.2 else t["bar_red"])
            self.progress.configure(progress_color=color)
        except: pass

        # Last update time
        try:
            now_str = datetime.now().strftime("%I:%M %p")
            self.lbl_update.configure(text=f"Last update  {now_str}")
        except: pass

        try:
            if 0 < current <= 20:
                cycle     = config_data.get("renewal_date", "")
                dismissed = config_data.get("alert_dismissed_cycle", "")
                if cycle != dismissed:
                    def mark_ok():
                        config_data["alert_dismissed_cycle"] = cycle
                        save_config()
                    AlertWindow(self, on_ok=mark_ok)
        except: pass

# ==========================================
# ENTRY POINT
# ==========================================
if __name__ == "__main__":
    app = QuotaWidget()
    app.mainloop()
