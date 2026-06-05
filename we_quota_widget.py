import time
import threading
import re
import json
import os
import sys
import ctypes
import base64
import io
import queue
import traceback
import webbrowser
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
from webdriver_manager.chrome import ChromeDriverManager
import pystray
from pystray import MenuItem as item

try:
    from winotify import Notification, audio
    HAS_WINOTIFY = True
except ImportError:
    HAS_WINOTIFY = False

# ==========================================
# CONFIGURATION & PATHS
# ==========================================
APP_VERSION = "0.9.7-beta.3"
CONFIG_FILENAME  = "config.json"
COOKIES_FILENAME = "cookies.json"

SIZES = {
    "small":  {"w": 240, "h": 130, "f_main": 36, "f_tot": 12, "f_days": 10, "f_upd": 8},
    "medium": {"w": 300, "h": 160, "f_main": 46, "f_tot": 14, "f_days": 12, "f_upd": 10},
    "large":  {"w": 360, "h": 190, "f_main": 56, "f_tot": 16, "f_days": 14, "f_upd": 11}
}

if getattr(sys, 'frozen', False):
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
    "update_interval_minutes": 60
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
        try:
            local_storage = driver.execute_script("return JSON.stringify(localStorage);")
        except:
            local_storage = None
        data = {"cookies": cookies, "localStorage": local_storage}
        with open(COOKIES_FULL_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except: pass

def load_cookies(driver):
    try:
        if not os.path.exists(COOKIES_FULL_PATH): return False
        with open(COOKIES_FULL_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not data: return False

        if isinstance(data, list):
            cookies = data
            local_storage = None
        else:
            cookies = data.get("cookies", [])
            local_storage = data.get("localStorage")

        if not cookies: return False

        for cookie in cookies:
            cookie.pop("sameSite", None)
            try: driver.add_cookie(cookie)
            except:
                cookie.pop("expiry", None)
                try: driver.add_cookie(cookie)
                except: pass

        if local_storage:
            try:
                driver.execute_script(f"""
                    var data = {local_storage};
                    for (var key in data) {{
                        localStorage.setItem(key, data[key]);
                    }}
                """)
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
        "text_total":  "#B0B0B0",
        "text_days":   "#00E5FF", 
        "text_warn":   "#FFEA00", 
        "text_err":    "#FF3366", 
        "bar_track":   "#1A1A1A",
        "bar_green":   "#00FF7F", 
        "bar_yellow":  "#FFEA00",
        "bar_red":     "#FF3366",
    },
    "light": {
        "text_main":   "#000000",
        "text_total":  "#4A4A4A",
        "text_days":   "#0055CC", 
        "text_warn":   "#D95A00", 
        "text_err":    "#C00000", 
        "bar_track":   "#E0E0E0",
        "bar_green":   "#008833", 
        "bar_yellow":  "#D95A00",
        "bar_red":     "#C00000",
    }
}

def T(): return THEMES[config_data.get("theme", "dark")]

# ==========================================
# CHROMEDRIVER 
# ==========================================
def make_driver(images=False):
    opts = Options()
    opts.add_argument("--headless=new") 
    opts.add_argument("--disable-web-security")
    opts.add_argument("--allow-running-insecure-content")
    opts.add_argument("--disable-features=IsolateOrigins,site-per-process")
    opts.add_argument("--no-first-run")
    opts.add_argument("--no-default-browser-check")
    opts.add_argument("--window-size=1280,800")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-software-rasterizer")
    opts.add_argument("--disable-extensions")
    opts.add_experimental_option("excludeSwitches", ["enable-logging"])
    opts.set_capability("unhandledPromptBehavior", "accept")
    
    if not images:
        opts.add_argument("--blink-settings=imagesEnabled=false")
    opts.add_argument("--log-level=3")
    opts.add_argument("--silent")
    opts.page_load_strategy = 'eager'

    driver = None
    try:
        driver = webdriver.Chrome(options=opts)
    except Exception as e1:
        try:
            import logging
            logging.getLogger('WDM').setLevel(logging.ERROR)
            svc = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=svc, options=opts)
        except Exception as e2:
            raise Exception(f"ChromeDriver Init Failed.\nNative Err: {e1}\nWDM Err: {e2}")

    try:
        driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {"source": """
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            window.alert = function(msg) { console.log('Suppressed Alert: ' + msg); };
            window.confirm = function(msg) { return true; };
        """})
    except: pass
    return driver

