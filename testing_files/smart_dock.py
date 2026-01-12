import tkinter as tk
import pyautogui
import ctypes
from ctypes import wintypes
import threading
import time
import json
import os
import keyboard 
from pystray import Icon as TrayIcon, Menu as TrayMenu, MenuItem as TrayItem
from PIL import Image, ImageDraw

# --- Audio Imports ---
import comtypes
from comtypes import CLSCTX_ALL, GUID, IUnknown, COMMETHOD, HRESULT
from comtypes import client as com_client
from pycaw.pycaw import AudioUtilities

# ==========================================
#           PHASE 1 – MICRO ANIMATIONS
# ==========================================

def ease_out(t):
    return 1 - (1 - t) ** 3

def animate(root, duration_ms, steps, update_fn, done_fn=None):
    interval = max(1, duration_ms // steps)

    def step(i):
        if i > steps:
            if done_fn:
                done_fn()
            return
        t = ease_out(i / steps)
        update_fn(t)
        root.after(interval, lambda: step(i + 1))

    step(0)


# ==========================================
#           AUDIO SWITCHER LOGIC
# ==========================================

class AudioSwitcher:
    def __init__(self):
        try:
            comtypes.CoInitialize()
        except: pass
        self.policy_config = self._get_policy_config()

    def _get_policy_config(self):
        try:
            class IPolicyConfig(IUnknown):
                _iid_ = GUID('{f8679f50-850a-41cf-9c72-430f290290c8}')
                _methods_ = [
                    COMMETHOD([], HRESULT, 'GetMixFormat'),
                    COMMETHOD([], HRESULT, 'GetDeviceFormat'),
                    COMMETHOD([], HRESULT, 'ResetDeviceFormat'),
                    COMMETHOD([], HRESULT, 'SetDeviceFormat'),
                    COMMETHOD([], HRESULT, 'GetProcessingPeriod'),
                    COMMETHOD([], HRESULT, 'SetProcessingPeriod'),
                    COMMETHOD([], HRESULT, 'GetShareMode'),
                    COMMETHOD([], HRESULT, 'SetShareMode'),
                    COMMETHOD([], HRESULT, 'GetPropertyValue'),
                    COMMETHOD([], HRESULT, 'SetPropertyValue'),
                    COMMETHOD([], HRESULT, 'SetDefaultEndpoint', (['in'], ctypes.c_wchar_p, 'wszDeviceId'), (['in'], ctypes.c_int, 'role')),
                ]
            CLSID_PolicyConfig = GUID('{870af99c-171d-4f9e-af0d-e63df40c2bc9}')
            return com_client.CreateObject(CLSID_PolicyConfig, interface=IPolicyConfig)
        except Exception as e:
            return None

    def get_devices(self):
        devs = []
        try:
            device_enumerator = AudioUtilities.GetDeviceEnumerator()
            collection = device_enumerator.EnumAudioEndpoints(0, 1) # 0=Render, 1=Active
            count = collection.GetCount()
            for i in range(count):
                raw_dev = collection.Item(i)
                device = AudioUtilities.CreateDevice(raw_dev)
                devs.append({'name': device.FriendlyName, 'id': device.id})
        except: pass
        return devs

    def get_current_device_id(self):
        try:
            device_enumerator = AudioUtilities.GetDeviceEnumerator()
            current = device_enumerator.GetDefaultAudioEndpoint(0, 1) # 0=Render, 1=Console
            return current.GetId()
        except: return None

    def set_default_device(self, device_id):
        if not self.policy_config: return
        try:
            self.policy_config.SetDefaultEndpoint(device_id, 0)
            self.policy_config.SetDefaultEndpoint(device_id, 2)
        except: pass

# ==========================================
#           MODERN UI COMPONENTS
# ==========================================

class ModernMenu(tk.Toplevel):
    def __init__(self, master, x, y, items, current_id, callback):
        super().__init__(master)
        self.callback = callback
        
        self.overrideredirect(True)
        self.configure(bg="#2b2b2b")
        self.attributes("-topmost", True)
        self.attributes("-alpha", 0.98) 
        
        self.border = tk.Frame(self, bg="#444444", padx=1, pady=1)
        self.border.pack(fill="both", expand=True)
        
        self.container = tk.Frame(self.border, bg="#252526")
        self.container.pack(fill="both", expand=True)

        lbl = tk.Label(self.container, text="Select Audio Output", 
                       font=("Segoe UI", 9, "bold"), 
                       bg="#252526", fg="#cccccc", pady=8, padx=10, anchor="w")
        lbl.pack(fill="x")
        
        tk.Frame(self.container, bg="#3e3e42", height=1).pack(fill="x", padx=5, pady=(0, 5))

        for item in items:
            self.create_item(item, current_id)
            
        self.geometry(f"+{x}+{y}")
        self.bind("<FocusOut>", lambda e: self.destroy())
        self.bind("<Escape>", lambda e: self.destroy())
        self.focus_force()

    def create_item(self, item, current_id):
        is_active = item['id'] == current_id
        
        row = tk.Frame(self.container, bg="#252526", cursor="hand2")
        row.pack(fill="x", pady=1)

        dot_color = "#98c379" if is_active else "#252526"
        dot = tk.Label(row, text="●", font=("Arial", 8), bg="#252526", fg=dot_color, width=3)
        dot.pack(side="left")

        name = item['name']
        if len(name) > 35: name = name[:33] + "..."
        
        lbl = tk.Label(row, text=name, font=("Segoe UI", 9), 
                       bg="#252526", fg="#ffffff", anchor="w", padx=5, pady=6)
        lbl.pack(side="left", fill="x", expand=True)

        def on_enter(e): 
            row.config(bg="#37373d"); dot.config(bg="#37373d"); lbl.config(bg="#37373d")
        def on_leave(e): 
            row.config(bg="#252526"); dot.config(bg="#252526"); lbl.config(bg="#252526")
        def on_click(e):
            self.callback(item['id'])
            self.destroy()

        for w in (row, lbl, dot):
            w.bind("<Enter>", on_enter)
            w.bind("<Leave>", on_leave)
            w.bind("<Button-1>", on_click)

class ModernButton(tk.Label):
    def __init__(self, parent, text, command,
                 bg="#333333", hover_bg="#4d4d4d",
                 fg="#ffffff", font=("Segoe UI", 11),
                 width=5, height=2):

        super().__init__(
            parent, text=text, bg=bg, fg=fg,
            font=font, cursor="hand2",
            width=width, height=height
        )

        self.command = command
        self.bg_normal = bg
        self.bg_hover = hover_bg
        self.bg_active = ACCENT_COLOR
        self._pressed = False

        self.bind("<Enter>", self._enter)
        self.bind("<Leave>", self._leave)
        self.bind("<ButtonPress-1>", self._press)
        self.bind("<ButtonRelease-1>", self._release)

    def _enter(self, e):
        if not self._pressed:
            self.configure(bg=self.bg_hover)

    def _leave(self, e):
        if not self._pressed:
            self.configure(bg=self.bg_normal)

    def _press(self, e):
        self._pressed = True
        self.configure(bg=self.bg_active)

        base_font = self.cget("font")
        animate(
            app.root, 80, 5,
            lambda t: self.configure(
                font=(base_font[0], int(base_font[1] * (1 - 0.08 * t)))
            )
        )

    def _release(self, e):
        self._pressed = False
        self.configure(bg=self.bg_hover)

        if self.command:
            self.command()

        base_font = self.cget("font")
        animate(
            app.root, 120, 6,
            lambda t: self.configure(
                font=(base_font[0], int(base_font[1] * (0.92 + 0.08 * t)))
            ),
            lambda: self.configure(font=base_font)
        )


# ==========================================
#           MAIN APPLICATION
# ==========================================

CONFIG_FILE = "floatpad_config.json"
DEFAULT_WIDTH = 300
DEFAULT_HEIGHT = 460
MIN_WIDTH = 220
MIN_HEIGHT = 350
SNAP_THRESHOLD = 75

BG_COLOR = "#1e1e1e"
TITLE_BG = "#252526"
ACCENT_COLOR = "#0078d4"
BTN_COLOR = "#333333"
BTN_HOVER = "#454545"
TXT_COLOR = "#ffffff"

user32 = ctypes.windll.user32
dwmapi = ctypes.windll.dwmapi
SetWindowCompositionAttribute = user32.SetWindowCompositionAttribute

class MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT), ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]

