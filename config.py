import json
import os

# --- Constants ---
CONFIG_FILE = "floatpad_config.json"
DEFAULT_WIDTH = 300
DEFAULT_HEIGHT = 360
MIN_WIDTH = 220
MIN_HEIGHT = 350
SNAP_THRESHOLD = 75

# --- Colors ---
BG_COLOR = "#1e1e1e"
TITLE_BG = "#252526"
ACCENT_COLOR = "#0078d4"
BTN_COLOR = "#333333"
BTN_HOVER = "#454545"
TXT_COLOR = "#ffffff"

def load_config():
    if os.path.exists(CONFIG_FILE):
        try: return json.load(open(CONFIG_FILE))
        except: pass
    return {}

def save_config_file(data):
    with open(CONFIG_FILE, 'w') as f:
        json.dump(data, f)