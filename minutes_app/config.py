import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import zoom_minutes as zm

SESSIONS_DIR = os.path.join(ROOT, "sessions")
STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")

HOST = "127.0.0.1"
PORT = int(os.environ.get("MINUTES_PORT", "8765"))

LIVE_LINES = int(os.environ.get("MINUTES_LIVE_LINES", "25"))
LIVE_SECONDS = int(os.environ.get("MINUTES_LIVE_SECONDS", "90"))


def load_env():
    zm.load_dotenv()


def env(key, default=""):
    return os.environ.get(key, default)
