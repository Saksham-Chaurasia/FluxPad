import ctypes
from ctypes import wintypes
import sys
import os

user32 = ctypes.windll.user32
dwmapi = ctypes.windll.dwmapi

class MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), 
                ("rcMonitor", wintypes.RECT), 
                ("rcWork", wintypes.RECT), 
                ("dwFlags", wintypes.DWORD)]

def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
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
    """ Prevents window from stealing focus aggressively """
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