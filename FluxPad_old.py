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
from PIL import Image, ImageDraw, ImageTk, ImageOps
import sys

# --- Audio Imports ---
import comtypes
from comtypes import CLSCTX_ALL, GUID, IUnknown, COMMETHOD, HRESULT
from comtypes import client as com_client
from pycaw.pycaw import AudioUtilities

def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)

class ToolTip:
    def __init__(self, widget, get_text_func):
        self.widget = widget
        self.get_text_func = get_text_func 
        self.tip_window = None
        self.label = None
        # Animation state tracking
        self.alpha = 0.0
        self.fade_job = None 
        self.is_hovering = False

        self.widget.bind("<Enter>", self.on_enter, add="+") 
        self.widget.bind("<Leave>", self.on_leave, add="+")

    def on_enter(self, event=None):
        self.is_hovering = True
        # Cancel any pending fade-outs
        if self.fade_job:
            self.widget.after_cancel(self.fade_job)
            self.fade_job = None
        
        text = self.get_text_func()
        if not text: return
        
        if not self.tip_window:
            self.create_window(text)
        
        # Start fading in
        self.fade_in()

    def on_leave(self, event=None):
        self.is_hovering = False
        # Cancel any pending fade-ins
        if self.fade_job:
            self.widget.after_cancel(self.fade_job)
            self.fade_job = None
            
        # Start fading out
        if self.tip_window:
            self.fade_out()

    def create_window(self, text):
        x = self.widget.winfo_rootx() + 5
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 5
        
        self.tip_window = tw = tk.Toplevel(self.widget)
        # Important: Start fully transparent
        self.alpha = 0.0
        tw.attributes("-alpha", self.alpha)
        tw.attributes("-topmost", True)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        
        border_frame = tk.Frame(tw, bg="#555555", padx=1, pady=1)
        border_frame.pack(fill="both", expand=True)
        
        self.label = tk.Label(border_frame, text=text, justify=tk.LEFT,
                          background="#2b2b2b", fg="#ffffff",
                          relief=tk.FLAT,
                          font=("Segoe UI", 9))
        self.label.pack(fill="both", expand=True, ipadx=5, ipady=2)

    def fade_in(self):
        # Stop if user left or window is gone
        if not self.is_hovering or not self.tip_window: return
            
        if self.alpha < 1.0:
            # Increase opacity slightly
            self.alpha += 0.08  # Adjust speed here (lower = smoother/slower)
            if self.alpha > 1.0: self.alpha = 1.0
            
            try: self.tip_window.attributes("-alpha", self.alpha)
            except: pass # Window might have closed during animate
            
            # Schedule next step in 15ms
            self.fade_job = self.widget.after(15, self.fade_in)
        else:
            self.fade_job = None

    def fade_out(self):
        # Stop if window is gone
        if not self.tip_window: return
            
        if self.alpha > 0.0:
            # Decrease opacity slightly
            self.alpha -= 0.08 # Adjust speed here
            if self.alpha < 0.0: self.alpha = 0.0

            try: self.tip_window.attributes("-alpha", self.alpha)
            except: pass

            # Schedule next step
            self.fade_job = self.widget.after(15, self.fade_out)
        else:
            # Animation complete, destroy window
            self.destroy_window()

    def destroy_window(self):
        if self.fade_job: self.widget.after_cancel(self.fade_job)
        if self.tip_window:
            self.tip_window.destroy()
        self.tip_window = None
        self.label = None
        self.alpha = 0.0
        self.fade_job = None

    def refresh(self):
        """Visual pulse when text changes"""
        if not self.tip_window or not self.label: return

        # 1. Update text
        new_text = self.get_text_func()
        self.label.config(text=new_text)
        
        # 2. Quick pulse effect (dim and fade back in)
        if self.fade_job: self.widget.after_cancel(self.fade_job)
        
        # Drop alpha instantly to 50% for the "switch" effect
        self.alpha = 0.5
        try: self.tip_window.attributes("-alpha", self.alpha)
        except: pass
        
        # Start a fast fade back to 100%
        self.fade_in()

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
    def __init__(self, parent, content, command=None, bg="#333333", hover_bg="#4d4d4d", 
                 fg="#ffffff", font=("Segoe UI", 11), width=5, height=2, 
                 repeat=False, repeat_command=None, long_press_command=None):
        
        if isinstance(content, str):
            super().__init__(parent, text=content, bg=bg, fg=fg, font=font, cursor="hand2")
        else:
            super().__init__(parent, image=content, bg=bg, cursor="hand2")
            self.image = content
            
        self.command = command
        self.repeat_command = repeat_command if repeat_command else command 
        self.long_press_command = long_press_command # New Parameter
        
        self.bg_normal = bg
        self.bg_hover = hover_bg
        
        # State flags
        self.repeat = repeat
        self.repeat_job = None
        self.is_long_pressed = False
        self.long_press_job = None
        
        self.bind("<Enter>", self.on_enter)
        self.bind("<Leave>", self.on_leave)
        self.bind("<ButtonPress-1>", self.on_press)
        self.bind("<ButtonRelease-1>", self.on_release)
        
    def on_enter(self, e): self.configure(bg=self.bg_hover)
    def on_leave(self, e): self.configure(bg=self.bg_normal)

    def on_press(self, e):
        self.configure(bg="#0078d4")
        self.is_long_pressed = False
        
        # Case 1: Repeat Mode (Volume/Back/Enter) - Fires immediately and loops
        if self.repeat:
            if self.command: self.command()
            if self.repeat_job: self.after_cancel(self.repeat_job)
            self.repeat_job = self.after(300, self.do_repeat)
            return

        # Case 2: Long Press Mode (Letters) - Waits 400ms to decide
        if self.long_press_command:
            self.long_press_job = self.after(400, self.do_long_press)
            return

        # Case 3: Standard Click - Fires immediately
        if self.command:
            self.command()

    def do_repeat(self):
        if self.repeat_command:
            self.repeat_command()
            self.repeat_job = self.after(100, self.do_repeat)

    def do_long_press(self):
        self.is_long_pressed = True
        if self.long_press_command:
            self.long_press_command()
            self.configure(bg="#005a9e") # Visual cue for long press

    def on_release(self, e):
        self.configure(bg=self.bg_hover)
        
        # Cleanup Repeat
        if self.repeat_job:
            self.after_cancel(self.repeat_job)
            self.repeat_job = None
            
        # Cleanup Long Press
        if self.long_press_job:
            self.after_cancel(self.long_press_job)
            self.long_press_job = None
            
        # If it was a letter key and we released BEFORE the long press triggered:
        # It counts as a normal Tap.
        if self.long_press_command and not self.is_long_pressed:
            if self.command: self.command()
