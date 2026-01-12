import tkinter as tk
import pyautogui
import threading
import time
import os
import ctypes
import keyboard 
from pystray import Icon as TrayIcon, Menu as TrayMenu, MenuItem as TrayItem
from PIL import Image, ImageDraw, ImageTk, ImageOps

# --- Custom Module Imports ---
import config
from window_utils import resource_path, apply_rounded_corners, set_no_focus, get_monitor_info
from audio_manager import AudioSwitcher
from ui_components import ModernButton, ModernMenu, ToolTip

class App:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("FloatPad")
        self.root.configure(bg=config.BG_COLOR)
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
        self.settings = config.load_config()
        
        # --- MEMORY FOR WINDOW SIZES ---
        start_geo = self.settings.get("geometry", f"{config.DEFAULT_WIDTH}x{config.DEFAULT_HEIGHT}+500+200")
        try:
            self.numpad_wh = start_geo.split('+')[0] 
        except:
            self.numpad_wh = f"{config.DEFAULT_WIDTH}x{config.DEFAULT_HEIGHT}"
            
        self.keyboard_wh = "480x460" 
        self.timeout = self.settings.get("timeout", 5)
        self.hide_on_type = self.settings.get("hide_on_type", True) 
        self.always_default_dock = self.settings.get("always_default_dock", False)
        self.last_dock_geo = self.settings.get("last_dock_geo", None)
        
        if "1x1" in start_geo: start_geo = f"{config.DEFAULT_WIDTH}x{config.DEFAULT_HEIGHT}+500+200"
        self.root.geometry(start_geo)
        self.saved_geometry = start_geo

        self.root.overrideredirect(True)
        self.root.wm_attributes("-topmost", True)
        self.root.update_idletasks()
        
        self.refresh_visuals()
        self.setup_ui()
        self.setup_dock_ui()
        self.setup_context_menu()
        
        self.root.after(100, self.dock_window)
        self.stop_threads = False
        
        try: keyboard.on_press(self.on_physical_keypress)
        except: pass

        threading.Thread(target=self.timer_loop, daemon=True).start()
        threading.Thread(target=self.setup_tray, daemon=True).start()

    def set_no_focus(self):
        hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id())
        set_no_focus(hwnd)

    def refresh_visuals(self):
        hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id())
        apply_rounded_corners(hwnd)
        set_no_focus(hwnd)
        self.root.configure(bg=config.BG_COLOR)
    
    def update_preferences(self):
        self.hide_on_type = self.hide_on_type_var.get()
        self.always_default_dock = self.always_default_dock_var.get()
        self.save_config()

    def setup_ui(self):
        self.main_frame = tk.Frame(self.root, bg=config.BG_COLOR)
        self.main_frame.pack(fill="both", expand=True)
        
        # 1. Title Bar
        self.title_bar = tk.Frame(self.main_frame, bg=config.TITLE_BG, height=32)
        self.title_bar.pack(fill='x', side='top', pady=0)
        self.title_bar.pack_propagate(False)
        
        title = tk.Label(self.title_bar, text="FloatPad", bg=config.TITLE_BG, fg="#888888", font=("Segoe UI", 9))
        title.pack(side="left", padx=10)
        self.bind_drag(title)
        self.bind_drag(self.title_bar)

        close_btn = tk.Label(self.title_bar, text="✕", bg=config.TITLE_BG, fg="#aaaaaa", font=("Arial", 9), cursor="hand2")
        close_btn.pack(side="right", padx=10, fill='y')
        close_btn.bind("<Button-1>", lambda e: self.dock_window())
        close_btn.bind("<Enter>", lambda e: close_btn.config(fg="white"))
        close_btn.bind("<Leave>", lambda e: close_btn.config(fg="#aaaaaa"))

        # --- STEP 1: LOAD IMAGES ---
        try:
            def load_and_process(path, size=(22, 22)):
                full_path = resource_path(path)
                if not os.path.exists(full_path): return None
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
                except: return None

            self.play_icon_img = load_and_process("icon/play.png")
            self.pause_icon_img = load_and_process("icon/pause.png")
            self.vol_down_img = load_and_process("icon/volumedown.png")
            self.vol_up_img = load_and_process("icon/volumeup.png")
            self.headphone_img = load_and_process("icon/headphone.png")
            self.backspace_img = load_and_process("icon/backspace.png")
            self.enter_img = load_and_process("icon/enter.png")
            self.keyboard_icon = load_and_process("icon/keyboard.png")
            self.numpad_icon = load_and_process("icon/numpad.png")
            self.emoji_icon = load_and_process("icon/emoji.png")
            self.space_icon = load_and_process("icon/space.png") 
            self.shift_off_icon = load_and_process("icon/shift_dark.png")
            self.shift_on_icon = load_and_process("icon/shift_light.png")

        except Exception:
            self.play_icon_img = "⏯"; self.pause_icon_img = "⏯"
            self.vol_down_img = "🔉"; self.vol_up_img = "🔊"; self.headphone_img = "🎧"
            self.backspace_img = "⌫"; self.enter_img = "⏎"
            self.keyboard_icon = "⌨"; self.numpad_icon = "🔢"; self.emoji_icon = "☺"
            self.space_icon = "Space"; self.shift_off_icon = "⇧"; self.shift_on_icon = "⬆"

        # 2. Bottom Bar
        self.bottom_bar = tk.Frame(self.main_frame, bg=config.BG_COLOR)
        self.bottom_bar.pack(side="bottom", fill="x", padx=5, pady=5)

        grip = tk.Label(self.bottom_bar, text="◢", bg=config.BG_COLOR, fg="#444444", cursor="sizing", font=("Arial", 8))
        grip.pack(side="right", anchor="se")
        grip.bind("<ButtonPress-1>", self.start_resize)
        grip.bind("<B1-Motion>", self.do_resize)
        grip.bind("<ButtonRelease-1>", self.stop_resize)

        emoji_content = self.emoji_icon if isinstance(self.emoji_icon, tk.PhotoImage) else "☺"
        self.emoji_btn = tk.Label(self.bottom_bar, 
                                  image=emoji_content if isinstance(emoji_content, tk.PhotoImage) else None,
                                  text=emoji_content if isinstance(emoji_content, str) else "",
                                  bg=config.BG_COLOR, fg="#666666", cursor="hand2", font=("Segoe UI", 14))
        if isinstance(emoji_content, tk.PhotoImage): self.emoji_btn.image = emoji_content 
        self.emoji_btn.pack(side="left", padx=(5, 0))
        self.emoji_btn.bind("<Button-1>", self.open_emoji_panel)
        self.emoji_btn.bind("<Enter>", lambda e: self.emoji_btn.config(bg="#3e3e42"))
        self.emoji_btn.bind("<Leave>", lambda e: self.emoji_btn.config(bg=config.BG_COLOR))
        ToolTip(self.emoji_btn, lambda: "Windows Emoji Panel")

        toggle_content = self.keyboard_icon if isinstance(self.keyboard_icon, tk.PhotoImage) else "⌨"
        self.toggle_btn = tk.Label(self.bottom_bar, 
                                   image=toggle_content if isinstance(toggle_content, tk.PhotoImage) else None,
                                   text=toggle_content if isinstance(toggle_content, str) else "",
                                   bg=config.BG_COLOR, fg="#666666", cursor="hand2", font=("Segoe UI", 14))
        if isinstance(toggle_content, tk.PhotoImage): self.toggle_btn.image = toggle_content
        self.toggle_btn.pack(side="left", expand=True, anchor="center") 
        self.toggle_btn.bind("<Button-1>", self.toggle_input_view)
        self.toggle_btn.bind("<Enter>", lambda e: self.toggle_btn.config(bg="#3e3e42"))
        self.toggle_btn.bind("<Leave>", lambda e: self.toggle_btn.config(bg=config.BG_COLOR))

        # 3. Content Area
        content = tk.Frame(self.main_frame, bg=config.BG_COLOR)
        content.pack(expand=True, fill="both", padx=8, pady=5)

        self.media_frame = tk.Frame(content, bg=config.BG_COLOR)
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
            if tip_text: ToolTip(btn, lambda t=tip_text: t)

        self.keys_container = tk.Frame(content, bg=config.BG_COLOR)
        self.keys_container.pack(expand=True, fill="both")
        self.build_numpad()

        def get_play_btn_text(): return "Pause" if self.is_playing else "Play"
        if hasattr(self, 'play_btn'): self.play_tooltip = ToolTip(self.play_btn, get_play_btn_text)
        self.root.bind("<MouseWheel>", self.on_mouse_scroll)
        self.root.bind("<Button-2>", self.on_middle_click)
    
    def toggle_input_view(self, event=None):
        current_geo = self.root.geometry()
        current_wh = current_geo.split('+')[0] 
        if self.is_keyboard_view: self.keyboard_wh = current_wh
        else: self.numpad_wh = current_wh
        self.is_keyboard_view = not self.is_keyboard_view
        for widget in self.keys_container.winfo_children(): widget.destroy()
            
        if self.is_keyboard_view:
            self.shift_active = True 
            self.caps_active = False
            self.build_alpha_keyboard()
            if isinstance(self.numpad_icon, tk.PhotoImage):
                self.toggle_btn.configure(image=self.numpad_icon, text=""); self.toggle_btn.image = self.numpad_icon
            else: self.toggle_btn.configure(image="", text="🔢")
            target_str = self.keyboard_wh
        else:
            self.build_numpad()
            if isinstance(self.keyboard_icon, tk.PhotoImage):
                self.toggle_btn.configure(image=self.keyboard_icon, text=""); self.toggle_btn.image = self.keyboard_icon
            else: self.toggle_btn.configure(image="", text="⌨")
            target_str = self.numpad_wh

        try:
            w, h = map(int, target_str.split('x'))
            self.animate_resize(w, h)
        except: self.root.geometry(target_str)

    def open_emoji_panel(self, event=None):
        self.last_interaction = time.time()
        self.emoji_panel_open_time = time.time()
        self.docking_paused = True
        try: keyboard.send('windows+;') 
        except: 
            try: pyautogui.hotkey('win', ';')
            except: pass

    def build_numpad(self):
        for i in range(10):
            self.keys_container.grid_columnconfigure(i, weight=0)
            self.keys_container.grid_rowconfigure(i, weight=0)

        numpad = ['7', '8', '9', '4', '5', '6', '1', '2', '3', 'backspace', '0', 'enter']
        key_content = {
            'backspace': self.backspace_img if self.backspace_img else '⌫',
            'enter': self.enter_img if self.enter_img else '⏎'
        }
        for i, key in enumerate(numpad):
            r = i // 3; c = i % 3
            content = key_content.get(key, key)
            should_repeat = False
            custom_command = None; custom_repeat = None
            if key == 'enter':
                should_repeat = True
                custom_command = lambda: self.virtual_key_action('enter')
                custom_repeat = lambda: self.virtual_key_action_hotkey('shift', 'enter')
            elif key == 'backspace':
                should_repeat = True
                custom_command = lambda: self.virtual_key_action('backspace')
            else:
                custom_command = lambda k=key: self.virtual_key_action(k)

            btn = ModernButton(self.keys_container, content=content, command=custom_command,
                               repeat_command=custom_repeat, bg="#252526", hover_bg="#37373d", 
                               font=("Segoe UI", 14), height=2, repeat=should_repeat)
            btn.grid(row=r, column=c, sticky="nsew", padx=2, pady=2)
            self.keys_container.grid_columnconfigure(c, weight=1)
            self.keys_container.grid_rowconfigure(r, weight=1)

    def build_alpha_keyboard(self):
        self.letter_buttons = []
        letters = "abcdefghijklmnopqrstuvwxyz"
        row_idx = 0; col_idx = 0
        for char in letters:
            cmd_tap = lambda c=char: self.type_letter(c)
            cmd_hold = lambda c=char: self.type_letter(c, force_upper=True)
            btn = ModernButton(self.keys_container, content=char, command=cmd_tap,
                               long_press_command=cmd_hold, bg="#252526", hover_bg="#37373d", 
                               font=("Segoe UI", 11), height=1)
            self.letter_buttons.append((btn, char)) 
            btn.grid(row=row_idx, column=col_idx, sticky="nsew", padx=1, pady=1)
            self.keys_container.grid_columnconfigure(col_idx, weight=1)
            col_idx += 1
            if col_idx > 4: 
                col_idx = 0; row_idx += 1
        
        row_idx += 1
        extras = [',', '.', '?', '!', '@']
        for i, char in enumerate(extras):
             btn = ModernButton(self.keys_container, content=char, command=lambda c=char: self.virtual_key_action_text(c),
                                bg="#252526", hover_bg="#37373d", font=("Segoe UI", 11), height=1)
             btn.grid(row=row_idx, column=i, sticky="nsew", padx=1, pady=1)

        row_idx += 1
        shift_content = self.shift_off_icon if self.shift_off_icon else "⇧"
        self.shift_btn = ModernButton(self.keys_container, content=shift_content, command=self.toggle_shift, 
                                      bg="#252526", hover_bg="#37373d", font=("Segoe UI", 10), height=1)
        self.shift_btn.grid(row=row_idx, column=0, sticky="nsew", padx=1, pady=1)

        self.caps_btn = ModernButton(self.keys_container, content="Caps", command=self.toggle_caps, 
                                     bg="#252526", hover_bg="#37373d", font=("Segoe UI", 8), height=1)
        self.caps_btn.grid(row=row_idx, column=1, sticky="nsew", padx=1, pady=1)

        space_content = self.space_icon if self.space_icon else "Space"
        btn_space = ModernButton(self.keys_container, content=space_content, command=lambda: self.virtual_key_action('space'),
                                 bg="#252526", hover_bg="#37373d", font=("Segoe UI", 9), height=1)
        btn_space.grid(row=row_idx, column=2, sticky="nsew", padx=1, pady=1)

        bk_c = self.backspace_img if self.backspace_img else "⌫"
        btn_bk = ModernButton(self.keys_container, content=bk_c, command=lambda: self.virtual_key_action('backspace'),
                              bg="#252526", hover_bg="#37373d", font=("Segoe UI", 10), height=1, repeat=True)
        btn_bk.grid(row=row_idx, column=3, sticky="nsew", padx=1, pady=1)

        en_c = self.enter_img if self.enter_img else "⏎"
        btn_en = ModernButton(self.keys_container, content=en_c, command=lambda: self.virtual_key_action('enter'),
                              repeat_command=lambda: self.virtual_key_action_hotkey('shift', 'enter'),
                              bg="#252526", hover_bg="#37373d", font=("Segoe UI", 10), height=1, repeat=True)
        btn_en.grid(row=row_idx, column=4, sticky="nsew", padx=1, pady=1)

        for r in range(row_idx + 1): self.keys_container.grid_rowconfigure(r, weight=1)
        self.update_keyboard_visuals()

    def update_keyboard_visuals(self):
        is_upper = self.shift_active or self.caps_active
        for btn, char in self.letter_buttons:
            text = char.upper() if is_upper else char.lower()
            btn.configure(text=text)
            
        if hasattr(self, 'shift_btn'):
            if isinstance(self.shift_on_icon, tk.PhotoImage) and isinstance(self.shift_off_icon, tk.PhotoImage):
                new_img = self.shift_on_icon if self.shift_active else self.shift_off_icon
                self.shift_btn.configure(image=new_img, text="", bg="#252526"); self.shift_btn.image = new_img
            else:
                shift_color = config.ACCENT_COLOR if self.shift_active else "#252526"
                self.shift_btn.configure(bg=shift_color)
            
        caps_color = config.ACCENT_COLOR if self.caps_active else "#252526"
        if hasattr(self, 'caps_btn'): self.caps_btn.configure(bg=caps_color)

    def type_letter(self, char, force_upper=False):
        self.last_interaction = time.time()
        final_char = char
        if force_upper: final_char = char.upper()
        else:
            if self.shift_active or self.caps_active:
                final_char = char.upper()
                if self.shift_active and not self.caps_active:
                    self.shift_active = False
                    self.update_keyboard_visuals()
            else: final_char = char.lower()
        try: pyautogui.write(final_char)
        except: pass

    def toggle_shift(self):
        self.shift_active = not self.shift_active
        if self.shift_active: self.caps_active = False
        self.update_keyboard_visuals()

    def toggle_caps(self):
        self.caps_active = not self.caps_active
        if self.caps_active: self.shift_active = False
        self.update_keyboard_visuals()

    def virtual_key_action_text(self, text):
        self.last_interaction = time.time()
        try: pyautogui.write(text)
        except: pass

    def on_mouse_scroll(self, event):
        try:
            mx, my = self.root.winfo_pointerxy()
            fx = self.media_frame.winfo_rootx(); fy = self.media_frame.winfo_rooty()
            fw = self.media_frame.winfo_width(); fh = self.media_frame.winfo_height()
            if fx <= mx <= fx + fw and fy <= my <= fy + fh:
                self.last_interaction = time.time()
                if event.delta > 0: self.virtual_key_action('volumeup')
                else: self.virtual_key_action('volumedown')
        except: pass

    def on_middle_click(self, event):
        self.last_interaction = time.time()
        self.virtual_key_action_hotkey('shift', 'enter')

    def setup_dock_ui(self):
        self.dock_frame = tk.Frame(self.root, bg=config.BG_COLOR, cursor="fleur")
        self.expand_btn = tk.Button(self.dock_frame, text="●", bg=config.BG_COLOR, fg="#666666", bd=0,
                                    activebackground=config.BG_COLOR, activeforeground=config.ACCENT_COLOR,
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
                if wx <= mx <= wx+ww and wy <= my <= wy+wh:
                    self.last_interaction = time.time()
                    self.docking_paused = False
            except: pass
            
            time_since_interaction = time.time() - self.last_interaction
            time_since_emoji = time.time() - self.emoji_panel_open_time
            if not self.is_docked and time_since_interaction > self.timeout:
                if time_since_emoji > 15: 
                    if self.timeout < 9000: self.root.after(0, self.dock_window)
            time.sleep(0.5)

    def dock_window(self, animate=True):
        if not self.is_docked:
            if self.root.winfo_width() > 100: self.saved_geometry = self.root.geometry()
        mon = get_monitor_info(self.root.winfo_id())
        if not mon: mon = {'l': 0, 't': 0, 'r': self.root.winfo_screenwidth(), 'b': self.root.winfo_screenheight()}
        
        if self.always_default_dock:
            target_x = mon['l'] + 100; target_y = mon['t']; mode = 'top'
        elif self.last_dock_geo:
            if animate: return self.animate_to_dock_string(self.last_dock_geo)
            else:
                self.is_docked = True
                self.main_frame.pack_forget(); self.dock_frame.pack(fill='both', expand=True)
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
        self.is_docked = True
        self.main_frame.pack_forget()
        self.dock_frame.pack(fill='both', expand=True)
        w, h = (80, 20) if mode == 'top' else (20, 80)
        fx, fy = (x - 40, y) if mode == 'top' else (x if mode == 'left' else x-20, y-40)
        self.expand_btn.config(text="—" if mode == 'top' else "│")
        dock_geo = f"{w}x{h}+{fx}+{fy}"
        self.last_dock_geo = dock_geo 
        if animate: self.animate(self.root.geometry(), dock_geo)
        else: self.root.geometry(dock_geo)
        self.save_config()

    def animate_to_dock_string(self, geo_str):
        self.is_docked = True
        self.main_frame.pack_forget()
        self.dock_frame.pack(fill='both', expand=True)
        if "80x20" in geo_str: self.expand_btn.config(text="—")
        else: self.expand_btn.config(text="│")
        self.animate(self.root.geometry(), geo_str)

    def undock_window(self):
        if not self.is_docked: return
        self.is_docked = False
        self.dock_frame.pack_forget()
        self.main_frame.pack(fill='both', expand=True)
        geo = self.saved_geometry if self.saved_geometry else f"{config.DEFAULT_WIDTH}x{config.DEFAULT_HEIGHT}+500+200"
        self.animate(self.root.geometry(), geo)
        self.last_interaction = time.time()

    def animate_resize(self, target_w, target_h):
        cur_w = self.root.winfo_width(); cur_h = self.root.winfo_height()
        cur_x = self.root.winfo_x(); cur_y = self.root.winfo_y()
        steps = 15; dt = 10 
        def _step(i):
            progress = i / steps
            ease = 1 - (1 - progress) ** 2 
            new_w = int(cur_w + (target_w - cur_w) * ease)
            new_h = int(cur_h + (target_h - cur_h) * ease)
            self.root.geometry(f"{new_w}x{new_h}+{cur_x}+{cur_y}")
            if i < steps: self.root.after(dt, lambda: _step(i + 1))
            else: self.root.geometry(f"{target_w}x{target_h}+{cur_x}+{cur_y}")
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
        mon = get_monitor_info(self.root.winfo_id())
        if not mon: mon = {'l': 0, 't': 0, 'r': self.root.winfo_screenwidth(), 'b': self.root.winfo_screenheight()}
        x, y = self.root.winfo_x(), self.root.winfo_y()
        if x < mon['l']+config.SNAP_THRESHOLD or x > mon['r']-config.SNAP_THRESHOLD or y < mon['t']+config.SNAP_THRESHOLD: 
            self.last_dock_geo = None; self.dock_window()
        else: self.save_config()

    def start_resize(self, e):
        self.resize_start_x = e.x_root; self.resize_start_y = e.y_root
        self.start_w = self.root.winfo_width(); self.start_h = self.root.winfo_height()
    def do_resize(self, e):
        dx = e.x_root - self.resize_start_x; dy = e.y_root - self.resize_start_y
        new_w, new_h = self.start_w + dx, self.start_h + dy
        if new_w > config.MIN_WIDTH and new_h > config.MIN_HEIGHT:
            self.root.geometry(f"{new_w}x{new_h}")
            self.root.update_idletasks()
    def stop_resize(self, e): self.save_config()

    def set_timeout(self, seconds): self.timeout = seconds; self.save_config()
    def reset_size(self): self.root.geometry(f"{config.DEFAULT_WIDTH}x{config.DEFAULT_HEIGHT}"); self.save_config()
    def hide_window(self): self.root.withdraw()

    def setup_context_menu(self):
        self.context_menu = tk.Menu(self.root, tearoff=0, bg=config.BG_COLOR, fg=config.TXT_COLOR)
        self.time_menu = tk.Menu(self.context_menu, tearoff=0, bg=config.BG_COLOR, fg=config.TXT_COLOR)
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
        menu = TrayMenu(TrayItem('Show', self.show_from_tray, default=True), 
                        TrayItem('Dock to Default', self.force_default_dock),
                        TrayItem('Quit', self.quit_app))
        img = Image.new('RGB', (64,64), (30,30,30)); d = ImageDraw.Draw(img)
        d.rectangle([16,26,48,38], fill="white")
        self.tray = TrayIcon("FloatPad", img, "FloatPad", menu)
        self.tray.run()

    def show_from_tray(self, icon=None, item=None):
        self.root.after(0, self.root.deiconify)
        self.root.after(10, self.root.lift)
        self.root.after(20, lambda: self.dock_window(animate=False))
        self.root.after(50, self.vibrate_eye_catch)

    def vibrate_eye_catch(self):
        orig_geo = self.root.geometry()
        try:
            parts = orig_geo.replace('+', 'x').split('x')
            w, h, x, y = map(int, parts)
            offsets = [5, -5, 4, -4, 2, -2, 0]
            def do_shake(index):
                if index < len(offsets):
                    new_x = x + offsets[index]
                    self.root.geometry(f"{w}x{h}+{new_x}+{y}")
                    self.root.after(30, lambda: do_shake(index + 1))
                else: self.root.geometry(orig_geo)
            do_shake(0)
        except: pass

    def save_config(self):
        if not self.is_docked: self.settings["geometry"] = self.root.geometry()
        self.settings.update({
            "timeout": self.timeout, "hide_on_type": self.hide_on_type,
            "always_default_dock": self.always_default_dock, "last_dock_geo": self.last_dock_geo
        })
        config.save_config_file(self.settings)
    
    def quit_app(self, *args):
        self.save_config()
        self.stop_threads = True
        try: keyboard.unhook_all()
        except: pass
        try: self.tray.stop()
        except: pass
        try: self.root.quit(); self.root.destroy()
        except: pass
        os._exit(0)
    
    def force_default_dock(self, icon=None, item=None):
        self.root.after(0, self.root.deiconify)
        self.root.after(10, self.root.lift)
        mon = get_monitor_info(self.root.winfo_id())
        if not mon: mon = {'l': 0, 't': 0}
        target_x = mon['l'] + 100; target_y = mon['t']
        self.root.after(20, lambda: self.set_dock('top', target_x, target_y, animate=False))
        self.root.after(50, self.vibrate_eye_catch)

if __name__ == "__main__":
    app = App()
    try: app.root.mainloop()
    except KeyboardInterrupt: app.quit_app()