class ACCENT_POLICY(ctypes.Structure):
    _fields_ = [("AccentState", ctypes.c_int), ("AccentFlags", ctypes.c_int), ("GradientColor", ctypes.c_int), ("AnimationId", ctypes.c_int)]

class WINDOWCOMPOSITIONATTRIBDATA(ctypes.Structure):
    _fields_ = [("Attribute", ctypes.c_int), ("Data", ctypes.POINTER(ACCENT_POLICY)), ("SizeOfData", ctypes.c_int)]

def apply_acrylic(hwnd, use_glass=True):
    try:
        policy = ACCENT_POLICY()
        policy.AccentState = 3 if use_glass else 0
        policy.GradientColor = 0xF21e1e1e if use_glass else 0xFF1e1e1e
        data = WINDOWCOMPOSITIONATTRIBDATA()
        data.Attribute = 19
        data.Data = ctypes.pointer(policy)
        data.SizeOfData = ctypes.sizeof(policy)
        SetWindowCompositionAttribute(hwnd, ctypes.byref(data))
    except: pass

def apply_rounded_corners(hwnd):
    try: dwmapi.DwmSetWindowAttribute(hwnd, 33, ctypes.byref(ctypes.c_int(2)), 4)
    except: pass


def get_foreground_app():
    hwnd = ctypes.windll.user32.GetForegroundWindow()
    if not hwnd:
        return None

    pid = ctypes.c_ulong()
    ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))

    try:
        import psutil
        return psutil.Process(pid.value).name().lower()
    except:
        return None