# ==========================================
#           MAIN APPLICATION
# ==========================================

CONFIG_FILE = "floatpad_config.json"
DEFAULT_WIDTH = 300
DEFAULT_HEIGHT = 360
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

class MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT), ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]

def apply_rounded_corners(hwnd):
    try: dwmapi.DwmSetWindowAttribute(hwnd, 33, ctypes.byref(ctypes.c_int(2)), 4)
    except: pass

class App:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("FloatPad")
        self.root.configure(bg=BG_COLOR)
        self.audio_switcher = AudioSwitcher()
        
        self.is_docked = False
        self.is_animating = False
        self.last_interaction = time.time()
        self.emoji_panel_open_time = 0
        self.ignore_next_keypress = False
        self.docking_paused = False
        self.drag_start_x = 0
        self.drag_start_y = 0
        self.is_keyboard_view = False
        self.shift_active = False
        self.caps_active = False
        self.letter_buttons = []
        self.settings = self.load_config()
        # --- MEMORY FOR WINDOW SIZES ---
        # Get the current start size from settings or default
        start_geo = self.settings.get("geometry", f"{DEFAULT_WIDTH}x{DEFAULT_HEIGHT}+500+200")
        try:
            # Extract just the "WxH" part (e.g., "300x460")
            self.numpad_wh = start_geo.split('+')[0] 
        except:
            self.numpad_wh = f"{DEFAULT_WIDTH}x{DEFAULT_HEIGHT}"
            
        self.keyboard_wh = "480x460" # Default starting size for keyboard
        # Load settings
        self.timeout = self.settings.get("timeout", 5)
        self.hide_on_type = self.settings.get("hide_on_type", True) 
        self.always_default_dock = self.settings.get("always_default_dock", False)
        
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

    def open_emoji_panel(self, event=None):
        self.last_interaction = time.time()
        
        # --- NEW: Set the timestamp ---
        self.emoji_panel_open_time = time.time()
        # ------------------------------
        
        try:
            keyboard.send('windows+.') 
        except:
            try: pyautogui.hotkey('win', '.')
            except: pass

    def timer_loop(self):
        while not self.stop_threads:
            if self.root.state() == 'withdrawn':
                time.sleep(1)
                continue
            
            # ... (Pointer check logic stays same) ...
            try:
                mx, my = self.root.winfo_pointerxy()
                wx, wy = self.root.winfo_rootx(), self.root.winfo_rooty()
                ww, wh = self.root.winfo_width(), self.root.winfo_height()
                if wx <= mx <= wx+ww and wy <= my <= wy+wh:
                    self.last_interaction = time.time()
            except: pass
            
            # --- UPDATED DOCKING LOGIC ---
            # Calculate time since last interaction
            time_since_interaction = time.time() - self.last_interaction
            # Calculate time since emoji panel opened
            time_since_emoji = time.time() - self.emoji_panel_open_time
            
            # DOCK ONLY IF:
            # 1. Not already docked
            # 2. User hasn't touched FloatPad for 'timeout' seconds
            # 3. AND Emoji panel wasn't opened in the last 15 seconds
            if not self.is_docked and time_since_interaction > self.timeout:
                if time_since_emoji > 15: # Grace period
                    if self.timeout < 9000: self.root.after(0, self.dock_window)
            
            time.sleep(0.5)


    def set_no_focus(self):
        try:
            hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id())
            style = ctypes.windll.user32.GetWindowLongW(hwnd, -20)
            ctypes.windll.user32.SetWindowLongW(hwnd, -20, style | 0x08000000 | 0x00000008)
        except: pass

    def refresh_visuals(self):
        try:
            hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id())
            apply_rounded_corners(hwnd)

            # --- NEW: Re-apply No Focus style aggressively ---
            # This ensures clicking the window doesn't steal focus from Emoji Panel
            style = ctypes.windll.user32.GetWindowLongW(hwnd, -20)
            ctypes.windll.user32.SetWindowLongW(hwnd, -20, style | 0x08000000 | 0x00000008)
            # -------------------------------------------------

            self.root.configure(bg=BG_COLOR)
        except: pass
    
    def update_preferences(self):
        self.hide_on_type = self.hide_on_type_var.get()
        self.always_default_dock = self.always_default_dock_var.get()
        self.save_config()

    def setup_ui(self):
        self.main_frame = tk.Frame(self.root, bg=BG_COLOR)
        self.main_frame.pack(fill="both", expand=True)
        
        # 1. Title Bar
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

        # --- STEP 1: LOAD IMAGES FIRST (CRITICAL FIX) ---
        try:
            def load_and_process(path, size=(22, 22)):
                """ Load image, handle dev/exe paths, invert color for dark mode """
                # 1. Determine where the app is running
                if getattr(sys, 'frozen', False):
                    base_path = os.path.dirname(sys.executable)
                else:
                    base_path = os.path.dirname(os.path.abspath(__file__))
                
                full_path = os.path.join(base_path, path)

                if not os.path.exists(full_path):
                    # print(f"MISSING: {full_path}")
                    return None
                
                try:
                    img = Image.open(full_path)
                    if img.mode == 'RGBA':
                        r, g, b, a = img.split()
                        rgb = Image.merge('RGB', (r,g,b))
                        inverted = ImageOps.invert(rgb)
                        r2, g2, b2 = inverted.split()
                        img = Image.merge('RGBA', (r2, g2, b2, a))
                    else:
                        img = ImageOps.invert(img.convert('RGB'))
                    img = img.resize(size, Image.Resampling.LANCZOS)
                    return ImageTk.PhotoImage(img)
                except Exception as e:
                    return None

            # Media Icons
            self.play_icon_img = load_and_process("icon/play.png")
            self.pause_icon_img = load_and_process("icon/pause.png")
            self.vol_down_img = load_and_process("icon/volumedown.png")
            self.vol_up_img = load_and_process("icon/volumeup.png")
            self.headphone_img = load_and_process("icon/headphone.png")
            
            # Key Icons
            self.backspace_img = load_and_process("icon/backspace.png")
            self.enter_img = load_and_process("icon/enter.png")
            
            # Toggle & UI Icons (Custom Size 24x24)
            self.keyboard_icon = load_and_process("icon/keyboard.png")
            self.numpad_icon = load_and_process("icon/numpad.png")
            self.emoji_icon = load_and_process("icon/emoji.png")
            
            # Space & Shift
            self.space_icon = load_and_process("icon/space.png") 
            self.shift_off_icon = load_and_process("icon/shift_dark.png")
            self.shift_on_icon = load_and_process("icon/shift_light.png")

        except Exception as e:
            # Fallbacks in case of error
            self.play_icon_img = "⏯"
            self.pause_icon_img = "⏯"
            self.vol_down_img = "🔉"
            self.vol_up_img = "🔊"
            self.headphone_img = "🎧"
            self.backspace_img = "⌫"
            self.enter_img = "⏎"
            self.keyboard_icon = "⌨"
            self.numpad_icon = "🔢"
            self.emoji_icon = "☺"
            self.space_icon = "Space"
            self.shift_off_icon = "⇧"
            self.shift_on_icon = "⬆"
        # --------------------------------------------------

        # 2. Bottom Bar (Now safe to create because images are loaded)
        self.bottom_bar = tk.Frame(self.main_frame, bg=BG_COLOR)
        self.bottom_bar.pack(side="bottom", fill="x", padx=5, pady=5)

        # A. Resize Grip
        grip = tk.Label(self.bottom_bar, text="◢", bg=BG_COLOR, fg="#444444", cursor="sizing", font=("Arial", 8))
        grip.pack(side="right", anchor="se")
        grip.bind("<ButtonPress-1>", self.start_resize)
        grip.bind("<B1-Motion>", self.do_resize)
        grip.bind("<ButtonRelease-1>", self.stop_resize)

        # B. Emoji Button (Safe now!)
        emoji_content = self.emoji_icon if isinstance(self.emoji_icon, tk.PhotoImage) else "☺"
        self.emoji_btn = tk.Label(self.bottom_bar, 
                                  image=emoji_content if isinstance(emoji_content, tk.PhotoImage) else None,
                                  text=emoji_content if isinstance(emoji_content, str) else "",
                                  bg=BG_COLOR, fg="#666666", cursor="hand2", font=("Segoe UI", 14))
        
        if isinstance(emoji_content, tk.PhotoImage):
             self.emoji_btn.image = emoji_content 
             
        self.emoji_btn.pack(side="left", padx=(5, 0))
        self.emoji_btn.bind("<Button-1>", self.open_emoji_panel)
        # Add hover effects
        self.emoji_btn.bind("<Enter>", lambda e: self.emoji_btn.config(bg="#3e3e42"))
        self.emoji_btn.bind("<Leave>", lambda e: self.emoji_btn.config(bg=BG_COLOR))
        
        ToolTip(self.emoji_btn, lambda: "Windows Emoji Panel")

        # C. Toggle Button
        toggle_content = self.keyboard_icon if isinstance(self.keyboard_icon, tk.PhotoImage) else "⌨"
        self.toggle_btn = tk.Label(self.bottom_bar, 
                                   image=toggle_content if isinstance(toggle_content, tk.PhotoImage) else None,
                                   text=toggle_content if isinstance(toggle_content, str) else "",
                                   bg=BG_COLOR, fg="#666666", cursor="hand2", font=("Segoe UI", 14))
                                   
        if isinstance(toggle_content, tk.PhotoImage):
             self.toggle_btn.image = toggle_content
             
        self.toggle_btn.pack(side="left", expand=True, anchor="center") 
        self.toggle_btn.bind("<Button-1>", self.toggle_input_view)
        # Add hover effects
        self.toggle_btn.bind("<Enter>", lambda e: self.toggle_btn.config(bg="#3e3e42"))
        self.toggle_btn.bind("<Leave>", lambda e: self.toggle_btn.config(bg=BG_COLOR))

        # 3. Content Area
        content = tk.Frame(self.main_frame, bg=BG_COLOR)
        content.pack(expand=True, fill="both", padx=8, pady=5)

        self.media_frame = tk.Frame(content, bg=BG_COLOR)
        self.media_frame.pack(fill="x", pady=(0, 10))
        self.media_frame.bind("<MouseWheel>", self.on_mouse_scroll)

        self.is_playing = False 

        def toggle_media():
            self.virtual_key_action('playpause')
            self.is_playing = not self.is_playing
            new_img = self.pause_icon_img if self.is_playing else self.play_icon_img
            if hasattr(self, 'play_btn'):
                self.play_btn.configure(image=new_img)
                self.play_btn.image = new_img
                if hasattr(self, 'play_tooltip'): self.play_tooltip.refresh()

        media_items = [
            (self.vol_down_img, lambda: self.virtual_key_action('volumedown'), "Volume/Scroll Down", True), 
            (self.play_icon_img, toggle_media, None, False), 
            (self.vol_up_img, lambda: self.virtual_key_action('volumeup'), "Volume/Scroll Up", True),
            (self.headphone_img, self.show_audio_menu, "Audio Devices", False)
        ]
        
        for i, (content_item, cmd, tip_text, can_repeat) in enumerate(media_items):
            btn = ModernButton(self.media_frame, content=content_item, command=cmd, 
                               bg="#2b2b2b", hover_bg="#3e3e42", font=("Segoe UI", 12),
                               repeat=can_repeat) 
            btn.grid(row=0, column=i, sticky="nsew", padx=2)
            self.media_frame.grid_columnconfigure(i, weight=1)
            btn.bind("<MouseWheel>", self.on_mouse_scroll)
            
            if content_item == self.headphone_img: self.audio_btn_widget = btn
            elif content_item == self.play_icon_img: self.play_btn = btn

            if tip_text:
                ToolTip(btn, lambda t=tip_text: t)

        # Keyboard Container
        self.keys_container = tk.Frame(content, bg=BG_COLOR)
        self.keys_container.pack(expand=True, fill="both")
        
        # Build Initial View
        self.build_numpad()

        def get_play_btn_text():
            return "Pause" if self.is_playing else "Play"
        if hasattr(self, 'play_btn'):
            self.play_tooltip = ToolTip(self.play_btn, get_play_btn_text)
            
        self.root.bind("<MouseWheel>", self.on_mouse_scroll)
        self.root.bind("<Button-2>", self.on_middle_click)
    
    
    def toggle_input_view(self, event=None):
        # 1. SAVE CURRENT SIZE
        current_geo = self.root.geometry()
        current_wh = current_geo.split('+')[0] 
        
        if self.is_keyboard_view:
            self.keyboard_wh = current_wh
        else:
            self.numpad_wh = current_wh

        # 2. SWITCH STATE
        self.is_keyboard_view = not self.is_keyboard_view
        
        # 3. CLEAR UI
        # 3. CLEAR OLD BUTTONS
        for widget in self.keys_container.winfo_children():
            widget.destroy()
            
        if self.is_keyboard_view:
            # --- SWITCHING TO KEYBOARD ---
            self.shift_active = True 
            self.caps_active = False
            self.build_alpha_keyboard()
            
            # FIX: Show "Numpad" icon (because clicking it goes to Numpad)
            if isinstance(self.numpad_icon, tk.PhotoImage):
                self.toggle_btn.configure(image=self.numpad_icon, text="")
                self.toggle_btn.image = self.numpad_icon
            else:
                self.toggle_btn.configure(image="", text="🔢")
                
            target_str = self.keyboard_wh
        else:
            # --- SWITCHING TO NUMPAD ---
            self.build_numpad()
            
            # FIX: Show "Keyboard" icon (because clicking it goes to Keyboard)
            if isinstance(self.keyboard_icon, tk.PhotoImage):
                self.toggle_btn.configure(image=self.keyboard_icon, text="")
                self.toggle_btn.image = self.keyboard_icon
            else:
                self.toggle_btn.configure(image="", text="⌨")
                
            target_str = self.numpad_wh
            
        # 4. PREPARE TARGET DIMENSIONS
        target_str = ""
        if self.is_keyboard_view:
            # Switching TO Keyboard
            self.shift_active = True 
            self.caps_active = False
            self.build_alpha_keyboard()
            # Switch icon to NUMPAD (to indicate "Click to go back")
            if isinstance(self.numpad_icon, tk.PhotoImage):
                self.toggle_btn.configure(image=self.numpad_icon, text="")
                self.toggle_btn.image = self.numpad_icon
            else:
                self.toggle_btn.configure(image="", text="🔢")
            target_str = self.keyboard_wh
        else:
            # Switching TO Numpad
            self.build_numpad()
            # Switch icon to KEYBOARD
            if isinstance(self.keyboard_icon, tk.PhotoImage):
                self.toggle_btn.configure(image=self.keyboard_icon, text="")
                self.toggle_btn.image = self.keyboard_icon
            else:
                self.toggle_btn.configure(image="", text="⌨")
            target_str = self.numpad_wh

        # 5. PARSE TARGET AND ANIMATE
        try:
            # target_str is usually "300x460" -> split to [300, 460]
            w, h = map(int, target_str.split('x'))
            self.animate_resize(w, h)
        except:
            # Fallback if parsing fails
            self.root.geometry(target_str)

    # --- NEW: Trigger Windows Emoji Panel ---
    def open_emoji_panel(self, event=None):
        self.last_interaction = time.time()
        self.docking_paused = True
        # "Windows + ." is the standard shortcut for the emoji panel
        try:
            keyboard.send('windows+;') 
        except:
            # Fallback if keyboard module fails
            try: pyautogui.hotkey('win', ';')
            except: pass

    def build_numpad(self):
        # --- FIX 1: RESET GRID WEIGHTS ---
        # Reset the grid so it forgets the 5-column layout of the keyboard
        for i in range(10):
            self.keys_container.grid_columnconfigure(i, weight=0)
            self.keys_container.grid_rowconfigure(i, weight=0)
        # ---------------------------------

        numpad = ['7', '8', '9', '4', '5', '6', '1', '2', '3', 'backspace', '0', 'enter']
        key_content = {
            'backspace': self.backspace_img if self.backspace_img else '⌫',
            'enter': self.enter_img if self.enter_img else '⏎'
        }
        
        for i, key in enumerate(numpad):
            r = i // 3; c = i % 3
            content = key_content.get(key, key)
            
            should_repeat = False
            custom_command = None
            custom_repeat = None
            
            if key == 'enter':
                should_repeat = True
                custom_command = lambda: self.virtual_key_action('enter')
                custom_repeat = lambda: self.virtual_key_action_hotkey('shift', 'enter')
            elif key == 'backspace':
                should_repeat = True
                custom_command = lambda: self.virtual_key_action('backspace')
            else:
                custom_command = lambda k=key: self.virtual_key_action(k)

            btn = ModernButton(self.keys_container, content=content, 
                               command=custom_command,
                               repeat_command=custom_repeat,
                               bg="#252526", hover_bg="#37373d", 
                               font=("Segoe UI", 14), height=2,
                               repeat=should_repeat)
            btn.grid(row=r, column=c, sticky="nsew", padx=2, pady=2)
            
            # --- FIX 2: RE-APPLY WEIGHTS FOR NUMPAD ONLY ---
            # Only give weight to the columns and rows we actually use (3 cols, 4 rows)
            self.keys_container.grid_columnconfigure(c, weight=1)
            self.keys_container.grid_rowconfigure(r, weight=1)

    def build_alpha_keyboard(self):
        self.letter_buttons = [] # Reset list
        
        letters = "abcdefghijklmnopqrstuvwxyz"
        row_idx = 0
        col_idx = 0
        
        for char in letters:
            # Command sends the specific character
            cmd_tap = lambda c=char: self.type_letter(c)
            # Hold sends uppercase forced
            cmd_hold = lambda c=char: self.type_letter(c, force_upper=True)
            
            btn = ModernButton(self.keys_container, content=char, # Initial text doesn't matter, will update
                               command=cmd_tap,
                               long_press_command=cmd_hold,
                               bg="#252526", hover_bg="#37373d", 
                               font=("Segoe UI", 11), height=1)
            
            # Store tuple: (Button Widget, The character 'a')
            self.letter_buttons.append((btn, char)) 
            
            btn.grid(row=row_idx, column=col_idx, sticky="nsew", padx=1, pady=1)
            self.keys_container.grid_columnconfigure(col_idx, weight=1)
            
            col_idx += 1
            if col_idx > 4: # 5 columns
                col_idx = 0
                row_idx += 1
        
        # --- Punctuation ---
        row_idx += 1
        extras = [',', '.', '?', '!', '@']
        for i, char in enumerate(extras):
             btn = ModernButton(self.keys_container, content=char, 
                                command=lambda c=char: self.virtual_key_action_text(c),
                                bg="#252526", hover_bg="#37373d", font=("Segoe UI", 11), height=1)
             btn.grid(row=row_idx, column=i, sticky="nsew", padx=1, pady=1)

        # --- Functional Row ---
        row_idx += 1
        
        # Shift
        # Use shift_off_icon by default
        shift_content = self.shift_off_icon if self.shift_off_icon else "⇧"
        
        self.shift_btn = ModernButton(self.keys_container, content=shift_content, 
                                      command=self.toggle_shift, 
                                      bg="#252526", hover_bg="#37373d", font=("Segoe UI", 10), height=1)
        self.shift_btn.grid(row=row_idx, column=0, sticky="nsew", padx=1, pady=1)

        # Caps
        self.caps_btn = ModernButton(self.keys_container, content="Caps", 
                                     command=self.toggle_caps, 
                                     bg="#252526", hover_bg="#37373d", font=("Segoe UI", 8), height=1)
        self.caps_btn.grid(row=row_idx, column=1, sticky="nsew", padx=1, pady=1)

        # Space
        space_content = self.space_icon if self.space_icon else "Space"
        
        btn_space = ModernButton(self.keys_container, content=space_content, 
                                 command=lambda: self.virtual_key_action('space'),
                                 bg="#252526", hover_bg="#37373d", font=("Segoe UI", 9), height=1)
        btn_space.grid(row=row_idx, column=2, sticky="nsew", padx=1, pady=1)

        # Backspace
        bk_c = self.backspace_img if self.backspace_img else "⌫"
        btn_bk = ModernButton(self.keys_container, content=bk_c, 
                              command=lambda: self.virtual_key_action('backspace'),
                              bg="#252526", hover_bg="#37373d", font=("Segoe UI", 10), height=1, repeat=True)
        btn_bk.grid(row=row_idx, column=3, sticky="nsew", padx=1, pady=1)

        # Enter
        en_c = self.enter_img if self.enter_img else "⏎"
        btn_en = ModernButton(self.keys_container, content=en_c, 
                              command=lambda: self.virtual_key_action('enter'),
                              repeat_command=lambda: self.virtual_key_action_hotkey('shift', 'enter'),
                              bg="#252526", hover_bg="#37373d", font=("Segoe UI", 10), height=1, repeat=True)
        btn_en.grid(row=row_idx, column=4, sticky="nsew", padx=1, pady=1)

        for r in range(row_idx + 1):
            self.keys_container.grid_rowconfigure(r, weight=1)
            
        # APPLY VISUALS IMMEDIATELY
        self.update_keyboard_visuals()

    def update_keyboard_visuals(self):
        # 1. Determine if we are uppercase
        is_upper = self.shift_active or self.caps_active
        
        # 2. Update all letter buttons
        for btn, char in self.letter_buttons:
            text = char.upper() if is_upper else char.lower()
            btn.configure(text=text)
            
        # 3. Update Shift Button Icon (CRITICAL FIX)
        if hasattr(self, 'shift_btn'):
            # Check if image files were successfully loaded
            if isinstance(self.shift_on_icon, tk.PhotoImage) and isinstance(self.shift_off_icon, tk.PhotoImage):
                # Swap the image based on state
                new_img = self.shift_on_icon if self.shift_active else self.shift_off_icon
                self.shift_btn.configure(image=new_img, text="")
                self.shift_btn.image = new_img # Important: Prevent garbage collection
                
                # Reset background to dark since the image likely has its own color
                self.shift_btn.configure(bg="#252526")
                self.shift_btn.bg_normal = "#252526"
            else:
                # Fallback to Text/Color if images missing
                shift_color = "#0078d4" if self.shift_active else "#252526"
                self.shift_btn.configure(bg=shift_color)
                self.shift_btn.bg_normal = shift_color
            
        # 4. Update Caps Button Color (Blue if active)
        caps_color = "#0078d4" if self.caps_active else "#252526"
        if hasattr(self, 'caps_btn'):
            self.caps_btn.configure(bg=caps_color)
            self.caps_btn.bg_normal = caps_color
            
        # 3. Update Shift Button Icon/Color
        if hasattr(self, 'shift_btn'):
            # Check if we have BOTH images loaded
            if isinstance(self.shift_on_icon, tk.PhotoImage) and isinstance(self.shift_off_icon, tk.PhotoImage):
                # IMAGE MODE
                new_img = self.shift_on_icon if self.shift_active else self.shift_off_icon
                self.shift_btn.configure(image=new_img)
                self.shift_btn.image = new_img # Prevent garbage collection
                
                # Reset bg to dark (since the image handles the "active" look)
                self.shift_btn.configure(bg="#252526")
                self.shift_btn.bg_normal = "#252526"
            else:
                # TEXT MODE (Fallback)
                shift_color = "#0078d4" if self.shift_active else "#252526"
                self.shift_btn.configure(bg=shift_color)
                self.shift_btn.bg_normal = shift_color
            
        # 4. Update Caps Button Color (Blue if active)
        caps_color = "#0078d4" if self.caps_active else "#252526"
        if hasattr(self, 'caps_btn'):
            self.caps_btn.configure(bg=caps_color)
            self.caps_btn.bg_normal = caps_color

    def type_letter(self, char, force_upper=False):
        self.last_interaction = time.time()
        
        final_char = char
        
        if force_upper:
            final_char = char.upper()
        else:
            # Logic: If Shift OR Caps is on -> Uppercase
            if self.shift_active or self.caps_active:
                final_char = char.upper()
                
                # Logic: If only Shift was on (not Caps), turn it off after typing 1 letter
                if self.shift_active and not self.caps_active:
                    self.shift_active = False
                    self.update_keyboard_visuals() # Revert to lowercase visuals
            else:
                final_char = char.lower()
        
        try: pyautogui.write(final_char)
        except: pass

    def toggle_shift(self):
        self.shift_active = not self.shift_active
        # If we turn on Shift, usually we turn off Caps to avoid confusion
        if self.shift_active: self.caps_active = False
        self.update_keyboard_visuals()

    def toggle_caps(self):
        self.caps_active = not self.caps_active
        # If we turn on Caps, turn off Shift
        if self.caps_active: self.shift_active = False
        self.update_keyboard_visuals()

    def virtual_key_action_text(self, text):
        self.last_interaction = time.time()
        try: pyautogui.write(text)
        except: pass

    def on_mouse_scroll(self, event):
        """Handle scroll wheel events, restricted to Media Frame"""
        try:
            # 1. Get Mouse Screen Coordinates
            mx, my = self.root.winfo_pointerxy()

            # 2. Get Media Frame Screen Coordinates and Size
            fx = self.media_frame.winfo_rootx()
            fy = self.media_frame.winfo_rooty()
            fw = self.media_frame.winfo_width()
            fh = self.media_frame.winfo_height()

            # 3. Check if Mouse is inside the Media Frame
            if fx <= mx <= fx + fw and fy <= my <= fy + fh:
                self.last_interaction = time.time()
                # Windows sends delta 120 (up) or -120 (down)
                if event.delta > 0:
                    self.virtual_key_action('volumeup')
                else:
                    self.virtual_key_action('volumedown')
        except:
            # Safety pass in case widget isn't ready
            pass

    def on_middle_click(self, event):
        """Scroll button press = Shift+Enter"""
        self.last_interaction = time.time()
        self.virtual_key_action_hotkey('shift', 'enter')

    def setup_dock_ui(self):
        self.dock_frame = tk.Frame(self.root, bg=BG_COLOR, cursor="fleur")
        self.expand_btn = tk.Button(self.dock_frame, text="●", bg=BG_COLOR, fg="#666666", bd=0,
                                    activebackground=BG_COLOR, activeforeground=ACCENT_COLOR,
                                    command=self.undock_window)
        self.expand_btn.pack(expand=True, fill="both")
        self.bind_drag(self.dock_frame)
        self.bind_drag(self.expand_btn)

    def show_audio_menu(self):
        devices = self.audio_switcher.get_devices()
        current = self.audio_switcher.get_current_device_id()
        if not devices: return
        x = self.audio_btn_widget.winfo_rootx()
        y = self.audio_btn_widget.winfo_rooty() + self.audio_btn_widget.winfo_height() + 5
        if y + 150 > self.root.winfo_screenheight(): y = self.audio_btn_widget.winfo_rooty() - 150
        ModernMenu(self.root, x, y, devices, current, self.audio_switcher.set_default_device)

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

    def virtual_key_action_hotkey(self, mod, key):
        self.last_interaction = time.time()
        self.ignore_next_keypress = True 
        try: pyautogui.hotkey(mod, key)
        except: pass
        self.root.after(100, lambda: setattr(self, 'ignore_next_keypress', False))

    def timer_loop(self):
        while not self.stop_threads:
            if self.root.state() == 'withdrawn':
                time.sleep(1)
                continue
            
            try:
                mx, my = self.root.winfo_pointerxy()
                wx, wy = self.root.winfo_rootx(), self.root.winfo_rooty()
                ww, wh = self.root.winfo_width(), self.root.winfo_height()
                
                # Check if mouse is INSIDE the FloatPad
                if wx <= mx <= wx+ww and wy <= my <= wy+wh:
                    self.last_interaction = time.time()
                    # --- NEW: User returned! Unpause the docking ---
                    self.docking_paused = False
                    # -----------------------------------------------
            except: pass
            
            # --- UPDATED DOCKING CONDITION ---
            # Only dock if:
            # 1. Not already docked
            # 2. Time is up
            # 3. AND we are NOT paused (waiting for emoji)
            if not self.is_docked and (time.time() - self.last_interaction > self.timeout):
                if not self.docking_paused:
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

    # --- NEW: SMOOTH RESIZE ANIMATION ---
    def animate_resize(self, target_w, target_h):
        # 1. Get current size and position
        cur_w = self.root.winfo_width()
        cur_h = self.root.winfo_height()
        cur_x = self.root.winfo_x()
        cur_y = self.root.winfo_y()

        # 2. Setup Animation Steps
        steps = 15  # Total frames (higher = slower/smoother)
        dt = 10     # Time per frame in ms

        def _step(i):
            # Calculate progress (0.0 to 1.0)
            progress = i / steps
            
            # Optional: "Ease Out" math makes it start fast and end slow (feels robotic without it)
            ease = 1 - (1 - progress) ** 2 

            # Calculate new size based on progress
            new_w = int(cur_w + (target_w - cur_w) * ease)
            new_h = int(cur_h + (target_h - cur_h) * ease)

            # Apply geometry
            self.root.geometry(f"{new_w}x{new_h}+{cur_x}+{cur_y}")

            if i < steps:
                # Schedule next frame
                self.root.after(dt, lambda: _step(i + 1))
            else:
                # Ensure we hit the exact target at the end
                self.root.geometry(f"{target_w}x{target_h}+{cur_x}+{cur_y}")

        # Start animation
        _step(0) 
    
    def animate(self, s_geo, e_geo):
        def parse(g): return [int(x) for x in g.replace('+','x').split('x') if x]
        try:
            sw, sh, sx, sy = parse(s_geo)
            ew, eh, ex, ey = parse(e_geo)
        except: return
        steps = 12
        def step(i):
            if i > steps: self.root.geometry(e_geo); return
            t = i/steps
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
            "hide_on_type": self.hide_on_type,
            "always_default_dock": self.always_default_dock,
            "last_dock_geo": self.last_dock_geo
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

if __name__ == "__main__":
    app = App()
    try:
        app.root.mainloop()
    except KeyboardInterrupt:
        app.quit_app()