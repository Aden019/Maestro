"""Loads and saves which app each gesture opens, and which gesture means sleep."""

import json
import os
from pathlib import Path

from .gestures import SLEEP_GESTURES

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.json"
DEFAULT_BINDINGS = {"victory": "Safari", "three": "Notes", "shaka": "Music"}


def load_settings(path=CONFIG_PATH):
    """Returns (bindings, sleep gesture), using defaults for anything missing or invalid."""
    try:
        saved = json.loads(path.read_text())
        saved_bindings = saved.get("bindings", {})
        saved_sleep = saved.get("sleep_gesture")
    except (OSError, ValueError, AttributeError):
        saved_bindings, saved_sleep = {}, None
    bindings = {
        gesture: saved_bindings[gesture] if isinstance(saved_bindings.get(gesture), str) else app
        for gesture, app in DEFAULT_BINDINGS.items()
    }
    return bindings, saved_sleep if saved_sleep in SLEEP_GESTURES else SLEEP_GESTURES[0]


def save_settings(bindings, sleep_gesture, path=CONFIG_PATH):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps({"bindings": bindings, "sleep_gesture": sleep_gesture}, indent=2) + "\n")
    os.replace(temporary, path)
