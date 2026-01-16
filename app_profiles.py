# app_profiles.py

# --- INSTRUCTIONS ---
# Add keywords found in the Window Title of the apps you want to trigger specific views.
# Case does not matter (e.g., "Netflix" is the same as "netflix").

# List 1: Apps that switch FloatPad to NUMPAD view
# (Good for: Calculator, Excel, Banking, PIN codes, Netflix)
NUMPAD_APPS = [
    "excel",
    "calculator",
    "sheets",
    "numbers",
    "calc",
    "pin",       # Common word in lock screens
    "login",     # Common in banking
    "netflix",   # As per your request
    "auth"
]

# List 2: Apps that switch FloatPad to KEYBOARD view
# (Good for: Writing, Chatting, Browsing)
KEYBOARD_APPS = [
    "word",
    "notepad",
    "docs",
    "writer",
    "outlook",
    "teams",
    "discord",
    "whatsapp",
    "chrome",
    "edge",
    "firefox",
    "brave",
    "slack"
]