def get_captcha_image(driver):
    try:
        img_elem = driver.find_element(By.XPATH, "//img[@alt='Captcha Image']")
        src = img_elem.get_attribute("src")
        if src and "base64," in src:
            b64_data = src.split("base64,", 1)[1]
            return Image.open(io.BytesIO(base64.b64decode(b64_data)))
    except: pass
    return None

# ==========================================
# WINDOWS (Setup, Captcha, Alert, Help)
# ==========================================
class HelpWindow(ctk.CTkToplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("How it works")
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry(f"360x370+{sw//2-180}+{sh//2-185}")
        self.resizable(False, False)
        self.attributes('-topmost', True)
        self.configure(fg_color="#1C1C1E")

        ctk.CTkLabel(self, text="How WE Widget Works", font=("Segoe UI", 16, "bold"), text_color="#3498DB").pack(pady=(15, 2))
        ctk.CTkLabel(self, text=f"Version: {APP_VERSION}", font=("Segoe UI", 10), text_color="#888888").pack(pady=(0, 10))
        
        info_text = (
            "1. The widget runs silently in the background.\n"
            "2. It automatically updates based on your interval.\n"
            "3. If WE portal requires a CAPTCHA, you'll be notified.\n"
            "4. Right-click the system tray icon to solve CAPTCHA.\n"
            "5. Drag the widget (click the text) anytime to move it.\n"
        )
        
        ctk.CTkLabel(self, text=info_text, font=("Segoe UI", 12), text_color="#DDDDDD", justify="left").pack(padx=20, pady=5, anchor="w")

        ctk.CTkLabel(self, text="Check for updates or report issues on GitHub:", font=("Segoe UI", 11, "bold"), text_color="#F1C40F").pack(pady=(10, 2))
        ctk.CTkButton(self, text="Open GitHub", fg_color="#2C2C2E", hover_color="#3498DB", text_color="#FFFFFF", font=("Segoe UI", 12, "bold"),
                      command=lambda: webbrowser.open("https://github.com/ismailkatilo/we-quota-widget")).pack(pady=(0, 15))

        ctk.CTkButton(self, text="Close", width=120, command=self.destroy).pack(pady=5)

class SetupWindow(ctk.CTkToplevel):
    def __init__(self, parent, on_save, first_setup=False):
        super().__init__(parent)
        self.on_save     = on_save
        self.first_setup = first_setup
        self.title("WE Widget - Settings")
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        
        h = 350
        self.geometry(f"340x{h}+{sw//2-170}+{sh//2-h//2}")
        self.resizable(False, False)
        self.attributes('-topmost', True)
        self.configure(fg_color="#1C1C1E")

        app_icon_path = os.path.join(assets_path, "app_icon.ico")
        if os.path.exists(app_icon_path):
            try: self.iconbitmap(app_icon_path)
            except: pass

        ctk.CTkLabel(self, text="WE Quota Widget", font=("Segoe UI", 17, "bold"), text_color="#3498DB").pack(pady=(20, 15))
        
        self.e_num = ctk.CTkEntry(self, placeholder_text="Service Number", width=270, height=36, corner_radius=8)
        self.e_num.pack(pady=(0, 15))
        if config_data["service_number"]: self.e_num.insert(0, config_data["service_number"])

        self.e_pwd = ctk.CTkEntry(self, placeholder_text="Password", width=270, height=36, corner_radius=8, show="*")
        self.e_pwd.pack(pady=(0, 15))
        if config_data["password"]: self.e_pwd.insert(0, decode_pw(config_data["password"]))

        if first_setup:
            self._pwd_visible = False
            self.btn_eye = ctk.CTkButton(self.e_pwd, text="👁", width=30, height=26, fg_color="transparent", 
                                         hover_color="#2C2C2E", text_color="#888888", font=("Segoe UI", 14), 
                                         command=self._toggle_pwd)
            self.btn_eye.place(relx=1.0, rely=0.5, anchor="e", x=-5)

        ctk.CTkLabel(self, text="Update Interval", font=("Segoe UI", 13, "bold"), text_color="#DDDDDD").pack(pady=(0, 2))
        ctk.CTkLabel(self, text="Set how often the widget checks for new data.", font=("Segoe UI", 10), text_color="#888888").pack(pady=(0, 10))

        self._interval_options = [("Every 10 minutes", 10), ("Every 30 minutes", 30), ("Every 1 hour", 60), ("Every 2 hours", 120), ("Every 4 hours", 240), ("Every 6 hours", 360)]
        current_min = config_data.get("update_interval_minutes", 60)
        cur_label   = next((o[0] for o in self._interval_options if o[1] == current_min), "Every 1 hour")
        self._interval_menu = ctk.CTkOptionMenu(self, values=[o[0] for o in self._interval_options], width=270, height=36)
        self._interval_menu.set(cur_label)
        self._interval_menu.pack(pady=(0, 15))

        self.lbl_err = ctk.CTkLabel(self, text="", text_color="#E74C3C", font=("Segoe UI", 11))
        self.lbl_err.pack()
        
        ctk.CTkButton(self, text="Save & Start", width=270, height=38, font=("Segoe UI", 13, "bold"), command=self._save).pack(pady=(0, 10))

    def _toggle_pwd(self):
        if not hasattr(self, '_pwd_visible'): return
        self._pwd_visible = not self._pwd_visible
        self.e_pwd.configure(show="" if self._pwd_visible else "*")
        self.btn_eye.configure(text_color="#3498DB" if self._pwd_visible else "#888888")

    def _save(self):
        num = self.e_num.get().strip()
        pwd = self.e_pwd.get().strip()
        if not num or not pwd: return
        config_data["service_number"] = num
        config_data["password"] = encode_pw(pwd)
        selected = self._interval_menu.get()
        minutes  = next((o[1] for o in self._interval_options if o[0] == selected), 60)
        config_data["update_interval_minutes"] = minutes
        clear_cookies()
        save_config()
        self.destroy()
        self.on_save()

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
        self.configure(fg_color="#1C1C1E")

        app_icon_path = os.path.join(assets_path, "app_icon.ico")
        if os.path.exists(app_icon_path):
            try: self.iconbitmap(app_icon_path)
            except: pass

        ctk.CTkLabel(self, text="CAPTCHA Required", font=("Segoe UI", 14, "bold"), text_color="#F39C12").pack(pady=(16, 10))
        img_row = ctk.CTkFrame(self, fg_color="transparent")
        img_row.pack(padx=16, fill="x")

        if has_img:
            try:
                img_resized = captcha_image.resize((280, 80), Image.LANCZOS)
                self._ctk_img = ctk.CTkImage(light_image=img_resized, dark_image=img_resized, size=(280, 80))
                ctk.CTkLabel(img_row, image=self._ctk_img, text="").pack(side="left")
            except: pass

        if on_refresh:
            ctk.CTkButton(img_row, text="Refresh", width=80, height=80, command=self._do_refresh).pack(side="left", padx=(10, 0))

        self.entry = ctk.CTkEntry(self, width=240, height=40, placeholder_text="e.g. k6i WN")
        self.entry.pack(pady=10)
        self.entry.bind("<Return>", lambda e: self._submit())
        ctk.CTkButton(self, text="Submit", width=180, height=38, command=self._submit).pack(pady=10)

    def _submit(self):
        code = self.entry.get().strip()
        if code:
            self.destroy()
            self.on_submit(code)

    def _do_refresh(self):
        self.destroy()
        if self.on_refresh: self.on_refresh()

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
        ctk.CTkLabel(card, text="Low Balance Warning", font=("Segoe UI", 14, "bold"), text_color="#F1C40F").pack(pady=(20, 6))
        ctk.CTkLabel(card, text="Less than 20% remaining.\nRecharge your WE account.", font=("Segoe UI", 11), text_color="#AAAAAA").pack()
        ctk.CTkButton(card, text="OK, Got it", width=120, height=34, command=self._ok).pack(pady=(14, 14))

    def _ok(self):
        self.on_ok()
        self.destroy()


# ==========================================
# MAIN WIDGET
# ==========================================
class QuotaWidget(ctk.CTk):
    def __init__(self):
        super().__init__()
        
        self.cmd_queue = queue.Queue()
        self._is_ready = False
        
        self.is_updating   = False
        self._update_job   = None
        self._last_data    = None

        sz = SIZES.get(config_data.get("widget_size", "small"), SIZES["small"])
        self.w = sz["w"]
        self.h = sz["h"]
        
        x = config_data.get("window_x")
        y = config_data.get("window_y")
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        
        if x is None or y is None:
            x = (sw // 2) - (self.w // 2)
            y = (sh // 2) - (self.h // 2)
            config_data["window_x"] = x
            config_data["window_y"] = y
            save_config()

        self.geometry(f"{self.w}x{self.h}+{x}+{y}")
        self.overrideredirect(True)
        self.configure(fg_color="#000001") 
        self.attributes('-transparentcolor', "#000001", '-alpha', 1.0)
        ctk.set_appearance_mode("Dark" if config_data.get("theme","dark") == "dark" else "Light")

        app_icon_path = os.path.join(assets_path, "app_icon.ico")
        if os.path.exists(app_icon_path):
            try: self.iconbitmap(app_icon_path)
            except: pass

        self._drag_x = 0
        self._drag_y = 0

        self._build_ui()
        self._apply_desktop_style()

        self._captcha_btn_visible    = False
        self._pending_captcha_driver = None
        self._pending_captcha_done   = None
        self._pending_captcha_code   = None
        self.tray_icon = None
        self.setup_system_tray()

        self.bind("<Unmap>", self._anti_hide)
        self._desktop_watchdog()

        self._process_queue()

        if not config_data["service_number"] or not config_data["password"]:
            self.after(300, lambda: SetupWindow(self, self._on_setup_done, first_setup=True))
        else:
            self.after(500, lambda: setattr(self, '_is_ready', True))
            self.start_auto_update()

    def _anti_hide(self, event):
        if getattr(self, '_is_ready', False) and event.widget == self:
            self.deiconify()
            self.lower()

    def _desktop_watchdog(self):
        if getattr(self, '_is_ready', False):
            if not self.winfo_viewable():
                self.deiconify()
                self.lower()
        self.after(300, self._desktop_watchdog)

    def _process_queue(self):
        try:
            while True:
                cmd = self.cmd_queue.get_nowait()
                cmd()
        except queue.Empty:
            pass
        self.after(100, self._process_queue)

    def setup_system_tray(self):
        try:
            tray_icon_path = os.path.join(assets_path, "tray_icon.ico")
            if os.path.exists(tray_icon_path):
                tray_img = Image.open(tray_icon_path)
            else:
                tray_img = Image.new('RGB', (64, 64), color=(52, 152, 219))
        except:
            tray_img = Image.new('RGB', (64, 64), color=(52, 152, 219))

        def _make_size_cb(size_str):
            return lambda icon, itm: self.cmd_queue.put(lambda: self._set_size(size_str))

        def _is_size_checked(size_str):
            return lambda itm: config_data.get("widget_size", "small") == size_str

        size_menu = pystray.Menu(
            item('Small (Default)', _make_size_cb('small'), checked=_is_size_checked('small'), radio=True),
            item('Medium', _make_size_cb('medium'), checked=_is_size_checked('medium'), radio=True),
            item('Large', _make_size_cb('large'), checked=_is_size_checked('large'), radio=True)
        )

        def _make_theme_cb(theme_str):
            return lambda icon, itm: self.cmd_queue.put(lambda: self._set_theme(theme_str))

        def _is_theme_checked(theme_str):
            return lambda itm: config_data.get("theme", "dark") == theme_str

        theme_menu = pystray.Menu(
            item('Dark Mode', _make_theme_cb('dark'), checked=_is_theme_checked('dark'), radio=True),
            item('Light Mode', _make_theme_cb('light'), checked=_is_theme_checked('light'), radio=True)
        )

        menu = pystray.Menu(
            item('Update Now', self._tray_update_now),
            pystray.Menu.SEPARATOR,
            item('Settings', self._tray_settings),
            item('Change Size', size_menu),
            item('Switch Theme', theme_menu),
            item('Reset Position', lambda icon, itm: self.cmd_queue.put(self._reset_position)),
            pystray.Menu.SEPARATOR,
            item('Solve CAPTCHA', self._tray_captcha, enabled=lambda item: self._captcha_btn_visible),
            pystray.Menu.SEPARATOR,
            item('Clear Cache & Cookies', self._tray_clear_cookies),
            item('Help / How it works', self._tray_help),
            pystray.Menu.SEPARATOR,
            item('Exit', self._tray_exit)
        )
        self.tray_icon = pystray.Icon("WE_Widget", tray_img, "WE Quota Widget", menu)
        threading.Thread(target=self.tray_icon.run, daemon=True).start()

    def _reset_position(self):
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        x = (sw // 2) - (self.w // 2)
        y = (sh // 2) - (self.h // 2)
        self.geometry(f"+{x}+{y}")
        config_data["window_x"] = x
        config_data["window_y"] = y
        threading.Thread(target=save_config, daemon=True).start()

    def _set_size(self, size_str):
        if config_data.get("widget_size", "small") == size_str: return
        config_data["widget_size"] = size_str
        save_config()
        if self.tray_icon: self.tray_icon.update_menu()
        self._rebuild_ui()

    def _set_theme(self, theme_str):
        if config_data.get("theme", "dark") == theme_str: return
        config_data["theme"] = theme_str
        save_config()
        if self.tray_icon: self.tray_icon.update_menu()
        self._rebuild_ui()

    def _tray_update_now(self, icon, item):
        self.cmd_queue.put(self.trigger_update)

    def _tray_help(self, icon, item):
        self.cmd_queue.put(lambda: HelpWindow(self))

    def _tray_settings(self, icon, item):
        self.cmd_queue.put(lambda: SetupWindow(self, self._on_setup_done))

    def _tray_clear_cookies(self, icon, item):
        self.cmd_queue.put(self._clear_cookies_action)

    def _tray_captcha(self, icon, item):
        if self._captcha_btn_visible:
            self.cmd_queue.put(self._open_captcha_window)

    def _tray_exit(self, icon, item):
        if self.tray_icon:
            self.tray_icon.stop()
        self.cmd_queue.put(self.destroy)
        sys.exit(0)

    def _on_press(self, e):
        self._drag_x = e.x_root - self.winfo_x()
        self._drag_y = e.y_root - self.winfo_y()

    def _on_drag(self, e):
        self._current_x = e.x_root - self._drag_x
        self._current_y = e.y_root - self._drag_y
        self.geometry(f"+{self._current_x}+{self._current_y}")

    def _on_release(self, e):
        if hasattr(self, '_current_x'):
            config_data["window_x"] = self._current_x
            config_data["window_y"] = self._current_y
            save_config()

    def _bind_drag_recursive(self, widget):
        widget.bind("<ButtonPress-1>", self._on_press)
        widget.bind("<B1-Motion>", self._on_drag)
        widget.bind("<ButtonRelease-1>", self._on_release)
        for child in widget.winfo_children():
            self._bind_drag_recursive(child)

    def _build_ui(self):
        for w in self.winfo_children(): w.destroy()
        t = T()
        sz = SIZES.get(config_data.get("widget_size", "small"), SIZES["small"])
        
        self.main_frame = ctk.CTkFrame(self, fg_color="transparent", corner_radius=0)
        self.main_frame.pack(fill="both", expand=True, padx=8, pady=8)
        
        self.data_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent", corner_radius=0)
        self.data_frame.pack(fill="x", pady=(5, 5), padx=10)
        
        self.lbl_current = ctk.CTkLabel(self.data_frame, text="...", font=("Segoe UI", sz["f_main"], "bold"), text_color=t["text_main"])
        self.lbl_current.pack(side="left", anchor="s")
        
        self.lbl_total = ctk.CTkLabel(self.data_frame, text="GB / --", font=("Segoe UI", sz["f_tot"], "bold"), text_color=t["text_total"])
        self.lbl_total.pack(side="left", anchor="s", padx=(5,0), pady=(0, 6))
        
        self.progress = ctk.CTkProgressBar(self.main_frame, height=8, corner_radius=4, fg_color=t["bar_track"], progress_color=t["bar_green"])
        self.progress.set(0)
        self.progress.pack(fill="x", padx=10)
        
        days_row = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        days_row.pack(fill="x", pady=(8,0), padx=10)

        self.lbl_days = ctk.CTkLabel(days_row, text="-- Days Remaining", font=("Segoe UI", sz["f_days"], "bold"), text_color=t["text_days"])
        self.lbl_days.pack(side="left", anchor="w")

        self.lbl_update = ctk.CTkLabel(days_row, text="", font=("Segoe UI", sz["f_upd"]), text_color=t["text_total"])
        self.lbl_update.pack(side="right", anchor="e")

        self._bind_drag_recursive(self)

    def _rebuild_ui(self):
        sz = SIZES.get(config_data.get("widget_size", "small"), SIZES["small"])
        self.w = sz["w"]
        self.h = sz["h"]
        x = config_data.get("window_x", 100)
        y = config_data.get("window_y", 100)
        self.geometry(f"{self.w}x{self.h}+{x}+{y}")
        ctk.set_appearance_mode("Dark" if config_data.get("theme","dark") == "dark" else "Light")
        self._build_ui()
        if self._last_data:
            d = self._last_data
            self.update_ui_safe(d["current"], d["total"], d["days"])

    def _clear_cookies_action(self):
        clear_cookies()
        self.lbl_days.configure(text="Cookies cleared!", text_color=T()["text_warn"])
        self.update()
        self.after(2000, lambda: self.trigger_update() if not self.is_updating else None)

    def _prompt_wrong_password(self):
        win = SetupWindow(self, self._on_setup_done)
        self.after(300, lambda: (
            win.lbl_err.configure(text="Invalid Password or Service Number.", text_color="#E74C3C"),
            win.e_pwd.delete(0, "end")
        ))

    def _on_setup_done(self):
        x = config_data.get("window_x", 100)
        y = config_data.get("window_y", 100)
        self.geometry(f"{self.w}x{self.h}+{x}+{y}")
        
        self.deiconify()
        self.lift()
        self.after(200, self._apply_desktop_style)
        
        self.after(1200, lambda: setattr(self, '_is_ready', True))

        if self._update_job:
            try: self.after_cancel(self._update_job)
            except: pass
        self._update_job = None
        self.trigger_update()

    def _apply_desktop_style(self):
        try:
            hwnd = ctypes.windll.user32.GetParent(self.winfo_id()) or self.winfo_id()
            
            ex_style = ctypes.windll.user32.GetWindowLongW(hwnd, -20)
            ctypes.windll.user32.SetWindowLongW(hwnd, -20, ex_style | 0x00000080)
            
            desktop_hwnd = ctypes.windll.user32.FindWindowW("Progman", None)
            
            workerw = [0]
            def enum_windows_callback(w_hwnd, lParam):
                if ctypes.windll.user32.FindWindowExW(w_hwnd, 0, "SHELLDLL_DefView", None):
                    workerw[0] = w_hwnd
                return True
            
            EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.c_int)
            ctypes.windll.user32.EnumWindows(EnumWindowsProc(enum_windows_callback), 0)
            
            if workerw[0]:
                desktop_hwnd = workerw[0]
                
            if desktop_hwnd:
                try:
                    set_owner = ctypes.windll.user32.SetWindowLongPtrW
                except AttributeError:
                    set_owner = ctypes.windll.user32.SetWindowLongW
                
                set_owner(hwnd, -8, desktop_hwnd)
                
        except Exception:
            pass

    def _show_captcha_btn(self):
        self._captcha_btn_visible = True
        if self.tray_icon: self.tray_icon.update_menu()
        try:
            self.lbl_days.configure(text="Click Tray Icon -> Solve CAPTCHA", text_color=T()["text_warn"])
            self.update()
        except: pass

    def _hide_captcha_btn(self):
        self._captcha_btn_visible = False
        if self.tray_icon: self.tray_icon.update_menu()

    def _open_captcha_window(self):
        driver = self._pending_captcha_driver
        done   = self._pending_captcha_done
        if not done: return
        
        def fetch_and_show():
            try: img = get_captcha_image(driver)
            except: img = None
            self.cmd_queue.put(lambda: self._show_captcha_dialog(img, driver, done))
        threading.Thread(target=fetch_and_show, daemon=True).start()

    def _show_captcha_dialog(self, img, driver, done):
        if done is None: return
        def on_submit(code):
            self._pending_captcha_code = code
            done.set()
        def on_refresh():
            def do_refresh():
                try:
                    r = driver.find_element(By.XPATH, "//img[@src and contains(@style,'cursor: pointer') and not(@alt='Captcha Image')]")
                    driver.execute_script("arguments[0].click();", r)
                    time.sleep(1.5)
                except: pass
            threading.Thread(target=do_refresh, daemon=True).start()
            self.cmd_queue.put(lambda: self.after(1800, self._open_captcha_window))

        CaptchaWindow(self, captcha_image=img, on_submit=on_submit, on_refresh=on_refresh)

    def _notify_and_solve_captcha(self, driver):
        if HAS_WINOTIFY:
            try:
                def _toast():
                    t = Notification(
                        app_id="WE Quota Widget",
                        title="WE Widget - CAPTCHA Required",
                        msg="Right-click the widget icon in the system tray and select 'Solve CAPTCHA' to verify.",
                        duration="long",
                    )
                    t.set_audio(audio.Default, loop=False)
                    t.show()
                threading.Thread(target=_toast, daemon=True).start()
            except: pass

        for attempt in range(5):
            done = threading.Event()
            self._pending_captcha_driver = driver
            self._pending_captcha_done   = done
            self._pending_captcha_code   = None
            
            self.cmd_queue.put(self._show_captcha_btn)

            waited = 0
            while not done.wait(timeout=5):
                waited += 5
                if waited >= 1800:
                    self.cmd_queue.put(self._hide_captcha_btn)
                    return False
                try: driver.execute_script("return 1;")
                except:
                    self.cmd_queue.put(self._hide_captcha_btn)
                    return False

            self.cmd_queue.put(self._hide_captcha_btn)
            code = self._pending_captcha_code
            if not code: return False

            try:
                inp = driver.find_element(By.XPATH, "//img[@alt=\'Captcha Image\']/following::input[1]")
                driver.execute_script("""
                    var el=arguments[0], val=arguments[1];
                    var s=Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,'value').set;
                    s.call(el,val);
                    el.dispatchEvent(new FocusEvent('focus',{bubbles:true}));
                    el.dispatchEvent(new InputEvent('input',{bubbles:true,data:val}));
                    el.dispatchEvent(new Event('change',{bubbles:true}));
                """, inp, code)
                time.sleep(0.5)
                btn = driver.find_element(By.XPATH, "//button[.//span[text()=\'Ok\']]")
                for _ in range(20):
                    if not btn.get_attribute("disabled"): break
                    time.sleep(0.25)
                driver.execute_script("arguments[0].click();", btn)
                time.sleep(3)
                try:
                    driver.find_element(By.XPATH, "//img[@alt=\'Captcha Image\']")
                    self._pending_captcha_driver = driver
                    continue
                except: return True
            except: return False
        return False

    def start_auto_update(self):
        self.trigger_update()

    def trigger_update(self):
        if self.is_updating: return
        self.is_updating = True
        self.lbl_days.configure(text="Updating...", text_color=T()["text_warn"])
        try: self.update() 
        except: pass
        threading.Thread(target=self.run_scraper, daemon=True).start()

    def run_scraper(self):
        driver  = None
        success = False
        is_no_internet = False
        try:
            driver = make_driver(images=True)
            wait   = WebDriverWait(driver, 30) 
            
            driver.get("https://my.te.eg/echannel/#/login")
            cookies_loaded = load_cookies(driver)
            if cookies_loaded:
                driver.refresh()
                time.sleep(3)
                
            try:
                driver.find_element(By.XPATH, "//span[contains(@style,'font-size: 2.1875rem')]")
                already_in = True
            except: 
                already_in = False

            if not already_in:
                driver.get("https://my.te.eg/echannel/#/login")
                time.sleep(2)

                try:
                    svc_input = wait.until(EC.visibility_of_element_located(
                        (By.XPATH, "//input[@id='login_loginid_input_01' or @formcontrolname='msisdn']")
                    ))
                    svc_input.clear()
                    svc_input.send_keys(config_data["service_number"] + Keys.TAB)
                    time.sleep(0.5)
                    driver.switch_to.active_element.send_keys("Internet" + Keys.ENTER)
                    time.sleep(0.5)
                    
                    pwd_input = driver.find_element(By.XPATH, "//input[@type='password']")
                    pwd_input.clear()
                    pwd_input.send_keys(decode_pw(config_data["password"]) + Keys.ENTER)
                    time.sleep(3)

                    try:
                        body = driver.find_element(By.TAG_NAME, "body").text
                        if "maximum number of attempts" in body or "try again after" in body:
                            self.cmd_queue.put(lambda: self.lbl_days.configure(text="Blocked: Retry in 1h", text_color=T()["text_err"]))
                            raise Exception("RATE_LIMITED")
                        if ("Invalid" in body or "incorrect" in body.lower() or "wrong" in body.lower() or "invalid password" in body.lower()):
                            self.cmd_queue.put(self._prompt_wrong_password)
                            raise Exception("WRONG_PASSWORD")
                    except Exception as _chk:
                        if "RATE_LIMITED" in str(_chk) or "WRONG_PASSWORD" in str(_chk):
                            raise

                except Exception as e:
                    pass

                try:
                    driver.find_element(By.XPATH, "//img[@alt='Captcha Image']")
                    captcha_present = True
                except: 
                    captcha_present = False

                if captcha_present:
                    self._captcha_driver = driver
                    solved = self._notify_and_solve_captcha(driver)
                    driver = getattr(self, "_captcha_driver", driver)
                    wait   = WebDriverWait(driver, 30) 
                    
                    if not solved:
                        clear_cookies()
                        raise Exception("CAPTCHA not solved")
                    time.sleep(4) 
                    
                    try:
                        wait.until(EC.visibility_of_element_located((By.XPATH, "//span[contains(@style,'font-size: 2.1875rem')]")))
                    except:
                        driver.get("https://my.te.eg/echannel/#/login")
                        time.sleep(2)
                        svc_input = wait.until(EC.visibility_of_element_located((By.XPATH, "//input[@id='login_loginid_input_01' or @formcontrolname='msisdn']")))
                        svc_input.clear()
                        svc_input.send_keys(config_data["service_number"] + Keys.TAB)
                        time.sleep(0.5)
                        driver.switch_to.active_element.send_keys("Internet" + Keys.ENTER)
                        time.sleep(0.5)
                        pwd_input = driver.find_element(By.XPATH, "//input[@type='password']")
                        pwd_input.clear()
                        pwd_input.send_keys(decode_pw(config_data["password"]) + Keys.ENTER)
                        time.sleep(4)
                        
                save_cookies(driver)

            usage_elem = wait.until(EC.visibility_of_element_located((By.XPATH, "//span[contains(@style, 'font-size: 2.1875rem')]")))
            current_quota = float(usage_elem.text)

            total = 0.0
            try:
                plan_elm = driver.find_element(By.XPATH, "//*[contains(text(),'GB)') or contains(text(),'GB )')]")
                m = re.search(r"\((\d+)\s*GB\)", plan_elm.text, re.IGNORECASE)
                if m: total = float(m.group(1))
            except: pass
            if total == 0 and config_data.get("total_quota"):
                total = float(config_data["total_quota"])

            days_val = "??"
            try:
                wait_slow = WebDriverWait(driver, 30)
                more_btn = wait_slow.until(EC.element_to_be_clickable((By.XPATH, "//span[contains(text(),'More Details')]")))
                driver.execute_script("arguments[0].click();", more_btn)
                time.sleep(2)
                d_elm = wait_slow.until(EC.visibility_of_element_located((By.XPATH, "//span[contains(@style,'0.8rem') and contains(text(),'Remaining Days')]")))
                d_match = re.search(r"(\d+)\s*Remaining Days", d_elm.text, re.IGNORECASE)
                if d_match:
                    days = int(d_match.group(1))
                    if days > 0: days_val = str(days)
                    config_data["renewal_date"] = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d")
            except:
                if config_data.get("renewal_date"):
                    try:
                        r    = datetime.strptime(config_data["renewal_date"], "%Y-%m-%d").date()
                        diff = (r - datetime.now().date()).days
                        if diff > 0:   
                            days_val = str(diff)
                    except: pass

            if total > 0: config_data["total_quota"] = total
            save_config()

            self.cmd_queue.put(lambda: self.update_ui_safe(current_quota, total, days_val))
            success = True

        except Exception as e:
            err_str = str(e)
            if "ERR_INTERNET_DISCONNECTED" in err_str or "ERR_NAME_NOT_RESOLVED" in err_str:
                is_no_internet = True
                self.cmd_queue.put(lambda: self.lbl_days.configure(text="No Internet", text_color=T()["text_err"]))
            elif "RATE_LIMITED" not in err_str and "WRONG_PASSWORD" not in err_str and "CAPTCHA not solved" not in err_str:
                tb_str = traceback.format_exc()
                with open(os.path.join(config_path, "error_log.txt"), "a", encoding="utf-8") as f:
                    f.write(f"\n--- {datetime.now()} ---\n{tb_str}\n")
                self.cmd_queue.put(lambda: self.lbl_days.configure(text="Err: check error_log.txt", text_color=T()["text_err"]))
        finally:
            active_driver = getattr(self, "_captcha_driver", None) or driver
            if active_driver:
                try: active_driver.quit()
                except: pass
            self._captcha_driver = None
            self.is_updating = False
            
            if self._update_job:
                try: self.after_cancel(self._update_job)
                except: pass
            
            if success:
                minutes = config_data.get("update_interval_minutes", 60)
                interval_ms = minutes * 60 * 1000
                self._update_job = self.after(interval_ms, self.start_auto_update)
            else:
                if is_no_internet:
                    self._update_job = self.after(600000, self.trigger_update) 
                else:
                    self._update_job = self.after(300000, self.trigger_update) 

    def update_ui_safe(self, current, total, days):
        self._last_data = {"current": current, "total": total, "days": days}
        t = T()
        try:
            self.lbl_current.configure(text=str(current))
            self.lbl_total.configure(text=f"GB / {int(total)}" if total else "GB / --")
            
            days_s = str(days)
            if days_s.lstrip('-').isdigit():
                days_txt = f"{days_s} Days Remaining"
                self.lbl_days.configure(text=days_txt, text_color=t["text_days"])
            else:
                self.lbl_days.configure(text=days_s, text_color=t["text_warn"])
                
            pct = (current / total) if total > 0 else 0
            self.progress.set(min(pct, 1.0))
            color = t["bar_green"] if pct > 0.5 else (t["bar_yellow"] if pct > 0.2 else t["bar_red"])
            self.progress.configure(progress_color=color)
            
            now_str = datetime.now().strftime("%I:%M %p")
            self.lbl_update.configure(text=f"Last update  {now_str}")
        except: pass

        try:
            if total > 0 and (current / total) < 0.20 and current > 0:
                cycle     = config_data.get("renewal_date", "")
                dismissed = config_data.get("alert_dismissed_cycle", "")
                if cycle != dismissed:
                    def mark_ok():
                        config_data["alert_dismissed_cycle"] = cycle
                        save_config()
                    AlertWindow(self, on_ok=mark_ok)
        except: pass

if __name__ == "__main__":
    app = QuotaWidget()
    app.mainloop()
