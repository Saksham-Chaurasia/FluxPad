import ctypes
from ctypes import wintypes
import sys
import os
import winreg  # <--- NEW IMPORT

user32 = ctypes.windll.user32
dwmapi = ctypes.windll.dwmapi

class MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), 
                ("rcMonitor", wintypes.RECT), 
                ("rcWork", wintypes.RECT), 
                ("dwFlags", wintypes.DWORD)]

def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

def apply_rounded_corners(hwnd):
    try: 
        dwmapi.DwmSetWindowAttribute(hwnd, 33, ctypes.byref(ctypes.c_int(2)), 4)
    except: pass

def set_no_focus(hwnd):
    try:
        style = user32.GetWindowLongW(hwnd, -20)
        user32.SetWindowLongW(hwnd, -20, style | 0x08000000 | 0x00000008)
    except: pass

def get_monitor_info(hwnd):
    try:
        h_mon = user32.MonitorFromWindow(hwnd, 2)
        mi = MONITORINFO()
        mi.cbSize = ctypes.sizeof(MONITORINFO)
        user32.GetMonitorInfoW(h_mon, ctypes.byref(mi))
        return {'l': mi.rcMonitor.left, 't': mi.rcMonitor.top, 
                'r': mi.rcMonitor.right, 'b': mi.rcMonitor.bottom}
    except: 
        return None

# --- NEW STARTUP LOGIC ---
def set_startup(enable=True):
    """ Adds or removes the app from Windows Startup Registry """
    app_name = "FloatPad"
    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_ALL_ACCESS)
        if enable:
            # Point to the current running EXE
            exe_path = sys.executable
            winreg.SetValueEx(key, app_name, 0, winreg.REG_SZ, exe_path)
        else:
            try:
                winreg.DeleteValue(key, app_name)
            except FileNotFoundError:
                pass
        winreg.CloseKey(key)
    except Exception as e:
        print(f"Startup Error: {e}")

def is_startup_enabled():
    """ Checks if the app is currently in the Startup Registry """
    app_name = "FloatPad"
    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_READ)
        winreg.QueryValueEx(key, app_name)
        winreg.CloseKey(key)
        return True
    except FileNotFoundError:
        return False
    except:
        return False