import tkinter as tk
import config # Import colors

class ToolTip:
    def __init__(self, widget, get_text_func):
        self.widget = widget
        self.get_text_func = get_text_func 
        self.tip_window = None
        self.label = None
        self.alpha = 0.0
        self.fade_job = None 
        self.is_hovering = False
        self.widget.bind("<Enter>", self.on_enter, add="+") 
        self.widget.bind("<Leave>", self.on_leave, add="+")

    def on_enter(self, event=None):
        self.is_hovering = True
        if self.fade_job:
            self.widget.after_cancel(self.fade_job)
            self.fade_job = None
        text = self.get_text_func()
        if not text: return
        if not self.tip_window:
            self.create_window(text)
        self.fade_in()

    def on_leave(self, event=None):
        self.is_hovering = False
        if self.fade_job:
            self.widget.after_cancel(self.fade_job)
            self.fade_job = None
        if self.tip_window:
            self.fade_out()

    def create_window(self, text):
        x = self.widget.winfo_rootx() + 5
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 5
        self.tip_window = tw = tk.Toplevel(self.widget)
        self.alpha = 0.0
        tw.attributes("-alpha", self.alpha)
        tw.attributes("-topmost", True)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        border_frame = tk.Frame(tw, bg="#555555", padx=1, pady=1)
        border_frame.pack(fill="both", expand=True)
        self.label = tk.Label(border_frame, text=text, justify=tk.LEFT,
                          background="#2b2b2b", fg="#ffffff",
                          relief=tk.FLAT, font=("Segoe UI", 9))
        self.label.pack(fill="both", expand=True, ipadx=5, ipady=2)

    def fade_in(self):
        if not self.is_hovering or not self.tip_window: return
        if self.alpha < 1.0:
            self.alpha += 0.08
            if self.alpha > 1.0: self.alpha = 1.0
            try: self.tip_window.attributes("-alpha", self.alpha)
            except: pass
            self.fade_job = self.widget.after(15, self.fade_in)
        else: self.fade_job = None

    def fade_out(self):
        if not self.tip_window: return
        if self.alpha > 0.0:
            self.alpha -= 0.08
            if self.alpha < 0.0: self.alpha = 0.0
            try: self.tip_window.attributes("-alpha", self.alpha)
            except: pass
            self.fade_job = self.widget.after(15, self.fade_out)
        else: self.destroy_window()

    def destroy_window(self):
        if self.fade_job: self.widget.after_cancel(self.fade_job)
        if self.tip_window: self.tip_window.destroy()
        self.tip_window = None
        self.label = None
        self.alpha = 0.0
        self.fade_job = None

    def refresh(self):
        if not self.tip_window or not self.label: return
        new_text = self.get_text_func()
        self.label.config(text=new_text)
        if self.fade_job: self.widget.after_cancel(self.fade_job)
        self.alpha = 0.5
        try: self.tip_window.attributes("-alpha", self.alpha)
        except: pass
        self.fade_in()

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
        lbl = tk.Label(self.container, text="Select Audio Output", font=("Segoe UI", 9, "bold"), 
                       bg="#252526", fg="#cccccc", pady=8, padx=10, anchor="w")
        lbl.pack(fill="x")
        tk.Frame(self.container, bg="#3e3e42", height=1).pack(fill="x", padx=5, pady=(0, 5))
        for item in items: self.create_item(item, current_id)
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
        lbl = tk.Label(row, text=name, font=("Segoe UI", 9), bg="#252526", fg="#ffffff", anchor="w", padx=5, pady=6)
        lbl.pack(side="left", fill="x", expand=True)
        def on_enter(e): row.config(bg="#37373d"); dot.config(bg="#37373d"); lbl.config(bg="#37373d")
        def on_leave(e): row.config(bg="#252526"); dot.config(bg="#252526"); lbl.config(bg="#252526")
        def on_click(e):
            self.callback(item['id'])
            self.destroy()
        for w in (row, lbl, dot):
            w.bind("<Enter>", on_enter); w.bind("<Leave>", on_leave); w.bind("<Button-1>", on_click)

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
        self.long_press_command = long_press_command
        self.bg_normal = bg
        self.bg_hover = hover_bg
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
        if self.repeat:
            if self.command: self.command()
            if self.repeat_job: self.after_cancel(self.repeat_job)
            self.repeat_job = self.after(300, self.do_repeat)
            return
        if self.long_press_command:
            self.long_press_job = self.after(400, self.do_long_press)
            return
        if self.command: self.command()
    def do_repeat(self):
        if self.repeat_command:
            self.repeat_command()
            self.repeat_job = self.after(100, self.do_repeat)
    def do_long_press(self):
        self.is_long_pressed = True
        if self.long_press_command:
            self.long_press_command()
            self.configure(bg="#005a9e")
    def on_release(self, e):
        self.configure(bg=self.bg_hover)
        if self.repeat_job:
            self.after_cancel(self.repeat_job); self.repeat_job = None
        if self.long_press_job:
            self.after_cancel(self.long_press_job); self.long_press_job = None
        if self.long_press_command and not self.is_long_pressed:
            if self.command: self.command()