class App:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("FloatPad")
        self.root.configure(bg=BG_COLOR)
        self.audio_switcher = AudioSwitcher()
        
        self.is_docked = False
        self.is_animating = False
        self.last_interaction = time.time()
        self.ignore_next_keypress = False
        self.drag_start_x = 0
        self.drag_start_y = 0
        
        # Load settings
        self.settings = self.load_config()
        self.timeout = self.settings.get("timeout", 5)
        self.use_glass = self.settings.get("use_glass", True)
        self.hide_on_type = self.settings.get("hide_on_type", True) 
        self.always_default_dock = self.settings.get("always_default_dock", False)
        
        # ---- Phase 2: Mode System ----
        self.current_mode = self.settings.get("current_mode", "PIN")
        self._mode_press_time = 0

        # Dock Positioning Logic
        self.last_dock_geo = self.settings.get("last_dock_geo", None)
        
        geo = self.settings.get("geometry", f"{DEFAULT_WIDTH}x{DEFAULT_HEIGHT}+500+200")
        if "1x1" in geo: geo = f"{DEFAULT_WIDTH}x{DEFAULT_HEIGHT}+500+200"
        self.root.geometry(geo)
        self.saved_geometry = geo

        self.root.overrideredirect(True)
        self.root.wm_attributes("-topmost", True)
        self.root.update_idletasks()
        
        self.set_no_focus() 
        self.refresh_visuals()
        self.setup_ui()
        self.setup_dock_ui()
        self.setup_context_menu()
        
        # Initial Docking
        self.root.after(100, self.dock_window)
        self.stop_threads = False
        
        try: keyboard.on_press(self.on_physical_keypress)
        except: pass

        threading.Thread(target=self.timer_loop, daemon=True).start()
        threading.Thread(target=self.setup_tray, daemon=True).start()
        threading.Thread(target=self.context_watcher, daemon=True).start()

        self.root.bind("<F5>", lambda e: self.toggle_glass())
        self.app_mode_rules = {
            "vlc.exe": "MEDIA",
            "spotify.exe": "MEDIA",
            "chrome.exe": "MEDIA",
            "msedge.exe": "MEDIA",
        }
        self.last_auto_mode = None

    def context_watcher(self):
        while not self.stop_threads:
            app = get_foreground_app()

            if app in self.app_mode_rules:
                target = self.app_mode_rules[app]
                if self.current_mode != target:
                    self.last_auto_mode = self.current_mode
                    self.root.after(0, lambda m=target: self.switch_mode(m))

            elif self.last_auto_mode:
                self.root.after(0, lambda m=self.last_auto_mode: self.switch_mode(m))
                self.last_auto_mode = None

            time.sleep(1.2)


    # ==========================================
    #           PHASE 2 – MODES
    # ==========================================

    def switch_mode(self, mode):
        if mode == self.current_mode:
            return
        self.current_mode = mode
        self.refresh_mode_ui()
        self.show_toast(f"{mode.title()} Mode")
        self.save_config()

    def cycle_mode(self):
        order = ["PIN", "MEDIA", "QUICK"]
        i = order.index(self.current_mode)
        self.switch_mode(order[(i + 1) % len(order)])

    def refresh_mode_ui(self):
        for f in (self.pin_frame, self.media_mode_frame, self.quick_frame):
            f.pack_forget()

        if self.current_mode == "PIN":
            # ✅ Balanced layout
            self.media_mode_frame.pack(fill="x")
            self.pin_frame.pack(expand=True, fill="both")

        elif self.current_mode == "MEDIA":
            self.media_mode_frame.pack(expand=True, fill="both")

        else:
            self.quick_frame.pack(expand=True, fill="both")


    def set_no_focus(self):
        try:
            hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id())
            style = ctypes.windll.user32.GetWindowLongW(hwnd, -20)
            ctypes.windll.user32.SetWindowLongW(hwnd, -20, style | 0x08000000 | 0x00000008)
        except: pass

    def refresh_visuals(self):
        try:
            hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id())
            apply_acrylic(hwnd, self.use_glass)
            apply_rounded_corners(hwnd)
            self.root.configure(bg=BG_COLOR)
        except: pass

    def toggle_glass(self):
        self.use_glass = not self.use_glass
        self.refresh_visuals()
        self.save_config()

    def update_preferences(self):
        self.hide_on_type = self.hide_on_type_var.get()
        self.always_default_dock = self.always_default_dock_var.get()
        self.save_config()

    def setup_ui(self):
        self.main_frame = tk.Frame(self.root, bg=BG_COLOR)
        
        self.title_bar = tk.Frame(self.main_frame, bg=TITLE_BG, height=32)
        self.title_bar.pack(fill='x', side='top', pady=0)
        self.title_bar.pack_propagate(False)
        
        title = tk.Label(self.title_bar, text="FloatPad", bg=TITLE_BG, fg="#888888", font=("Segoe UI", 9))
        title.pack(side="left", padx=10)
        self.bind_drag(title)
        self.bind_drag(self.title_bar)

        close_btn = tk.Label(self.title_bar, text="✕", bg=TITLE_BG, fg="#aaaaaa", font=("Arial", 9), cursor="hand2")
        close_btn.pack(side="right", padx=10, fill='y')
        close_btn.bind("<Button-1>", lambda e: self.dock_window())
        close_btn.bind("<Enter>", lambda e: close_btn.config(fg="white"))
        close_btn.bind("<Leave>", lambda e: close_btn.config(fg="#aaaaaa"))

        content = tk.Frame(self.main_frame, bg=BG_COLOR)
        content.pack(expand=True, fill="both", padx=8, pady=5)

        # ---- Mode Containers ----
        self.pin_frame = tk.Frame(content, bg=BG_COLOR)
        self.media_mode_frame = tk.Frame(content, bg=BG_COLOR)
        self.quick_frame = tk.Frame(content, bg=BG_COLOR)

        media_frame = tk.Frame(self.media_mode_frame, bg=BG_COLOR, height=52)
        media_frame.pack(fill="x", pady=(0, 6))
        media_frame.pack_propagate(False)


        
        media_items = [
            ("🔉", lambda: self.virtual_key_action('volumedown')),
            ("⏯", lambda: self.virtual_key_action('playpause')),
            ("🔊", lambda: self.virtual_key_action('volumeup')),
            ("🎧", self.show_audio_menu)
        ]
        
        for i, (txt, cmd) in enumerate(media_items):
            btn = ModernButton(media_frame, text=txt, command=cmd, bg="#2b2b2b", hover_bg="#3e3e42", font=("Segoe UI", 12))
            btn.grid(row=0, column=i, sticky="nsew", padx=2)
            media_frame.grid_columnconfigure(i, weight=1)
            if txt == "🎧":
                self.audio_btn_widget = btn
                btn.bind("<ButtonPress-1>", self._audio_press)
                btn.bind("<ButtonRelease-1>", self._audio_release)


        keys_frame = tk.Frame(self.pin_frame, bg=BG_COLOR)
        keys_frame.pack(expand=True, fill="both")


        numpad = ['7', '8', '9', '4', '5', '6', '1', '2', '3', 'backspace', '0', 'enter']
        labels = {'backspace': '⌫', 'enter': '⏎'}
        
        for i, key in enumerate(numpad):
            r = i // 3; c = i % 3
            lbl = labels.get(key, key)
            btn = ModernButton(keys_frame, text=lbl, 
                               command=lambda k=key: self.virtual_key_action(k),
                               bg="#252526", hover_bg="#37373d", 
                               font=("Segoe UI", 14), height=2)
            btn.grid(row=r, column=c, sticky="nsew", padx=2, pady=2)
            keys_frame.grid_columnconfigure(c, weight=1)
            keys_frame.grid_rowconfigure(r, weight=1)

        grip = tk.Label(self.main_frame, text="◢", bg=BG_COLOR, fg="#444444", cursor="sizing", font=("Arial", 8))
        grip.pack(side="bottom", anchor="e", padx=2)
        grip.bind("<ButtonPress-1>", self.start_resize)
        grip.bind("<B1-Motion>", self.do_resize)
        grip.bind("<ButtonRelease-1>", self.stop_resize)

        # ---- Quick Mode ----
        actions = [
            ("🔒", lambda: ctypes.windll.user32.LockWorkStation()),
            ("📸", lambda: pyautogui.hotkey("win", "shift", "s")),
            ("🎧", self.show_audio_menu),
        ]

        for i, (txt, cmd) in enumerate(actions):
            btn = ModernButton(
                self.quick_frame,
                text=txt,
                command=lambda c=cmd: (c(), self.dock_window()),
                bg="#252526",
                hover_bg="#37373d",
                font=("Segoe UI", 16),
                height=2
            )
            btn.grid(row=i // 2, column=i % 2, sticky="nsew", padx=6, pady=6)

            self.quick_frame.grid_columnconfigure(i % 2, weight=1)
        
        self.refresh_mode_ui()

    def _audio_press(self, e):
        self._mode_press_time = time.time()

    def _audio_release(self, e):
        if time.time() - self._mode_press_time > 0.5:
            self.cycle_mode()
        else:
            self.show_audio_menu()


    def setup_dock_ui(self):
        self.dock_frame = tk.Frame(self.root, bg=BG_COLOR, cursor="fleur")
        self.expand_btn = tk.Button(self.dock_frame, text="●", bg=BG_COLOR, fg="#666666", bd=0,
                                    activebackground=BG_COLOR, activeforeground=ACCENT_COLOR,
                                    command=self.undock_window)
        self.expand_btn.pack(expand=True, fill="both")
        self.bind_drag(self.dock_frame)
        self.bind_drag(self.expand_btn)
        self.dock_frame.bind("<MouseWheel>", lambda e: self.cycle_mode())


    def show_audio_menu(self):
        devices = self.audio_switcher.get_devices()
        current = self.audio_switcher.get_current_device_id()
        if not devices: return
        x = self.audio_btn_widget.winfo_rootx()
        y = self.audio_btn_widget.winfo_rooty() + self.audio_btn_widget.winfo_height() + 5
        if y + 150 > self.root.winfo_screenheight(): y = self.audio_btn_widget.winfo_rooty() - 150
        ModernMenu(self.root, x, y, devices, current, lambda dev_id: (self.audio_switcher.set_default_device(dev_id), self.show_toast("Audio output switched")))


    def bind_drag(self, widget):
        widget.bind("<ButtonPress-1>", self.start_move)
        widget.bind("<B1-Motion>", self.do_move)
        widget.bind("<ButtonRelease-1>", self.stop_move)

    def on_physical_keypress(self, event):
        if self.ignore_next_keypress: return
        if self.root.state() == 'withdrawn': return
        if self.hide_on_type and not self.is_docked:
            self.root.after(0, self.dock_window)

    def virtual_key_action(self, key):
        self.last_interaction = time.time()
        self.ignore_next_keypress = True 
        try: pyautogui.press(key)
        except: pass
        self.root.after(100, lambda: setattr(self, 'ignore_next_keypress', False))
        if self.current_mode == "PIN" and key == "enter":
            self.root.after(200, self.dock_window)


    def timer_loop(self):
        while not self.stop_threads:
            if self.root.state() == 'withdrawn':
                time.sleep(1)
                continue
            try:
                mx, my = self.root.winfo_pointerxy()
                wx, wy = self.root.winfo_rootx(), self.root.winfo_rooty()
                ww, wh = self.root.winfo_width(), self.root.winfo_height()
                if wx <= mx <= wx+ww and wy <= my <= wy+wh:
                    self.last_interaction = time.time()
            except: pass
            
            if not self.is_docked and (time.time() - self.last_interaction > self.timeout):
                if self.timeout < 9000: self.root.after(0, self.dock_window)
            time.sleep(0.5)

    def get_monitor(self):
        try:
            hwnd = self.root.winfo_id()
            h_mon = user32.MonitorFromWindow(hwnd, 2)
            mi = MONITORINFO(); mi.cbSize = ctypes.sizeof(MONITORINFO)
            user32.GetMonitorInfoW(h_mon, ctypes.byref(mi))
            return {'l': mi.rcMonitor.left, 't': mi.rcMonitor.top, 'r': mi.rcMonitor.right, 'b': mi.rcMonitor.bottom}
        except: return {'l': 0, 't': 0, 'r': self.root.winfo_screenwidth(), 'b': self.root.winfo_screenheight()}

    def dock_window(self):
        """Logic to decide WHERE to dock the window."""
        if not self.is_docked:
            if self.root.winfo_width() > 100: 
                self.saved_geometry = self.root.geometry()

        mon = self.get_monitor()
        
        # --- IMPROVED POSITIONING LOGIC ---
        if self.always_default_dock:
            # Force Top-Left (not totally left, small offset)
            target_x = mon['l'] + 100 
            target_y = mon['t']
            mode = 'top'
        elif self.last_dock_geo:
            # Re-use the last successful dock position
            return self.animate_to_dock_string(self.last_dock_geo)
        else:
            # Calculate nearest edge based on current mouse/window position
            mx, my = self.root.winfo_pointerxy()
            dl, dt = mx - mon['l'], my - mon['t']
            dr = mon['r'] - mx
            md = min(dl, dt, dr)
            
            if md == dt: mode, target_x, target_y = 'top', mx, mon['t']
            elif md == dl: mode, target_x, target_y = 'left', mon['l'], my
            else: mode, target_x, target_y = 'right', mon['r'], my

        self.set_dock(mode, target_x, target_y)

    def set_dock(self, mode, x, y):
        self.is_docked = True
        self.main_frame.pack_forget()
        self.dock_frame.pack(fill='both', expand=True)
        w, h = (80, 20) if mode == 'top' else (20, 80)
        fx, fy = (x - 40, y) if mode == 'top' else (x if mode == 'left' else x-20, y-40)
        self.expand_btn.config(text="—" if mode == 'top' else "│")
        
        dock_geo = f"{w}x{h}+{fx}+{fy}"
        self.last_dock_geo = dock_geo # Remember this spot
        self.animate(self.root.geometry(), dock_geo)
        self.save_config()

    def animate_to_dock_string(self, geo_str):
        self.is_docked = True
        self.main_frame.pack_forget()
        self.dock_frame.pack(fill='both', expand=True)
        # Determine mode based on dimensions in string
        if "80x20" in geo_str: self.expand_btn.config(text="—")
        else: self.expand_btn.config(text="│")
        self.animate(self.root.geometry(), geo_str)

    def undock_window(self):
        if not self.is_docked: return
        self.is_docked = False
        self.dock_frame.pack_forget()
        self.main_frame.pack(fill='both', expand=True)
        geo = self.saved_geometry if self.saved_geometry else f"{DEFAULT_WIDTH}x{DEFAULT_HEIGHT}+500+200"
        self.animate(self.root.geometry(), geo)
        self.last_interaction = time.time()

    def animate(self, s_geo, e_geo):
        def parse(g): return [int(x) for x in g.replace('+','x').split('x') if x]
        try:
            sw, sh, sx, sy = parse(s_geo)
            ew, eh, ex, ey = parse(e_geo)
        except: return
        steps = 12
        def step(i):
            if i > steps: self.root.geometry(e_geo); return
            t = ease_out(i / steps)
            self.root.geometry(f"{int(sw+(ew-sw)*t)}x{int(sh+(eh-sh)*t)}+{int(sx+(ex-sx)*t)}+{int(sy+(ey-sy)*t)}")
            self.root.after(10, lambda: step(i+1))
        step(0)

    def start_move(self, e): self.dx, self.dy = e.x, e.y; self.drag_start_x = self.root.winfo_x(); self.drag_start_y = self.root.winfo_y()
    def do_move(self, e): self.root.geometry(f"+{self.root.winfo_x() + e.x - self.dx}+{self.root.winfo_y() + e.y - self.dy}")
    def stop_move(self, e):
        if ((self.root.winfo_x()-self.drag_start_x)**2 + (self.root.winfo_y()-self.drag_start_y)**2)**0.5 < 5: return
        mon = self.get_monitor()
        x, y = self.root.winfo_x(), self.root.winfo_y()
        # If dragged near any edge, dock there and SAVE that as the new preferred spot
        if x < mon['l']+SNAP_THRESHOLD or x > mon['r']-SNAP_THRESHOLD or y < mon['t']+SNAP_THRESHOLD: 
            # Reset last_dock_geo so dock_window calculates the NEW nearest edge
            self.last_dock_geo = None 
            self.dock_window()
        else: 
            self.save_config()

    def start_resize(self, e):
        self.resize_start_x = e.x_root
        self.resize_start_y = e.y_root
        self.start_w = self.root.winfo_width()
        self.start_h = self.root.winfo_height()

    def do_resize(self, e):
        dx = e.x_root - self.resize_start_x
        dy = e.y_root - self.resize_start_y
        new_w, new_h = self.start_w + dx, self.start_h + dy
        if new_w > MIN_WIDTH and new_h > MIN_HEIGHT:
            self.root.geometry(f"{new_w}x{new_h}")
            self.root.update_idletasks()

    def stop_resize(self, e):
        self.save_config()
        if self.use_glass:
             hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id())
             apply_acrylic(hwnd, True)

    def set_timeout(self, seconds): 
        self.timeout = seconds; self.save_config()
    def reset_size(self): 
        self.root.geometry(f"{DEFAULT_WIDTH}x{DEFAULT_HEIGHT}"); self.save_config()
    def hide_window(self):
        self.root.withdraw()

    def setup_context_menu(self):
        self.context_menu = tk.Menu(self.root, tearoff=0, bg=BG_COLOR, fg=TXT_COLOR)
        
        self.time_menu = tk.Menu(self.context_menu, tearoff=0, bg=BG_COLOR, fg=TXT_COLOR)
        self.time_menu.add_command(label="5 Seconds", command=lambda: self.set_timeout(5))
        self.time_menu.add_command(label="10 Seconds", command=lambda: self.set_timeout(10))
        self.time_menu.add_command(label="Never Auto-Hide", command=lambda: self.set_timeout(99999))
        
        self.hide_on_type_var = tk.BooleanVar(value=self.hide_on_type)
        self.always_default_dock_var = tk.BooleanVar(value=self.always_default_dock)

        self.context_menu.add_checkbutton(label="Auto-Dock on Typing", variable=self.hide_on_type_var, command=self.update_preferences)
        self.context_menu.add_checkbutton(label="Always Dock to Top-Left", variable=self.always_default_dock_var, command=self.update_preferences)
        self.context_menu.add_separator()
        
        self.context_menu.add_cascade(label="Auto-Dock Timer", menu=self.time_menu)
        self.context_menu.add_command(label="Toggle Glass/Solid (F5)", command=self.toggle_glass)
        self.context_menu.add_command(label="Hide to Tray", command=self.hide_window)
        self.context_menu.add_command(label="Reset Size", command=self.reset_size)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="Quit", command=self.quit_app)
        
        self.root.bind("<Button-3>", lambda e: self.context_menu.tk_popup(e.x_root, e.y_root))

    def setup_tray(self):
        # Set show_from_tray as the default action
        menu = TrayMenu(
            TrayItem('Show', self.show_from_tray, default=True), 
            TrayItem('Dock to Default', self.force_default_dock),
            TrayItem('Quit', self.quit_app)
        )
        img = Image.new('RGB', (64,64), (30,30,30))
        d = ImageDraw.Draw(img)
        d.rectangle([16,26,48,38], fill="white")
        self.tray = TrayIcon("FloatPad", img, "FloatPad", menu)
        self.tray.run()

    def show_from_tray(self, icon=None, item=None):
        """Spring feature: brings the window back and makes it vibrate to catch the eye."""
        self.root.after(0, self.root.deiconify)
        self.root.after(10, self.root.lift)
        # Snap to dock instantly first
        self.root.after(20, lambda: self.dock_window(animate=False))
        # Trigger the vibration catch
        self.root.after(50, self.vibrate_eye_catch)

    def vibrate_eye_catch(self):
        """Quick vibration effect to make the window easy to find."""
        orig_geo = self.root.geometry()
        try:
            # Parse current position
            parts = orig_geo.replace('+', 'x').split('x')
            w, h, x, y = map(int, parts)
            
            # Vibration sequence (offsets in pixels)
            offsets = [5, -5, 4, -4, 2, -2, 0]
            
            def do_shake(index):
                if index < len(offsets):
                    new_x = x + offsets[index]
                    self.root.geometry(f"{w}x{h}+{new_x}+{y}")
                    self.root.after(30, lambda: do_shake(index + 1))
                else:
                    self.root.geometry(orig_geo) # Reset to perfect position
            
            do_shake(0)
        except:
            pass

    def dock_window(self, animate=True):
        """Updated dock logic to support instant snapping."""
        if not self.is_docked:
            if self.root.winfo_width() > 100: 
                self.saved_geometry = self.root.geometry()

        mon = self.get_monitor()
        
        if self.always_default_dock:
            target_x = mon['l'] + 100 
            target_y = mon['t']
            mode = 'top'
        elif self.last_dock_geo:
            if animate:
                return self.animate_to_dock_string(self.last_dock_geo)
            else:
                # Instant Snap
                self.is_docked = True
                self.main_frame.pack_forget()
                self.dock_frame.pack(fill='both', expand=True)
                # Ensure correct button text based on saved geometry
                self.expand_btn.config(text="—" if "80x20" in self.last_dock_geo else "│")
                self.root.geometry(self.last_dock_geo)
                return
        else:
            mx, my = self.root.winfo_pointerxy()
            dl, dt = mx - mon['l'], my - mon['t']
            dr = mon['r'] - mx
            md = min(dl, dt, dr)
            if md == dt: mode, target_x, target_y = 'top', mx, mon['t']
            elif md == dl: mode, target_x, target_y = 'left', mon['l'], my
            else: mode, target_x, target_y = 'right', mon['r'], my

        self.set_dock(mode, target_x, target_y, animate=animate)

    def set_dock(self, mode, x, y, animate=True):
        """Updated set_dock with animation toggle."""
        self.is_docked = True
        self.main_frame.pack_forget()
        self.dock_frame.pack(fill='both', expand=True)
        w, h = (80, 20) if mode == 'top' else (20, 80)
        fx, fy = (x - 40, y) if mode == 'top' else (x if mode == 'left' else x-20, y-40)
        self.expand_btn.config(text="—" if mode == 'top' else "│")
        
        dock_geo = f"{w}x{h}+{fx}+{fy}"
        self.last_dock_geo = dock_geo 
        
        if animate:
            self.animate(self.root.geometry(), dock_geo)
        else:
            self.root.geometry(dock_geo)
        self.save_config()

    def load_config(self):
        if os.path.exists(CONFIG_FILE):
            try: return json.load(open(CONFIG_FILE))
            except: pass
        return {}

    def save_config(self):
        if not self.is_docked: 
            self.settings["geometry"] = self.root.geometry()
        
        self.settings.update({
            "timeout": self.timeout, 
            "use_glass": self.use_glass, 
            "hide_on_type": self.hide_on_type,
            "always_default_dock": self.always_default_dock,
            "last_dock_geo": self.last_dock_geo,
            "current_mode": self.current_mode,
        })
        with open(CONFIG_FILE, 'w') as f: json.dump(self.settings, f)
    
    def quit_app(self, *args):
        self.save_config()
        self.stop_threads = True
        try: keyboard.unhook_all()
        except: pass
        try: self.tray.stop()
        except: pass
        try:
            self.root.quit()
            self.root.destroy()
        except: pass
        os._exit(0)
    
    def force_default_dock(self, icon=None, item=None):
        """Instantly snaps the window to the safe default (Top-Left) position."""
        self.root.after(0, self.root.deiconify)
        self.root.after(10, self.root.lift)
        
        # Calculate the default 'safe' spot (Top-Left offset)
        mon = self.get_monitor()
        target_x = mon['l'] + 100 
        target_y = mon['t']
        
        # Snap instantly using your existing set_dock method
        self.root.after(20, lambda: self.set_dock('top', target_x, target_y, animate=False))
        self.root.after(50, self.vibrate_eye_catch)

    def show_toast(self, text, duration=900):
        toast = tk.Toplevel(self.root)
        toast.overrideredirect(True)
        toast.attributes("-topmost", True)
        toast.configure(bg="#2b2b2b")

        tk.Label(
            toast, text=text,
            bg="#2b2b2b", fg="white",
            font=("Segoe UI", 9),
            padx=12, pady=6
        ).pack()

        x = self.root.winfo_rootx() + 20
        y = self.root.winfo_rooty() + self.root.winfo_height() + 6
        toast.geometry(f"+{x}+{y}")
        toast.attributes("-alpha", 0)

        animate(self.root, 150, 8,
                lambda t: toast.attributes("-alpha", t))

        toast.after(duration, lambda:
            animate(self.root, 150, 8,
                    lambda t: toast.attributes("-alpha", 1 - t),
                    toast.destroy))




if __name__ == "__main__":
    app = App()
    try:
        app.root.mainloop()
    except KeyboardInterrupt:
        app.quit_app()